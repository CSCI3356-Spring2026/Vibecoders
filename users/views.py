import mimetypes
from pathlib import Path
from urllib.parse import urlencode

from allauth.socialaccount.providers.google import views as google_views
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import content_disposition_header
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_POST

from communications.forms import ConversationMessageForm
from communications.selectors import (
    accessible_conversations_for_user,
    conversation_summary_for_user,
    direct_conversation_between_users,
    direct_conversations_by_counterparty,
)
from core.rate_limits import consume_rate_limit, request_rate_limit_identifier
from core.utils import get_page, preserved_query_suffix, safe_next_url
from listings.selectors import active_roommate_post_for_user, with_feedback_summary

from .compatibility import (
    compatibility_highlights,
    compute_compatibility,
    compute_group_compatibility,
    group_compatibility_highlights,
)
from .forms import AdminProfileForm, AvatarUploadForm, GoogleLoginAcceptanceForm, StudentProfileForm, UserFileUploadForm
from .group_services import create_group_invite, respond_to_group_invite, respond_to_invite_approval
from .legal import (
    is_legal_review_required,
    set_pending_legal_acceptance,
)
from .models import AdminProfile, Role, RoommateGroupInvite, StudentProfile, UserFile
from .selectors import (
    accessible_user_files_queryset,
    active_roommate_group_for_user,
    pending_group_invite_approvals_for_user,
    pending_group_invites_for_user,
    roommate_candidate_results,
    roommate_group_memberships,
    roommate_group_profiles_for_user,
)
from .session_security import has_recent_auth

FILES_PER_PAGE = 12
POSTS_PER_PAGE = 12
ROOMMATE_RESULTS_PER_PAGE = 12
LOGIN_RATE_LIMIT_ERROR = "Too many sign-in attempts. Wait a few minutes and try again."
FILE_UPLOAD_RATE_LIMIT_ERROR = "Too many file uploads in a short time. Wait a few minutes and try again."


def _consume_login_rate_limit(request):
    return consume_rate_limit(
        scope="login-init",
        identifier=request_rate_limit_identifier(request),
        limit=getattr(settings, "LOGIN_INIT_RATE_LIMIT", 10),
        window_seconds=getattr(settings, "LOGIN_INIT_RATE_WINDOW_SECONDS", 300),
    )


def _consume_user_file_upload_rate_limit(user):
    user_id = getattr(user, "id", None)
    if not user_id:
        return False

    return consume_rate_limit(
        scope="user-file-upload",
        identifier=str(user_id),
        limit=getattr(settings, "USER_FILE_UPLOAD_RATE_LIMIT", 25),
        window_seconds=getattr(settings, "USER_FILE_UPLOAD_RATE_WINDOW_SECONDS", 300),
    )


def _files_redirect(request):
    preserved = {}
    for key in ("page", "q"):
        value = request.GET.get(key) or request.POST.get(key)
        if value:
            preserved[key] = value
    query_string = urlencode(preserved)
    if not query_string:
        return redirect("users:files")
    return redirect(f"{reverse('users:files')}?{query_string}")


def _workspace_summary(user):
    return {
        "listings_count": user.listings.count(),
        "files_count": user.files.count(),
        "can_browse_marketplace": user.can_browse_marketplace,
        "can_start_listing_conversations": user.can_start_listing_conversations,
        "has_listing_only_access": user.has_listing_only_access,
        **conversation_summary_for_user(user),
    }


def _add_form_validation_errors(form, exc, *, default_field):
    if hasattr(exc, "message_dict"):
        for field_name, messages_list in exc.message_dict.items():
            target_field = field_name if field_name in form.fields else default_field
            for message in messages_list:
                form.add_error(target_field, message)
        return

    for message in exc.messages:
        form.add_error(default_field, message)


def _selected_file_flags(user_file):
    if not user_file or not user_file.file:
        return False, False

    mime_type, _ = mimetypes.guess_type(user_file.file.name)
    if not mime_type:
        return False, False
    return mime_type.startswith("image/"), mime_type == "application/pdf"


def _accessible_user_file_or_404(user, file_id):
    return get_object_or_404(accessible_user_files_queryset(user), id=file_id)


def _open_user_file_or_404(user_file):
    if not user_file.file:
        raise Http404("File not found.")

    try:
        return user_file.file.open("rb")
    except FileNotFoundError as exc:
        raise Http404("File not found.") from exc


def _preview_content_type_or_404(user_file):
    content_type = mimetypes.guess_type(user_file.file.name)[0] or "application/octet-stream"
    if content_type == "application/pdf" or content_type.startswith("image/"):
        return content_type
    raise Http404("Preview not available.")


def _apply_private_file_response_headers(response):
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["Cross-Origin-Resource-Policy"] = "same-origin"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response


def login_page(request):
    if request.user.is_authenticated:
        return redirect("users:dashboard")
    legal_review_required = is_legal_review_required(request)
    next_url = safe_next_url(request, request.POST.get("next") or request.GET.get("next"), "")
    if request.method == "POST":
        if not _consume_login_rate_limit(request):
            messages.error(request, LOGIN_RATE_LIMIT_ERROR)
            form = GoogleLoginAcceptanceForm(request.POST, require_review=legal_review_required)
            return render(
                request,
                "users/login.html",
                {"login_form": form, "next_url": next_url, "legal_review_required": legal_review_required},
            )
        if not legal_review_required:
            return redirect(_google_login_url(request))
        form = GoogleLoginAcceptanceForm(request.POST, require_review=True)
        if form.is_valid():
            set_pending_legal_acceptance(request)
            return redirect(_google_login_url(request))
    else:
        form = GoogleLoginAcceptanceForm(require_review=legal_review_required)
    return render(
        request,
        "users/login.html",
        {"login_form": form, "next_url": next_url, "legal_review_required": legal_review_required},
    )


def google_login_gate(request):
    if not _consume_login_rate_limit(request):
        messages.error(request, LOGIN_RATE_LIMIT_ERROR)
        return redirect(_login_redirect_with_next(request))
    if is_legal_review_required(request):
        messages.error(request, "Review and accept the Terms of Service and Privacy Policy before continuing.")
        return redirect(_login_redirect_with_next(request))
    return google_views.oauth2_login(request)


def _google_login_url(request):
    next_url = safe_next_url(request, request.POST.get("next") or request.GET.get("next"), "")
    base_url = reverse("google_login")
    if not next_url:
        return base_url
    return f"{base_url}?{urlencode({'next': next_url})}"


def _login_redirect_with_next(request):
    next_url = safe_next_url(request, request.GET.get("next"), "")
    base_url = reverse("users:login")
    if not next_url:
        return base_url
    return f"{base_url}?{urlencode({'next': next_url})}"


@login_required
def profile(request):
    return redirect("users:dashboard")


def _dashboard_context(user):
    recent_conversations = list(accessible_conversations_for_user(user)[:5])
    for conversation in recent_conversations:
        conversation.ui_counterparty = conversation.counterparty_for(user)
        conversation.ui_has_unread = conversation.has_unread_for(user)
        conversation.ui_context_title = conversation.context_title_for(user)
    return {
        **_workspace_summary(user),
        "recent_listings": user.listings.with_related()[:3],
        "recent_files": user.files.all()[:5],
        "recent_conversations": recent_conversations,
    }


@login_required
def dashboard(request):
    return render(request, "users/dashboard.html", _dashboard_context(request.user))


@login_required
def profile_setup(request):
    user = request.user
    next_url = safe_next_url(request, request.POST.get("next") or request.GET.get("next"), "")
    profile_needs_completion = settings.PROFILE_COMPLETION_REQUIRED and not user.profile_completed_at
    if user.role == Role.STUDENT:
        profile, _ = StudentProfile.objects.get_or_create(user=user)
        form_class = StudentProfileForm
        role_label = "Student"
        profile_title = "Student profile"
        profile_subtitle = "These details power roommate matching and your public profile."
        is_student_profile = True
    elif user.role in {Role.ADMIN, Role.REALTOR}:
        profile, _ = AdminProfile.objects.get_or_create(user=user)
        form_class = AdminProfileForm
        role_label = "Admin" if user.role == Role.ADMIN else "Realtor"
        profile_title = "Admin profile" if user.role == Role.ADMIN else "Listing profile"
        profile_subtitle = "Keep the public details for this account clean and current."
        is_student_profile = False
    else:
        messages.info(request, "Profile details are only available for student or admin accounts.")
        return redirect("users:dashboard")

    if request.method == "POST":
        form = form_class(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            if not user.profile_completed_at:
                user.profile_completed_at = timezone.now()
                user.save(update_fields={"profile_completed_at"})
            messages.success(request, "Profile completed." if profile_needs_completion else "Profile updated.")
            if next_url:
                return redirect(next_url)
            if profile_needs_completion:
                return redirect("users:dashboard")
            return redirect("users:profile_setup")
    else:
        form = form_class(instance=profile)

    context = {
        "form": form,
        "role_label": role_label,
        "profile_title": profile_title,
        "profile_subtitle": profile_subtitle,
        "is_student_profile": is_student_profile,
        "next_url": next_url,
        "profile_needs_completion": profile_needs_completion,
    }
    return render(request, "users/profile_form.html", context)


@login_required
def posts(request):
    listings_qs = (
        with_feedback_summary(request.user.listings.with_related())
        .annotate(
            conversation_count=Count(
                "conversations",
                filter=Q(conversations__owner_deleted_at__isnull=True),
                distinct=True,
            )
        )
        .order_by("-created_at")
    )
    listings_page = get_page(listings_qs, request.GET.get("page"), POSTS_PER_PAGE)
    context = {
        **_workspace_summary(request.user),
        "listings": listings_page,
        "listings_total": listings_page.paginator.count,
        "pagination_query": preserved_query_suffix(request.GET, "page"),
    }
    return render(request, "users/posts.html", context)


@login_required
def files(request):
    query = request.GET.get("q", "").strip()
    selected_id = request.GET.get("file")

    if request.method == "POST":
        form = UserFileUploadForm(request.POST, request.FILES)
        if not _consume_user_file_upload_rate_limit(request.user):
            form.add_error("file", FILE_UPLOAD_RATE_LIMIT_ERROR)
        elif form.is_valid():
            user_file = form.save(commit=False)
            user_file.owner = request.user
            if not user_file.title:
                uploaded_name = Path(user_file.file.name).name
                user_file.title = uploaded_name
            try:
                user_file.save()
            except ValidationError as exc:
                _add_form_validation_errors(form, exc, default_field="file")
            else:
                return redirect("users:files")
    else:
        form = UserFileUploadForm()

    files_qs = accessible_user_files_queryset(request.user).filter(owner=request.user)
    if query:
        files_qs = files_qs.filter(title__icontains=query)

    files_page = get_page(files_qs, request.GET.get("page"), FILES_PER_PAGE)

    selected_file = None
    if selected_id:
        selected_file = get_object_or_404(files_qs, id=selected_id)
    else:
        selected_file = files_page.object_list.first()

    selected_is_image, selected_is_pdf = _selected_file_flags(selected_file)

    context = {
        "form": form,
        "files": files_page,
        "files_total": files_page.paginator.count,
        "pagination_query": preserved_query_suffix(request.GET, "page", "file"),
        "query": query,
        "selected_file": selected_file,
        "selected_is_image": selected_is_image,
        "selected_is_pdf": selected_is_pdf,
    }
    return render(request, "users/files.html", context)


@login_required
@require_GET
@xframe_options_sameorigin
def file_preview(request, file_id):
    user_file = _accessible_user_file_or_404(request.user, file_id)
    file_handle = _open_user_file_or_404(user_file)
    content_type = _preview_content_type_or_404(user_file)
    filename = Path(user_file.file.name).name
    response = FileResponse(file_handle, content_type=content_type)
    response["Content-Disposition"] = content_disposition_header(False, filename)
    return _apply_private_file_response_headers(response)


@login_required
@require_GET
def file_download(request, file_id):
    user_file = _accessible_user_file_or_404(request.user, file_id)
    file_handle = _open_user_file_or_404(user_file)
    filename = Path(user_file.file.name).name
    response = FileResponse(
        file_handle,
        as_attachment=True,
        filename=filename,
    )
    response["Content-Disposition"] = content_disposition_header(True, filename)
    return _apply_private_file_response_headers(response)


@login_required
@require_POST
def delete_file(request, file_id):
    user_file = get_object_or_404(UserFile, id=file_id, owner=request.user)
    user_file.delete()
    return _files_redirect(request)


@login_required
@require_POST
def delete_account(request):
    if not has_recent_auth(request):
        messages.error(request, "Sign in again before deleting your account.")
        return redirect("users:dashboard")
    user = request.user
    if (
        user.role == Role.ADMIN
        and not user.__class__._default_manager.exclude(pk=user.pk)
        .filter(
            role=Role.ADMIN,
            is_active=True,
        )
        .exists()
    ):
        messages.error(request, "You cannot delete the last active admin account.")
        return redirect("users:dashboard")
    logout(request)
    user.delete()
    messages.success(request, "Account deleted.")
    return redirect("core:landing")


@login_required
@require_POST
def upload_avatar(request):
    form = AvatarUploadForm(request.POST, request.FILES)
    if form.is_valid():
        user = request.user
        if user.uploaded_avatar:
            user.uploaded_avatar.delete(save=False)
        user.uploaded_avatar = form.cleaned_data["avatar"]
        user.save(update_fields=["uploaded_avatar"])
        messages.success(request, "Profile photo updated.")
    else:
        for error_list in form.errors.values():
            for error in error_list:
                messages.error(request, error)
    return redirect("users:profile_setup")


@login_required
@require_GET
def browse_roommates(request):
    if not request.user.is_student:
        raise Http404
    query = request.GET.get("q", "").strip()
    gender_filter = request.GET.get("gender", "").strip()
    smoke_filter = request.GET.get("smoke", "").strip()
    pets_filter = request.GET.get("pets", "").strip()
    min_score_raw = request.GET.get("min_score", "").strip()
    min_score = int(min_score_raw) if min_score_raw.isdigit() else None

    my_profile = getattr(request.user, "student_profile", None)
    active_group = active_roommate_group_for_user(request.user)
    group_memberships = roommate_group_memberships(active_group) if active_group else []
    group_member_ids = {membership.user_id for membership in group_memberships}

    results = roommate_candidate_results(
        request.user,
        query=query,
        gender_filter=gender_filter,
        smoke_filter=smoke_filter,
        pets_filter=pets_filter,
        min_score=min_score,
    )
    for result in results:
        result["is_in_group"] = result["user"].id in group_member_ids

    results_page = get_page(results, request.GET.get("page"), ROOMMATE_RESULTS_PER_PAGE)
    page_results = list(results_page.object_list)

    # Look up existing direct conversations in one query
    if request.user.can_use_roommate_matching and page_results:
        existing_convos = direct_conversations_by_counterparty(request.user, [r["user"] for r in page_results])
    else:
        existing_convos = {}

    existing_invites = RoommateGroupInvite.objects.filter(
        inviter=request.user,
        invitee__in=[result["user"] for result in page_results],
        status__in=[
            RoommateGroupInvite.STATUS_PENDING_APPROVAL,
            RoommateGroupInvite.STATUS_PENDING_INVITEE,
        ],
    ).values_list("invitee_id", "status")
    invite_status_map = {invitee_id: status for invitee_id, status in existing_invites}

    for result in page_results:
        result["existing_convo"] = existing_convos.get(result["user"].id)
        result["invite_status"] = invite_status_map.get(result["user"].id)

    filters_active = any([query, gender_filter, smoke_filter, pets_filter, min_score is not None])

    return render(
        request,
        "users/browse_roommates.html",
        {
            "results": results_page,
            "results_total": results_page.paginator.count,
            "pagination_query": preserved_query_suffix(request.GET, "page"),
            "query": query,
            "gender_filter": gender_filter,
            "smoke_filter": smoke_filter,
            "pets_filter": pets_filter,
            "min_score": min_score_raw,
            "filters_active": filters_active,
            "has_my_profile": my_profile is not None,
            "can_message": request.user.can_use_roommate_matching,
            "active_group": active_group,
            "group_memberships": group_memberships,
            "pending_group_approvals": pending_group_invite_approvals_for_user(request.user),
            "pending_group_invites": pending_group_invites_for_user(request.user),
        },
    )


@login_required
@require_GET
def public_profile(request, user_id):
    if not request.user.is_student:
        raise Http404
    User = get_user_model()
    target = get_object_or_404(User, id=user_id, role=Role.STUDENT, is_active=True, profile_completed_at__isnull=False)
    their_profile = getattr(target, "student_profile", None)
    if their_profile is None:
        raise Http404
    my_profile = getattr(request.user, "student_profile", None)
    group_profiles = roommate_group_profiles_for_user(request.user)
    if group_profiles:
        score = compute_group_compatibility(group_profiles, their_profile) if their_profile else None
        highlights = group_compatibility_highlights(group_profiles, their_profile)
    else:
        score = compute_compatibility(my_profile, their_profile) if my_profile else None
        highlights = compatibility_highlights(my_profile, their_profile)
    existing_direct_conversation = None
    direct_message_form = None
    if request.user.id != target.id and request.user.can_use_roommate_matching:
        existing_direct_conversation = direct_conversation_between_users(request.user, target)
    has_active_roommate_post = active_roommate_post_for_user(target) is not None
    can_message_user = (
        request.user.id != target.id and request.user.can_use_roommate_matching and has_active_roommate_post
    )
    if can_message_user:
        direct_message_form = ConversationMessageForm(
            placeholder="Introduce yourself and compare housing plans.",
        )
    active_group = active_roommate_group_for_user(request.user)
    group_member_ids = set()
    if active_group:
        group_member_ids = {membership.user_id for membership in roommate_group_memberships(active_group)}
    group_member_count = len(group_member_ids) if group_member_ids else (1 if my_profile else 0)
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
    return render(
        request,
        "users/public_profile.html",
        {
            "target": target,
            "their_profile": their_profile,
            "score": score,
            "compatibility_highlights": highlights,
            "can_message_user": can_message_user,
            "has_active_roommate_post": has_active_roommate_post,
            "existing_direct_conversation": existing_direct_conversation,
            "direct_message_form": direct_message_form,
            "active_group": active_group,
            "invite_status": invite_status,
            "is_in_group": target.id in group_member_ids,
            "group_member_count": group_member_count,
        },
    )


@login_required
@require_POST
def send_group_invite(request, user_id):
    if not request.user.is_student:
        raise Http404
    User = get_user_model()
    invitee = get_object_or_404(
        User,
        id=user_id,
        role=Role.STUDENT,
        is_active=True,
        profile_completed_at__isnull=False,
    )
    next_url = safe_next_url(request, request.POST.get("next"), reverse("users:browse_roommates"))
    try:
        invite = create_group_invite(request.user, invitee)
    except ValidationError as exc:
        if hasattr(exc, "message_dict"):
            message = next(iter(exc.message_dict.values()))[0]
        else:
            message = exc.messages[0]
        messages.error(request, message)
    else:
        if invite.status == RoommateGroupInvite.STATUS_PENDING_APPROVAL:
            messages.success(request, "Invite proposed. Waiting on your group to approve.")
        else:
            messages.success(request, "Group invite sent.")
    return redirect(next_url)


@login_required
@require_POST
def approve_group_invite(request, invite_id):
    invite = get_object_or_404(RoommateGroupInvite, pk=invite_id)
    next_url = safe_next_url(request, request.POST.get("next"), reverse("users:browse_roommates"))
    try:
        respond_to_invite_approval(invite, request.user, approve=True)
    except ValidationError as exc:
        message = exc.messages[0]
        messages.error(request, message)
    else:
        messages.success(request, "Invite approved.")
    return redirect(next_url)


@login_required
@require_POST
def reject_group_invite(request, invite_id):
    invite = get_object_or_404(RoommateGroupInvite, pk=invite_id)
    next_url = safe_next_url(request, request.POST.get("next"), reverse("users:browse_roommates"))
    try:
        respond_to_invite_approval(invite, request.user, approve=False)
    except ValidationError as exc:
        message = exc.messages[0]
        messages.error(request, message)
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
        message = exc.messages[0]
        messages.error(request, message)
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
        message = exc.messages[0]
        messages.error(request, message)
    else:
        messages.success(request, "You declined the invite.")
    return redirect(next_url)
