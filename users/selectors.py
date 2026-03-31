from django.contrib.auth import get_user_model
from django.db.models import Case, Count, IntegerField, Prefetch, Q, Value, When

from listings.models import Listing, ListingReport, ListingReportUpdate
from listings.selectors import with_feedback_summary

from .compatibility import compatibility_highlights, compute_compatibility
from .models import Role, UserFile


def admin_listings_queryset(query="", selected_status="", selected_review_status=""):
    status_values = {status for status, _ in Listing.STATUS_CHOICES}
    review_status_values = {status for status, _ in Listing.APPROVAL_CHOICES}
    review_priority = Case(
        When(approval_status=Listing.APPROVAL_PENDING, then=Value(0)),
        When(approval_status=Listing.APPROVAL_REJECTED, then=Value(1)),
        default=Value(2),
        output_field=IntegerField(),
    )
    queryset = with_feedback_summary(Listing.objects.with_related()).annotate(review_priority=review_priority)

    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(address__icontains=query)
            | Q(owner__email__icontains=query)
            | Q(owner__username__icontains=query)
        )
    if selected_status in status_values:
        queryset = queryset.filter(status=selected_status)
    if selected_review_status in review_status_values:
        queryset = queryset.filter(approval_status=selected_review_status)

    return queryset.order_by("review_priority", "-submitted_for_approval_at", "-created_at")


def admin_reports_queryset(query="", selected_status="", selected_reason="", *, include_closed=False):
    status_values = {status for status, _ in ListingReport.STATUS_CHOICES}
    reason_values = {reason for reason, _ in ListingReport.REASON_CHOICES}
    status_priority = Case(
        When(status=ListingReport.STATUS_OPEN, then=Value(0)),
        When(status=ListingReport.STATUS_IN_REVIEW, then=Value(1)),
        When(status=ListingReport.STATUS_RESOLVED, then=Value(2)),
        default=Value(3),
        output_field=IntegerField(),
    )
    queryset = (
        ListingReport.objects.select_related(
            "listing",
            "listing__owner",
            "reporter",
            "reviewed_by",
        )
        .prefetch_related(
            Prefetch(
                "updates",
                queryset=ListingReportUpdate.objects.select_related("actor").order_by("-created_at", "-id"),
            )
        )
        .annotate(status_priority=status_priority)
    )

    if query:
        queryset = queryset.filter(
            Q(listing__title__icontains=query)
            | Q(listing__address__icontains=query)
            | Q(reporter__email__icontains=query)
            | Q(reporter__username__icontains=query)
            | Q(details__icontains=query)
            | Q(resolution_notes__icontains=query)
        )
    if selected_status in status_values:
        queryset = queryset.filter(status=selected_status)
    elif not include_closed:
        queryset = queryset.filter(status__in=[ListingReport.STATUS_OPEN, ListingReport.STATUS_IN_REVIEW])
    if selected_reason in reason_values:
        queryset = queryset.filter(reason=selected_reason)

    return queryset.order_by("status_priority", "-created_at")


def admin_users_queryset(query="", selected_role="", selected_active=""):
    role_values = {role.value for role in Role}
    user_model = get_user_model()
    queryset = user_model.objects.all().order_by("username")

    if query:
        queryset = queryset.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )
    if selected_role in role_values:
        queryset = queryset.filter(role=selected_role)
    if selected_active in {"active", "inactive"}:
        queryset = queryset.filter(is_active=(selected_active == "active"))

    return queryset


def admin_dashboard_metrics():
    user_model = get_user_model()
    listing_metrics = Listing.objects.aggregate(
        total_listings=Count("id"),
        pending_review_listings=Count("id", filter=Q(approval_status=Listing.APPROVAL_PENDING)),
        approved_listings=Count("id", filter=Q(approval_status=Listing.APPROVAL_APPROVED)),
        rejected_listings=Count("id", filter=Q(approval_status=Listing.APPROVAL_REJECTED)),
    )
    user_metrics = user_model.objects.aggregate(
        student_users=Count("id", filter=Q(role=Role.STUDENT)),
        realtor_users=Count("id", filter=Q(role=Role.REALTOR)),
        admin_users_total=Count("id", filter=Q(role=Role.ADMIN)),
    )
    report_metrics = ListingReport.objects.aggregate(
        open_reports=Count("id", filter=Q(status=ListingReport.STATUS_OPEN)),
        reports_in_review=Count("id", filter=Q(status=ListingReport.STATUS_IN_REVIEW)),
    )
    return {
        **listing_metrics,
        **user_metrics,
        **report_metrics,
    }


def accessible_user_files_queryset(user):
    if user.is_bc_admin:
        return UserFile.objects.select_related("owner")
    return UserFile.objects.filter(owner=user).select_related("owner")


def compatible_students_for_user(user, limit=30):
    """
    Return a list of dicts {user, profile, score} for active students (excluding `user`)
    sorted descending by compatibility score. Students with no scoreable profile fields
    are excluded. At most `limit` results are returned.
    """
    user_model = get_user_model()
    candidates = (
        user_model.objects.filter(role=Role.STUDENT, is_active=True, profile_completed_at__isnull=False)
        .exclude(pk=user.pk)
        .select_related("student_profile")
    )

    if not getattr(user, "can_use_roommate_matching", False):
        return []
    my_profile = getattr(user, "student_profile", None)

    results = []
    for candidate in candidates:
        their_profile = getattr(candidate, "student_profile", None)
        if their_profile is None:
            continue
        score = compute_compatibility(my_profile, their_profile) if my_profile else None
        results.append(
            {
                "user": candidate,
                "profile": their_profile,
                "score": score,
                "highlights": compatibility_highlights(my_profile, their_profile),
            }
        )

    results.sort(key=lambda x: (x["score"] is not None, x["score"] or 0), reverse=True)
    return results[:limit]
