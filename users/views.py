import mimetypes
from pathlib import Path
from urllib.parse import urlencode

from allauth.socialaccount.providers.google import views as google_views
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_POST

from communications.selectors import accessible_conversations_for_user, conversation_summary_for_user
from core.utils import get_page, preserved_query_suffix, safe_next_url

from .forms import GoogleLoginAcceptanceForm, UserFileUploadForm
from .legal import has_current_legal_acceptance, set_pending_legal_acceptance
from .models import UserFile
from .selectors import accessible_user_files_queryset

FILES_PER_PAGE = 12
POSTS_PER_PAGE = 12


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
        "student_email_domains": ", ".join(sorted(user.student_email_domains())),
        **conversation_summary_for_user(user),
    }


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


def login_page(request):
    if request.user.is_authenticated:
        return redirect("users:dashboard")
    next_url = safe_next_url(request, request.POST.get("next") or request.GET.get("next"), "")
    if request.method == "POST":
        is_legacy_login_post = request.path == reverse("account_login")
        has_legal_fields = "accept_terms" in request.POST or "accept_privacy" in request.POST
        if is_legacy_login_post and not has_legal_fields:
            return redirect("users:login")
        form = GoogleLoginAcceptanceForm(request.POST)
        if form.is_valid():
            set_pending_legal_acceptance(request)
            return redirect(_google_login_url(request))
    else:
        form = GoogleLoginAcceptanceForm()
    return render(request, "users/login.html", {"login_form": form, "next_url": next_url})


def google_login_gate(request):
    if not has_current_legal_acceptance(request):
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
    return render(request, "users/profile.html", _workspace_summary(request.user))


@login_required
def dashboard(request):
    recent_conversations = list(accessible_conversations_for_user(request.user)[:5])
    for conversation in recent_conversations:
        conversation.ui_counterparty = conversation.counterparty_for(request.user)
        conversation.ui_has_unread = conversation.has_unread_for(request.user)
    context = {
        **_workspace_summary(request.user),
        "recent_listings": request.user.listings.with_related()[:3],
        "recent_files": request.user.files.all()[:5],
        "recent_conversations": recent_conversations,
    }
    return render(request, "users/dashboard.html", context)


@login_required
def posts(request):
    listings_qs = (
        request.user.listings.with_related()
        .annotate(
            conversation_count=Count(
                "conversations",
                filter=Q(conversations__owner_deleted_at__isnull=True),
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
        if form.is_valid():
            user_file = form.save(commit=False)
            user_file.owner = request.user
            if not user_file.title:
                uploaded_name = Path(user_file.file.name).name
                user_file.title = uploaded_name
            user_file.save()
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
    response = FileResponse(file_handle, content_type=content_type)
    response["Content-Disposition"] = f'inline; filename="{Path(user_file.file.name).name}"'
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@require_GET
def file_download(request, file_id):
    user_file = _accessible_user_file_or_404(request.user, file_id)
    file_handle = _open_user_file_or_404(user_file)
    response = FileResponse(
        file_handle,
        as_attachment=True,
        filename=Path(user_file.file.name).name,
    )
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@require_POST
def delete_file(request, file_id):
    user_file = get_object_or_404(UserFile, id=file_id, owner=request.user)
    user_file.delete()
    return _files_redirect(request)


@login_required
@require_POST
def delete_account(request):
    user = request.user
    logout(request)
    user.delete()
    messages.success(request, "Account deleted.")
    return redirect("core:landing")
