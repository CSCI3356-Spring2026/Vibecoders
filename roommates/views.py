from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from communications.forms import ConversationMessageForm
from communications.selectors import direct_conversation_between_users
from core.utils import preserved_query_suffix, safe_next_url
from listings.roommate_post_service import decorate_roommate_posts_for_user
from users.compatibility import (
    compatibility_highlights,
    compute_compatibility,
    compute_group_compatibility,
    group_compatibility_highlights,
)
from users.forms import UserReportForm
from users.models import UserReport

from .forms import RoommateGroupForm, RoommatePostFilterForm, RoommatePostForm
from .models import RoommateGroupInvite, RoommateGroupMembership, RoommatePost
from .selectors import (
    active_roommate_group_for_user,
    active_roommate_post_for_user,
    discover_roommate_people,
    favorited_people_queryset,
    filtered_roommate_posts_queryset,
    roommate_group_for_user,
    roommate_group_memberships,
    roommate_group_post_for_user,
    roommate_group_profiles_for_user,
    roommate_post_for_user,
)
from .services import (
    create_group_invite,
    respond_to_group_invite,
    respond_to_invite_approval,
    save_roommate_group_details,
)
from .services import remove_group_member as remove_roommate_group_member

ROOMMATE_POSTS_PER_PAGE = 12
ROOMMATE_PEOPLE_PER_PAGE = 12


def _first_form_error(form, fallback):
    if form.non_field_errors():
        return form.non_field_errors()[0]
    for field_errors in form.errors.values():
        if field_errors:
            return field_errors[0]
    return fallback


def _lifestyle_match_class_for_diff(diff):
    if diff is None:
        return ""
    if diff <= 0:
        return "lifestyle-match-strong"
    if diff == 1:
        return "lifestyle-match-good"
    if diff == 2:
        return "lifestyle-match-mid"
    if diff == 3:
        return "lifestyle-match-low"
    return "lifestyle-match-poor"


def _bedtime_difference_hours(value_a, value_b):
    raw_diff = abs(value_a - value_b)
    return min(raw_diff, 24 - raw_diff)


def _lifestyle_match_classes(my_profile, their_profile, *, enabled):
    if not enabled or my_profile is None or their_profile is None:
        return {}

    classes = {}
    for field_name in ("messy_level", "noise_level", "guest_level", "drink", "party"):
        my_value = getattr(my_profile, field_name)
        their_value = getattr(their_profile, field_name)
        if my_value is None or their_value is None:
            continue
        classes[field_name] = _lifestyle_match_class_for_diff(abs(my_value - their_value))

    if my_profile.bedtime is not None and their_profile.bedtime is not None:
        bedtime_diff = _bedtime_difference_hours(my_profile.bedtime, their_profile.bedtime)
        classes["bedtime"] = _lifestyle_match_class_for_diff(bedtime_diff)

    for field_name in ("smoke", "pets"):
        matches = getattr(my_profile, field_name) == getattr(their_profile, field_name)
        classes[field_name] = "lifestyle-match-strong" if matches else "lifestyle-match-poor"

    return classes


def _groups_tab_context(
    request,
    *,
    create_form=None,
    edit_forms_by_pk=None,
    edit_error_pk=None,
    show_create_modal=False,
):
    personal_post = roommate_post_for_user(request.user)
    led_group = roommate_group_for_user(request.user)
    group_post = roommate_group_post_for_user(request.user)
    display_group = led_group or active_roommate_group_for_user(request.user)
    all_posts = [post for post in (personal_post, group_post) if post is not None]
    my_posts_with_forms = []
    for post in all_posts:
        if edit_forms_by_pk and post.pk in edit_forms_by_pk:
            form = edit_forms_by_pk[post.pk]
        else:
            group = led_group if post.group_id else None
            form = RoommatePostForm(instance=post, user=request.user, group=group)
        my_posts_with_forms.append((post, form))

    if create_form is None:
        create_form = RoommatePostForm(user=request.user)
    group_members = list(roommate_group_memberships(display_group)) if display_group else []
    return {
        "my_posts_with_forms": my_posts_with_forms,
        "roommate_post_create_form": create_form,
        "show_create_modal": show_create_modal,
        "edit_error_pk": edit_error_pk,
        "display_group": display_group,
        "group_members": group_members,
        "is_group_lead": display_group is not None and display_group.lead_id == request.user.id,
    }


def _posts_tab_context(request):
    filter_form = RoommatePostFilterForm(request.GET or None)
    filter_data = {}
    if filter_form.is_bound:
        filter_form.is_valid()
        filter_data = filter_form.cleaned_data

    group_profiles = roommate_group_profiles_for_user(request.user)
    roommate_posts = filtered_roommate_posts_queryset(
        request.user,
        query=filter_data.get("q", ""),
        housing_status=filter_data.get("housing_status", ""),
        max_budget=filter_data.get("max_budget"),
        move_in_by=filter_data.get("move_in_by"),
        open_spots_min=filter_data.get("open_spots_min"),
        people_in_group=filter_data.get("people_in_group"),
    )
    roommate_posts = decorate_roommate_posts_for_user(request.user, roommate_posts, group_profiles=group_profiles)
    page_obj = preserved_query_suffix(request.GET, "page")
    return {
        "roommate_post_filter_form": filter_form,
        "roommate_posts": request_page(roommate_posts, request.GET.get("page")),
        "roommate_posts_total": len(roommate_posts),
        "pagination_query": page_obj,
        "can_message_roommate_posts": request.user.can_use_roommate_matching,
        "roommate_filters_active": any(filter_data.get(field_name) for field_name in filter_data),
    }


def request_page(items, page_number):
    from core.utils import get_page

    return get_page(items, page_number, ROOMMATE_POSTS_PER_PAGE)


def _people_tab_context(request):
    query = request.GET.get("q", "").strip()
    gender_filter = request.GET.get("gender", "").strip()
    smoke_filter = request.GET.get("smoke", "").strip()
    pets_filter = request.GET.get("pets", "").strip()
    min_score_raw = request.GET.get("min_score", "").strip()
    saved_only = request.GET.get("saved", "").strip().lower() in {"1", "true", "yes", "on"}
    min_score = int(min_score_raw) if min_score_raw.isdigit() else None

    discovery = discover_roommate_people(
        request.user,
        query=query,
        gender_filter=gender_filter,
        smoke_filter=smoke_filter,
        pets_filter=pets_filter,
        min_score=min_score,
        saved_only=saved_only,
        page=request.GET.get("page"),
        per_page=ROOMMATE_PEOPLE_PER_PAGE,
    )

    return {
        "people_results": discovery["results_page"],
        "people_results_total": discovery["results_total"],
        "pagination_query": preserved_query_suffix(request.GET, "page"),
        "has_my_profile": discovery["has_my_profile"],
        "can_message": discovery["can_message"],
        "is_group_lead": discovery["is_group_lead"],
        "people_gender_filter": gender_filter,
        "people_smoke_filter": smoke_filter,
        "people_pets_filter": pets_filter,
        "people_min_score": min_score_raw,
        "people_saved_only": saved_only,
        "people_filters_active": discovery["filters_active"],
    }


@login_required
@require_GET
def hub(request):
    if not request.user.is_student:
        raise Http404

    tab = request.GET.get("tab", "posts")
    if tab not in {"posts", "people", "groups"}:
        tab = "posts"

    personal_post = roommate_post_for_user(request.user)
    has_any_post = personal_post is not None or roommate_group_post_for_user(request.user) is not None
    context = {
        "tab": tab,
        "can_manage_roommate_post": True,
        "current_roommate_post": personal_post,
        "has_any_roommate_post": has_any_post,
        "roommate_post_create_form": RoommatePostForm(user=request.user),
        "show_create_modal": False,
        "edit_error_pk": None,
        "my_posts_with_forms": [],
    }
    if tab == "posts":
        context.update(_posts_tab_context(request))
    elif tab == "people":
        context.update(_people_tab_context(request))
    else:
        context.update(_groups_tab_context(request))
    return render(request, "listings/roommates_hub.html", context)


@login_required
@require_GET
def public_profile(request, user_id):
    if not request.user.is_student:
        raise Http404
    user_model = get_user_model()
    target = get_object_or_404(
        user_model,
        id=user_id,
        role="student",
        is_active=True,
        profile_completed_at__isnull=False,
        roommate_access_restricted_at__isnull=True,
    )
    their_profile = getattr(target, "student_profile", None)
    if their_profile is None:
        raise Http404

    is_self_profile = request.user.id == target.id
    my_profile = getattr(request.user, "student_profile", None)
    if is_self_profile:
        score = None
        highlights = []
    else:
        group_profiles = roommate_group_profiles_for_user(request.user)
        if group_profiles:
            score = compute_group_compatibility(group_profiles, their_profile) if their_profile else None
            highlights = group_compatibility_highlights(group_profiles, their_profile)
        else:
            score = compute_compatibility(my_profile, their_profile) if my_profile else None
            highlights = compatibility_highlights(my_profile, their_profile)

    existing_direct_conversation = None
    direct_message_form = None
    if not is_self_profile and request.user.can_use_roommate_matching:
        existing_direct_conversation = direct_conversation_between_users(request.user, target)
    has_active_roommate_post = active_roommate_post_for_user(target) is not None
    can_message_user = not is_self_profile and request.user.can_use_roommate_matching
    if can_message_user:
        direct_message_form = ConversationMessageForm(
            placeholder="Introduce yourself and compare housing plans.",
        )

    active_group = active_roommate_group_for_user(request.user)
    group_member_ids = (
        {membership.user_id for membership in roommate_group_memberships(active_group)} if active_group else set()
    )
    group_member_count = len(group_member_ids) if group_member_ids else (1 if my_profile else 0)
    invite_status = (
        RoommateGroupInvite.objects.filter(
            inviter=request.user,
            invitee=target,
            status__in=[
                RoommateGroupInvite.STATUS_PENDING_APPROVAL,
                RoommateGroupInvite.STATUS_PENDING_INVITEE,
            ],
        )
        .values_list("status", flat=True)
        .first()
    )
    is_favorited = False
    active_user_report = None
    user_report_form = None
    if not is_self_profile and request.user.is_student:
        is_favorited = favorited_people_queryset(request.user).filter(favorite_user=target).exists()
        active_user_report = (
            UserReport.objects.filter(
                reported_user=target,
                reporter=request.user,
                status__in=[UserReport.STATUS_OPEN, UserReport.STATUS_IN_REVIEW],
            )
            .order_by("-created_at")
            .first()
        )
        if active_user_report is None:
            user_report_form = UserReportForm()

    return render(
        request,
        "users/public_profile.html",
        {
            "target": target,
            "their_profile": their_profile,
            "score": score,
            "compatibility_highlights": highlights,
            "show_compatibility": not is_self_profile,
            "lifestyle_match_classes": _lifestyle_match_classes(my_profile, their_profile, enabled=not is_self_profile),
            "can_message_user": can_message_user,
            "has_active_roommate_post": has_active_roommate_post,
            "existing_direct_conversation": existing_direct_conversation,
            "direct_message_form": direct_message_form,
            "active_group": active_group,
            "invite_status": invite_status,
            "is_favorited": is_favorited,
            "is_in_group": target.id in group_member_ids,
            "group_member_count": group_member_count,
            "active_user_report": active_user_report,
            "user_report_form": user_report_form,
        },
    )


@login_required
@require_POST
def save_roommate_post(request):
    if not request.user.is_student:
        return HttpResponseForbidden("Student access is required to use roommate posts.")

    current_post = roommate_post_for_user(request.user)
    was_active = bool(current_post and current_post.is_active)
    form = RoommatePostForm(request.POST, instance=current_post, user=request.user)
    if form.is_valid():
        form.save()
        if current_post is None:
            messages.success(request, "Roommate post published.")
        elif was_active:
            messages.success(request, "Roommate post updated.")
        else:
            messages.success(request, "Roommate post reactivated.")
        return redirect(f"{reverse('roommates:hub')}?tab=groups")

    messages.error(request, _first_form_error(form, "Review the highlighted roommate post fields and try again."))
    context = {
        "tab": "groups",
        "can_manage_roommate_post": True,
        "current_roommate_post": current_post,
    }
    context.update(_groups_tab_context(request, create_form=form, show_create_modal=True))
    return render(request, "listings/roommates_hub.html", context)


@login_required
@require_POST
def save_roommate_group(request):
    if not request.user.is_student:
        return HttpResponseForbidden("Student access is required to use roommate groups.")

    current_group = roommate_group_for_user(request.user)
    form = RoommateGroupForm(request.POST, instance=current_group, user=request.user)
    if form.is_valid():
        save_roommate_group_details(
            lead=request.user,
            group=current_group,
            name=form.cleaned_data["name"],
            description=form.cleaned_data["description"],
        )
        messages.success(request, "Roommate group saved.")
    else:
        messages.error(request, _first_form_error(form, "Review the highlighted roommate group fields and try again."))
    return redirect(f"{reverse('roommates:hub')}?tab=groups")


@login_required
@require_POST
def save_group_roommate_post(request):
    if not request.user.is_student:
        return HttpResponseForbidden("Student access is required to use roommate posts.")

    current_group = roommate_group_for_user(request.user)
    if current_group is None:
        messages.error(request, "Create your roommate group before publishing a group post.")
        return redirect(f"{reverse('roommates:hub')}?tab=groups")

    current_post = roommate_group_post_for_user(request.user)
    was_active = bool(current_post and current_post.is_active)
    form = RoommatePostForm(request.POST, instance=current_post, user=request.user, group=current_group)
    if form.is_valid():
        form.save()
        if current_post is None:
            messages.success(request, "Group roommate post published.")
        elif was_active:
            messages.success(request, "Group roommate post updated.")
        else:
            messages.success(request, "Group roommate post reactivated.")
    else:
        messages.error(request, _first_form_error(form, "Review the highlighted group post fields and try again."))
    return redirect(f"{reverse('roommates:hub')}?tab=groups")


@login_required
@require_POST
def deactivate_roommate_post(request):
    if not request.user.is_student:
        return HttpResponseForbidden("Student access is required to use roommate posts.")

    roommate_post = roommate_post_for_user(request.user)
    if roommate_post is not None and roommate_post.is_active:
        roommate_post.is_active = False
        roommate_post.save(update_fields=["is_active", "updated_at"])
        messages.success(request, "Roommate post paused.")
    return redirect(f"{reverse('roommates:hub')}?tab=groups")


@login_required
@require_POST
def deactivate_group_roommate_post(request):
    if not request.user.is_student:
        return HttpResponseForbidden("Student access is required to use roommate posts.")

    roommate_post = roommate_group_post_for_user(request.user)
    if roommate_post is not None and roommate_post.is_active:
        roommate_post.is_active = False
        roommate_post.save(update_fields=["is_active", "updated_at"])
        messages.success(request, "Group roommate post paused.")
    return redirect(f"{reverse('roommates:hub')}?tab=groups")


@login_required
@require_POST
def edit_roommate_post(request, pk):
    if not request.user.is_student:
        return HttpResponseForbidden("Student access is required.")

    post = get_object_or_404(RoommatePost, pk=pk)
    current_group = roommate_group_for_user(request.user)
    if post.author_id != request.user.id and (current_group is None or post.group_id != current_group.pk):
        return HttpResponseForbidden("You cannot edit this post.")

    group = current_group if post.group_id else None
    form = RoommatePostForm(request.POST, instance=post, user=request.user, group=group)
    if form.is_valid():
        form.save()
        messages.success(request, "Post updated.")
        return redirect(f"{reverse('roommates:hub')}?tab=groups")

    messages.error(request, _first_form_error(form, "Review the highlighted fields and try again."))
    context = {
        "tab": "groups",
        "can_manage_roommate_post": True,
        "current_roommate_post": roommate_post_for_user(request.user),
    }
    context.update(_groups_tab_context(request, edit_forms_by_pk={post.pk: form}, edit_error_pk=post.pk))
    return render(request, "listings/roommates_hub.html", context)


@login_required
@require_POST
def delete_roommate_post(request, pk):
    if not request.user.is_student:
        return HttpResponseForbidden("Student access is required.")

    post = get_object_or_404(RoommatePost, pk=pk)
    current_group = roommate_group_for_user(request.user)
    if post.author_id != request.user.id and (current_group is None or post.group_id != current_group.pk):
        return HttpResponseForbidden("You cannot delete this post.")

    post.delete()
    messages.success(request, "Roommate post deleted.")
    return redirect(f"{reverse('roommates:hub')}?tab=groups")


@login_required
@require_POST
def remove_group_member(request, member_pk):
    if not request.user.is_student:
        raise Http404
    membership = get_object_or_404(RoommateGroupMembership, pk=member_pk)
    removed_name = membership.user.display_name
    try:
        remove_roommate_group_member(acting_user=request.user, membership=membership)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(request, f"Removed {removed_name} from the group.")
    return redirect(f"{reverse('roommates:hub')}?tab=groups")


@login_required
@require_POST
def send_group_invite(request, user_id):
    if not request.user.is_student:
        raise Http404
    user_model = get_user_model()
    invitee = get_object_or_404(
        user_model,
        id=user_id,
        role="student",
        is_active=True,
        profile_completed_at__isnull=False,
    )
    next_url = safe_next_url(request, request.POST.get("next"), f"{reverse('roommates:hub')}?tab=people")
    try:
        invite = create_group_invite(request.user, invitee)
    except ValidationError as exc:
        message = next(iter(exc.message_dict.values()))[0] if hasattr(exc, "message_dict") else exc.messages[0]
        messages.error(request, message)
    else:
        if invite.status == RoommateGroupInvite.STATUS_PENDING_APPROVAL:
            messages.success(request, "Invite proposed. Waiting on your group to approve.")
        else:
            messages.success(request, "Group invite sent.")
    return redirect(next_url)


@login_required
@require_POST
def toggle_favorite_roommate(request, user_id):
    if not request.user.is_student:
        raise Http404
    user_model = get_user_model()
    favorite_user = get_object_or_404(
        user_model,
        id=user_id,
        role="student",
        is_active=True,
        profile_completed_at__isnull=False,
    )
    next_url = safe_next_url(request, request.POST.get("next"), f"{reverse('roommates:hub')}?tab=people")

    if favorite_user.id == request.user.id:
        messages.error(request, "You cannot save your own profile.")
        return redirect(next_url)

    favorite = favorited_people_queryset(request.user).filter(favorite_user=favorite_user).first()
    if favorite is None:
        request.user.favorite_roommates.create(favorite_user=favorite_user)
        messages.success(request, f"Saved {favorite_user.display_name} to your favorites.")
    else:
        favorite.delete()
        messages.success(request, f"Removed {favorite_user.display_name} from your favorites.")
    return redirect(next_url)


@login_required
@require_POST
def approve_group_invite(request, invite_id):
    invite = get_object_or_404(RoommateGroupInvite, pk=invite_id)
    next_url = safe_next_url(request, request.POST.get("next"), f"{reverse('roommates:hub')}?tab=people")
    try:
        respond_to_invite_approval(invite, request.user, approve=True)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(request, "Invite approved.")
    return redirect(next_url)


@login_required
@require_POST
def reject_group_invite(request, invite_id):
    invite = get_object_or_404(RoommateGroupInvite, pk=invite_id)
    next_url = safe_next_url(request, request.POST.get("next"), f"{reverse('roommates:hub')}?tab=people")
    try:
        respond_to_invite_approval(invite, request.user, approve=False)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(request, "Invite declined.")
    return redirect(next_url)


@login_required
@require_POST
def accept_group_invite(request, invite_id):
    invite = get_object_or_404(RoommateGroupInvite, pk=invite_id)
    next_url = safe_next_url(request, request.POST.get("next"), reverse("communications:messages"))
    try:
        respond_to_group_invite(invite, request.user, accept=True)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(request, "You joined the group.")
    return redirect(next_url)


@login_required
@require_POST
def decline_group_invite(request, invite_id):
    invite = get_object_or_404(RoommateGroupInvite, pk=invite_id)
    next_url = safe_next_url(request, request.POST.get("next"), reverse("communications:messages"))
    try:
        respond_to_group_invite(invite, request.user, accept=False)
    except ValidationError as exc:
        messages.error(request, exc.messages[0])
    else:
        messages.success(request, "You declined the invite.")
    return redirect(next_url)


@login_required
@require_GET
def browse_redirect(request):
    base_url = reverse("roommates:hub")
    query = urlencode({"tab": "people"})
    return redirect(f"{base_url}?{query}")
