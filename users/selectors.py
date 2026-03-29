from django.contrib.auth import get_user_model
from django.db.models import Case, Count, IntegerField, Q, Value, When

from listings.models import Listing, ListingReport
from listings.selectors import with_feedback_summary

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


def admin_reports_queryset(query="", selected_status="", selected_reason=""):
    status_values = {status for status, _ in ListingReport.STATUS_CHOICES}
    reason_values = {reason for reason, _ in ListingReport.REASON_CHOICES}
    status_priority = Case(
        When(status=ListingReport.STATUS_OPEN, then=Value(0)),
        When(status=ListingReport.STATUS_IN_REVIEW, then=Value(1)),
        When(status=ListingReport.STATUS_RESOLVED, then=Value(2)),
        default=Value(3),
        output_field=IntegerField(),
    )
    queryset = ListingReport.objects.select_related(
        "listing",
        "listing__owner",
        "reporter",
        "reviewed_by",
    ).annotate(status_priority=status_priority)

    if query:
        queryset = queryset.filter(
            Q(listing__title__icontains=query)
            | Q(listing__address__icontains=query)
            | Q(reporter__email__icontains=query)
            | Q(reporter__username__icontains=query)
            | Q(details__icontains=query)
        )
    if selected_status in status_values:
        queryset = queryset.filter(status=selected_status)
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
