import mimetypes
from pathlib import Path
from urllib.parse import urlencode

from allauth.socialaccount.providers.google import views as google_views
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import content_disposition_header
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_POST

from communications.selectors import (
    accessible_conversations_for_user,
    conversation_summary_for_user,
)
from core.media import normalize_public_media_subpath, public_file_response
from core.rate_limits import consume_rate_limit, request_rate_limit_identifier
from core.utils import get_page, preserved_query_suffix, safe_next_url
from listings.selectors import with_feedback_summary
from roommates import views as roommate_views

from .admin_state import may_delete
from .forms import AdminProfileForm, AvatarUploadForm, GoogleLoginAcceptanceForm, StudentProfileForm, UserFileUploadForm
from .legal import (
    is_legal_review_required,
    set_pending_legal_acceptance,
)
from .models import AdminProfile, CustomUser, Role, StudentProfile, UserFile
from .profile_integrity import mark_profile_completed_now, profile_satisfies_completion_requirements
from .selectors import (
    accessible_user_files_queryset,
    favorited_people_queryset,
)
from .session_security import has_recent_auth

FILES_PER_PAGE = 12
POSTS_PER_PAGE = 12
FAVORITE_PEOPLE_PER_PAGE = 12
ROOMMATE_RESULTS_PER_PAGE = 12
LOGIN_RATE_LIMIT_ERROR = "Too many sign-in attempts. Wait a few minutes and try again."
FILE_UPLOAD_RATE_LIMIT_ERROR = "Too many file uploads in a short time. Wait a few minutes and try again."
LIFESTYLE_MATCH_STRONG = "lifestyle-match-strong"
LIFESTYLE_MATCH_GOOD = "lifestyle-match-good"
LIFESTYLE_MATCH_MID = "lifestyle-match-mid"
LIFESTYLE_MATCH_LOW = "lifestyle-match-low"
LIFESTYLE_MATCH_POOR = "lifestyle-match-poor"


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
    favorite_people_count = favorited_people_queryset(user).count() if getattr(user, "is_student", False) else 0
    return {
        "listings_count": user.listings.count(),
        "files_count": user.files.count(),
        "favorite_people_count": favorite_people_count,
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


def _lifestyle_match_class_for_diff(diff):
    if diff is None:
        return ""
    if diff <= 0:
        return LIFESTYLE_MATCH_STRONG
    if diff == 1:
        return LIFESTYLE_MATCH_GOOD
    if diff == 2:
        return LIFESTYLE_MATCH_MID
    if diff == 3:
        return LIFESTYLE_MATCH_LOW
    return LIFESTYLE_MATCH_POOR


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
        classes[field_name] = LIFESTYLE_MATCH_STRONG if matches else LIFESTYLE_MATCH_POOR

    return classes


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


@require_GET
def public_avatar(request, path):
    image_name = f"avatars/{normalize_public_media_subpath(path)}"
    user = get_object_or_404(CustomUser.objects.filter(uploaded_avatar=image_name))
    return public_file_response(user.uploaded_avatar, cache_seconds=300)


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
    recent_favorite_people = list(favorited_people_queryset(user)[:5]) if getattr(user, "is_student", False) else []
    return {
        **_workspace_summary(user),
        "recent_listings": user.listings.with_related()[:3],
        "recent_files": user.files.all()[:5],
        "recent_conversations": recent_conversations,
        "recent_favorite_people": recent_favorite_people,
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
            if profile_satisfies_completion_requirements(user):
                mark_profile_completed_now(user)
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
def favorite_people(request):
    return redirect(f"{reverse('roommates:hub')}?tab=people&saved=1")


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
    if not may_delete(user):
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
    query = request.GET.copy()
    query["tab"] = "people"
    return redirect(f"{reverse('roommates:hub')}?{query.urlencode()}")


@login_required
@require_GET
def public_profile(request, user_id):
    return roommate_views.public_profile(request, user_id)


@login_required
@require_POST
def send_group_invite(request, user_id):
    return roommate_views.send_group_invite(request, user_id)


@login_required
@require_POST
def toggle_favorite_roommate(request, user_id):
    return roommate_views.toggle_favorite_roommate(request, user_id)


@login_required
@require_POST
def approve_group_invite(request, invite_id):
    return roommate_views.approve_group_invite(request, invite_id)


@login_required
@require_POST
def reject_group_invite(request, invite_id):
    return roommate_views.reject_group_invite(request, invite_id)


@login_required
@require_POST
def accept_group_invite(request, invite_id):
    return roommate_views.accept_group_invite(request, invite_id)


@login_required
@require_POST
def decline_group_invite(request, invite_id):
    return roommate_views.decline_group_invite(request, invite_id)
