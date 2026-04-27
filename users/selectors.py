from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Case, Count, IntegerField, Prefetch, Q, Value, When
from django.utils import timezone

from communications.models import ListingConversation, ListingMessage
from communications.selectors import direct_conversations_by_counterparty
from core.utils import get_page
from listings.models import Listing, ListingReport
from listings.selectors import listing_reports_queryset_for_admin, with_feedback_summary
from roommates.models import FavoriteRoommate, RoommateGroupInvite, RoommateGroupInviteApproval, RoommateGroupMembership

from .compatibility import (
    compatibility_highlights,
    compute_compatibility,
    compute_group_compatibility,
    group_compatibility_highlights,
)
from .models import Role, UserFile, UserReport, UserReportUpdate

ROOMMATE_DISCOVERY_CANDIDATE_LIMIT = 300


def _percentage(numerator, denominator):
    if not denominator:
        return 0
    return round((numerator / denominator) * 100)


def roommate_candidate_results(
    user,
    *,
    query="",
    gender_filter="",
    smoke_filter="",
    pets_filter="",
    min_score=None,
):
    """
    Shared roommate-people ranking used by browse and hub:
    - Pulls active, completed student profiles (excluding the requester)
    - Applies basic field filters in SQL
    - Computes compatibility in Python for ranking and highlights
    - Returns list of dicts {user, profile, score, highlights}
    """
    User = get_user_model()
    my_profile = getattr(user, "student_profile", None)
    group_profiles = roommate_group_profiles_for_user(user)

    students_qs = (
        User.objects.filter(
            role=Role.STUDENT,
            is_active=True,
            profile_completed_at__isnull=False,
            roommate_access_restricted_at__isnull=True,
        )
        .exclude(id=user.id)
        .select_related("student_profile")
        .order_by("first_name", "last_name", "id")
    )
    if query:
        students_qs = students_qs.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(student_profile__preferred_name__icontains=query)
        )
    if gender_filter:
        students_qs = students_qs.filter(student_profile__gender=gender_filter)
    if smoke_filter == "yes":
        students_qs = students_qs.filter(student_profile__smoke=True)
    elif smoke_filter == "no":
        students_qs = students_qs.filter(student_profile__smoke=False)
    if pets_filter == "yes":
        students_qs = students_qs.filter(student_profile__pets=True)
    elif pets_filter == "no":
        students_qs = students_qs.filter(student_profile__pets=False)

    results = []
    for student in students_qs:
        their_profile = getattr(student, "student_profile", None)
        if group_profiles:
            score = compute_group_compatibility(group_profiles, their_profile) if their_profile else None
            highlights = group_compatibility_highlights(group_profiles, their_profile) if their_profile else []
        else:
            score = compute_compatibility(my_profile, their_profile) if my_profile and their_profile else None
            highlights = compatibility_highlights(my_profile, their_profile)
        if min_score is not None and (score is None or score < min_score):
            continue
        results.append({"user": student, "profile": their_profile, "score": score, "highlights": highlights})

    results.sort(key=lambda r: r["score"] if r["score"] is not None else -1, reverse=True)
    return results


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
    queryset = listing_reports_queryset_for_admin()

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


def user_reports_queryset_for_admin():
    status_priority = Case(
        When(status=UserReport.STATUS_OPEN, then=Value(0)),
        When(status=UserReport.STATUS_IN_REVIEW, then=Value(1)),
        When(status=UserReport.STATUS_RESOLVED, then=Value(2)),
        default=Value(3),
        output_field=IntegerField(),
    )
    return (
        UserReport.objects.select_related(
            "reported_user",
            "reporter",
            "reviewed_by",
        )
        .prefetch_related(
            "reported_user__socialaccount_set",
            "reporter__socialaccount_set",
            "reviewed_by__socialaccount_set",
            Prefetch(
                "updates",
                queryset=UserReportUpdate.objects.select_related("actor").order_by("-created_at", "-id"),
            ),
        )
        .annotate(status_priority=status_priority)
    )


def admin_user_reports_queryset(query="", selected_status="", selected_reason="", *, include_closed=False):
    status_values = {status for status, _ in UserReport.STATUS_CHOICES}
    reason_values = {reason for reason, _ in UserReport.REASON_CHOICES}
    queryset = user_reports_queryset_for_admin()

    if query:
        queryset = queryset.filter(
            Q(reported_user__email__icontains=query)
            | Q(reported_user__username__icontains=query)
            | Q(reporter__email__icontains=query)
            | Q(reporter__username__icontains=query)
            | Q(details__icontains=query)
            | Q(resolution_notes__icontains=query)
        )
    if selected_status in status_values:
        queryset = queryset.filter(status=selected_status)
    elif not include_closed:
        queryset = queryset.filter(status__in=[UserReport.STATUS_OPEN, UserReport.STATUS_IN_REVIEW])
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
        moderator_users=Count("id", filter=Q(role=Role.MODERATOR)),
        support_users=Count("id", filter=Q(role=Role.SUPPORT)),
        platform_admin_users=Count("id", filter=Q(role=Role.ADMIN)),
    )
    report_metrics = ListingReport.objects.aggregate(
        open_reports=Count("id", filter=Q(status=ListingReport.STATUS_OPEN)),
        reports_in_review=Count("id", filter=Q(status=ListingReport.STATUS_IN_REVIEW)),
    )
    user_report_metrics = UserReport.objects.aggregate(
        open_user_reports=Count("id", filter=Q(status=UserReport.STATUS_OPEN)),
        user_reports_in_review=Count("id", filter=Q(status=UserReport.STATUS_IN_REVIEW)),
    )
    return {
        **listing_metrics,
        **user_metrics,
        **report_metrics,
        **user_report_metrics,
    }


def admin_dashboard_snapshot(*, query="", selected_status="", selected_review_status=""):
    snapshot_minute = timezone.localtime().strftime("%Y%m%d%H%M")
    cache_key = f"admin-dashboard:{query}:{selected_status}:{selected_review_status}:{snapshot_minute}"
    cached_snapshot = cache.get(cache_key)
    if cached_snapshot is not None:
        return cached_snapshot

    user_model = get_user_model()
    now = timezone.now()
    today = timezone.localdate()
    weekly_cutoff = now - timedelta(days=7)
    listings_qs = admin_listings_queryset(
        query=query,
        selected_status=selected_status,
        selected_review_status=selected_review_status,
    )
    reports_qs = admin_reports_queryset()
    user_reports_qs = admin_user_reports_queryset()
    recent_users_qs = user_model.objects.order_by("-date_joined", "-id")
    recent_messages_qs = ListingMessage.objects.select_related(
        "sender",
        "conversation",
        "conversation__listing",
        "conversation__owner",
        "conversation__participant",
    ).order_by("-created_at")

    metrics = admin_dashboard_metrics()
    metrics.update(
        Listing.objects.aggregate(
            live_marketplace_listings=Count(
                "id",
                filter=Q(
                    archived_at__isnull=True,
                    approval_status=Listing.APPROVAL_APPROVED,
                    is_hidden=False,
                    status=Listing.STATUS_AVAILABLE,
                    end_date__gte=today,
                ),
            ),
            archived_listings=Count("id", filter=Q(archived_at__isnull=False)),
            listings_last_7_days=Count("id", filter=Q(created_at__gte=weekly_cutoff)),
        )
    )
    metrics.update(
        user_model.objects.aggregate(
            total_users=Count("id"),
            active_users=Count("id", filter=Q(is_active=True)),
            inactive_users=Count("id", filter=Q(is_active=False)),
            new_users_last_7_days=Count("id", filter=Q(date_joined__gte=weekly_cutoff)),
        )
    )
    metrics.update(
        ListingReport.objects.aggregate(
            resolved_reports=Count("id", filter=Q(status=ListingReport.STATUS_RESOLVED)),
            reports_last_7_days=Count("id", filter=Q(created_at__gte=weekly_cutoff)),
        )
    )
    metrics.update(
        UserReport.objects.aggregate(
            resolved_user_reports=Count("id", filter=Q(status=UserReport.STATUS_RESOLVED)),
            user_reports_last_7_days=Count("id", filter=Q(created_at__gte=weekly_cutoff)),
        )
    )

    total_conversations = ListingConversation.objects.count()
    total_messages = ListingMessage.objects.count()
    active_listing_incidents = metrics["open_reports"] + metrics["reports_in_review"]
    active_user_incidents = metrics["open_user_reports"] + metrics["user_reports_in_review"]
    active_incidents = active_listing_incidents + active_user_incidents

    metrics.update(
        {
            "total_conversations": total_conversations,
            "total_messages": total_messages,
            "messages_last_7_days": ListingMessage.objects.filter(created_at__gte=weekly_cutoff).count(),
            "direct_conversations": ListingConversation.objects.filter(
                conversation_type=ListingConversation.CONVERSATION_TYPE_DIRECT
            ).count(),
            "listing_conversations": ListingConversation.objects.filter(
                conversation_type=ListingConversation.CONVERSATION_TYPE_LISTING
            ).count(),
            "filtered_listings_count": listings_qs.count(),
            "approval_rate": _percentage(metrics["approved_listings"], metrics["total_listings"]),
            "marketplace_live_rate": _percentage(metrics["live_marketplace_listings"], metrics["total_listings"]),
            "incident_rate": _percentage(active_incidents, metrics["total_listings"]),
            "active_user_rate": _percentage(metrics["active_users"], metrics["total_users"]),
            "messages_per_conversation": round(total_messages / total_conversations, 1) if total_conversations else 0,
            "active_incidents": active_incidents,
            "active_listing_incidents": active_listing_incidents,
            "active_user_incidents": active_user_incidents,
            "priority_listings": list(listings_qs[:8]),
            "review_queue": list(admin_listings_queryset(selected_review_status=Listing.APPROVAL_PENDING)[:5]),
            "recent_reports": list(reports_qs[:5]),
            "recent_user_reports": list(user_reports_qs[:5]),
            "recent_users": list(recent_users_qs[:5]),
            "recent_messages": list(recent_messages_qs[:6]),
        }
    )
    cache.set(cache_key, metrics, timeout=60)
    return metrics


def accessible_user_files_queryset(user):
    if not getattr(user, "is_authenticated", False):
        return UserFile.objects.none()
    return UserFile.objects.filter(owner=user).select_related("owner")


def compatible_students_for_user(user, limit=30):
    """
    Return a list of dicts {user, profile, score} for active students (excluding `user`)
    sorted descending by compatibility score. Students with no scoreable profile fields
    are excluded. At most `limit` results are returned.
    """
    user_model = get_user_model()
    candidates = (
        user_model.objects.filter(
            role=Role.STUDENT,
            is_active=True,
            profile_completed_at__isnull=False,
            roommate_access_restricted_at__isnull=True,
        )
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


def active_roommate_group_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return None
    membership = RoommateGroupMembership.objects.select_related("group").filter(user=user).first()
    if membership is None:
        return None
    return membership.group


def roommate_group_memberships(group):
    return (
        RoommateGroupMembership.objects.filter(group=group)
        .select_related("user", "user__student_profile")
        .order_by("created_at", "id")
    )


def roommate_group_profiles_for_user(user):
    if not getattr(user, "can_use_roommate_matching", False):
        return []
    group = active_roommate_group_for_user(user)
    if group is None:
        return []
    memberships = roommate_group_memberships(group)
    profiles = []
    for membership in memberships:
        profile = getattr(membership.user, "student_profile", None)
        if profile is not None:
            profiles.append(profile)
    return profiles


def pending_group_invite_approvals_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return RoommateGroupInviteApproval.objects.none()
    return RoommateGroupInviteApproval.objects.select_related(
        "invite",
        "invite__group",
        "invite__invitee",
        "invite__inviter",
    ).filter(
        member=user,
        approved__isnull=True,
        invite__status=RoommateGroupInvite.STATUS_PENDING_APPROVAL,
    )


def pending_group_invites_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return RoommateGroupInvite.objects.none()
    return RoommateGroupInvite.objects.select_related(
        "group",
        "inviter",
        "inviter__student_profile",
        "conversation",
    ).filter(
        invitee=user,
        status=RoommateGroupInvite.STATUS_PENDING_INVITEE,
    )


def pending_group_invite_for_conversation(user, conversation):
    if conversation is None or not getattr(conversation, "is_direct", False):
        return None
    return (
        RoommateGroupInvite.objects.select_related("group", "inviter")
        .filter(
            conversation=conversation,
            invitee=user,
            status=RoommateGroupInvite.STATUS_PENDING_INVITEE,
        )
        .first()
    )


def favorited_people_queryset(user):
    if not getattr(user, "is_authenticated", False):
        return FavoriteRoommate.objects.none()
    return FavoriteRoommate.objects.filter(user=user).select_related("favorite_user", "favorite_user__student_profile")


def favorite_roommate_ids_for_user(user, candidates):
    if not getattr(user, "is_authenticated", False):
        return set()
    candidate_ids = [candidate.id for candidate in candidates]
    if not candidate_ids:
        return set()
    return set(
        FavoriteRoommate.objects.filter(user=user, favorite_user_id__in=candidate_ids).values_list(
            "favorite_user_id",
            flat=True,
        )
    )


def discover_roommate_people(
    user,
    *,
    query="",
    gender_filter="",
    smoke_filter="",
    pets_filter="",
    min_score=None,
    page=None,
    per_page=12,
):
    user_model = get_user_model()
    my_profile = getattr(user, "student_profile", None)
    group_profiles = roommate_group_profiles_for_user(user)
    active_group = active_roommate_group_for_user(user)
    group_memberships = list(roommate_group_memberships(active_group)) if active_group else []
    group_member_ids = {membership.user_id for membership in group_memberships}

    students_qs = (
        user_model.objects.filter(
            role=Role.STUDENT,
            is_active=True,
            profile_completed_at__isnull=False,
        )
        .exclude(id=user.id)
        .select_related("student_profile")
        .order_by("first_name", "last_name", "id")
    )

    if query:
        students_qs = students_qs.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(student_profile__preferred_name__icontains=query)
        )
    if gender_filter:
        students_qs = students_qs.filter(student_profile__gender=gender_filter)
    if smoke_filter == "yes":
        students_qs = students_qs.filter(student_profile__smoke=True)
    elif smoke_filter == "no":
        students_qs = students_qs.filter(student_profile__smoke=False)
    if pets_filter == "yes":
        students_qs = students_qs.filter(student_profile__pets=True)
    elif pets_filter == "no":
        students_qs = students_qs.filter(student_profile__pets=False)

    results = []
    for student in students_qs[:ROOMMATE_DISCOVERY_CANDIDATE_LIMIT]:
        their_profile = getattr(student, "student_profile", None)
        if group_profiles:
            score = compute_group_compatibility(group_profiles, their_profile) if their_profile else None
            highlights = group_compatibility_highlights(group_profiles, their_profile) if their_profile else []
        else:
            score = compute_compatibility(my_profile, their_profile) if my_profile and their_profile else None
            highlights = compatibility_highlights(my_profile, their_profile)
        if min_score is not None and (score is None or score < min_score):
            continue
        results.append(
            {
                "user": student,
                "profile": their_profile,
                "score": score,
                "highlights": highlights,
            }
        )

    results.sort(key=lambda result: result["score"] if result["score"] is not None else -1, reverse=True)
    results_page = get_page(results, page, per_page)
    page_results = list(results_page.object_list)

    if user.can_use_roommate_matching and page_results:
        existing_convos = direct_conversations_by_counterparty(user, [result["user"] for result in page_results])
    else:
        existing_convos = {}

    favorite_ids = favorite_roommate_ids_for_user(user, [result["user"] for result in page_results])
    invite_status_map = {
        invitee_id: status
        for invitee_id, status in RoommateGroupInvite.objects.filter(
            inviter=user,
            invitee__in=[result["user"] for result in page_results],
            status__in=[
                RoommateGroupInvite.STATUS_PENDING_APPROVAL,
                RoommateGroupInvite.STATUS_PENDING_INVITEE,
            ],
        ).values_list("invitee_id", "status")
    }

    for result in page_results:
        is_in_group = result["user"].id in group_member_ids
        result["existing_convo"] = existing_convos.get(result["user"].id)
        result["invite_status"] = invite_status_map.get(result["user"].id)
        result["is_in_group"] = is_in_group
        result["already_in_group"] = is_in_group
        result["is_favorited"] = result["user"].id in favorite_ids

    return {
        "results_page": results_page,
        "results_total": results_page.paginator.count,
        "filters_active": any([query, gender_filter, smoke_filter, pets_filter, min_score is not None]),
        "has_my_profile": my_profile is not None,
        "can_message": user.can_use_roommate_matching,
        "active_group": active_group,
        "group_memberships": group_memberships,
        "is_group_lead": active_group is not None and active_group.lead_id == user.id,
    }
