from django.contrib.auth import get_user_model
from django.db.models import Q

from communications.selectors import direct_conversations_by_counterparty
from core.utils import get_page
from listings.models import Listing
from listings.selectors import marketplace_listings_for_user, with_favorite_state
from users.compatibility import (
    compatibility_highlights,
    compute_compatibility,
    compute_group_compatibility,
    group_compatibility_highlights,
)

from .models import (
    FavoriteRoommate,
    RoommateGroup,
    RoommateGroupInvite,
    RoommateGroupInviteApproval,
    RoommateGroupMembership,
    RoommatePost,
)

ROOMMATE_DISCOVERY_CANDIDATE_LIMIT = 300


def roommate_post_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return None
    return RoommatePost.objects.with_related().filter(author=user).first()


def roommate_group_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return None
    return RoommateGroup.objects.prefetch_related("members").filter(lead=user).first()


def roommate_group_post_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return None
    return RoommatePost.objects.with_related().filter(group__lead=user).first()


def active_roommate_post_for_user(user):
    if not getattr(user, "is_authenticated", False):
        return None
    return RoommatePost.objects.active().filter(Q(author=user) | Q(group__lead=user)).first()


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
    return [
        membership.user.student_profile
        for membership in roommate_group_memberships(group)
        if getattr(membership.user, "student_profile", None) is not None
    ]


def open_listings_matching_roommate_post(user, roommate_post):
    if roommate_post is None:
        return Listing.objects.none()

    queryset = with_favorite_state(marketplace_listings_for_user(user), user)
    move_in_date = getattr(roommate_post, "move_in_date", None)
    if move_in_date:
        queryset = queryset.filter(start_date__lte=move_in_date, end_date__gte=move_in_date)

    target_size = roommate_post.target_household_size or roommate_post.current_group_size
    if target_size:
        queryset = queryset.filter(rooms__gte=target_size)

    return queryset.order_by("-created_at")


def filtered_roommate_posts_queryset(
    user,
    *,
    query="",
    housing_status="",
    max_budget=None,
    move_in_by=None,
    open_spots_min=None,
    people_in_group=None,
):
    queryset = RoommatePost.objects.active()
    if getattr(user, "is_authenticated", False):
        queryset = queryset.exclude(Q(author=user) | Q(group__lead=user))

    if query:
        queryset = queryset.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(neighborhoods__icontains=query)
            | Q(group__name__icontains=query)
            | Q(author__first_name__icontains=query)
            | Q(author__last_name__icontains=query)
            | Q(author__username__icontains=query)
            | Q(author__student_profile__major__icontains=query)
            | Q(group__lead__first_name__icontains=query)
            | Q(group__lead__last_name__icontains=query)
            | Q(group__lead__username__icontains=query)
            | Q(group__members__first_name__icontains=query)
            | Q(group__members__last_name__icontains=query)
            | Q(group__members__student_profile__major__icontains=query)
        )
    if housing_status in {value for value, _ in RoommatePost.HOUSING_CHOICES}:
        queryset = queryset.filter(housing_status=housing_status)
    if max_budget is not None:
        queryset = queryset.filter(budget_min__lte=max_budget)
    if move_in_by is not None:
        queryset = queryset.filter(move_in_date__lte=move_in_by)
    if open_spots_min is not None:
        queryset = queryset.filter(open_spots__gte=open_spots_min)
    if people_in_group is not None:
        queryset = queryset.filter(open_spots__gte=people_in_group)

    return queryset.distinct().order_by("-updated_at", "-created_at")


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
    saved_only=False,
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
            role="student",
            is_active=True,
            profile_completed_at__isnull=False,
        )
        .exclude(id=user.id)
        .select_related("student_profile")
        .order_by("first_name", "last_name", "id")
    )
    if saved_only:
        students_qs = students_qs.filter(
            id__in=FavoriteRoommate.objects.filter(user=user).values_list("favorite_user_id", flat=True)
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
        result["already_in_group"] = is_in_group
        result["is_favorited"] = result["user"].id in favorite_ids

    return {
        "results_page": results_page,
        "results_total": results_page.paginator.count,
        "filters_active": any([query, gender_filter, smoke_filter, pets_filter, min_score is not None, saved_only]),
        "has_my_profile": my_profile is not None,
        "can_message": user.can_use_roommate_matching,
        "active_group": active_group,
        "group_memberships": group_memberships,
        "is_group_lead": active_group is not None and active_group.lead_id == user.id,
    }
