import mimetypes
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_POST

from core.utils import get_page, preserved_query_suffix, safe_next_url
from listings.models import Listing, ListingInquiry

from .forms import UserFileUploadForm
from .models import Role, UserFile
from .selectors import accessible_user_files_queryset, admin_listings_queryset, admin_users_queryset

FILES_PER_PAGE = 12
POSTS_PER_PAGE = 12
ADMIN_LISTINGS_PER_PAGE = 20
ADMIN_USERS_PER_PAGE = 20
ADMIN_USER_DETAIL_PREVIEW_LIMIT = 15


def _files_redirect(request):
    query_string = request.GET.urlencode()
    if not query_string:
        return redirect("users:files")
    return redirect(f"{reverse('users:files')}?{query_string}")


def _workspace_summary(user):
    return {
        "listings_count": user.listings.count(),
        "files_count": user.files.count(),
        "sent_inquiries_count": user.sent_inquiries.count(),
        "incoming_inquiries_count": ListingInquiry.objects.filter(listing__owner=user).count(),
        "can_browse_marketplace": user.can_browse_marketplace,
        "can_inquire_on_listings": user.can_inquire_on_listings,
        "has_listing_only_access": user.has_listing_only_access,
        "student_email_domains": ", ".join(sorted(user.student_email_domains())),
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
    if request.method == "POST":
        return redirect("users:login")
    return render(request, "users/login.html")


@login_required
def profile(request):
    return render(request, "users/profile.html", _workspace_summary(request.user))


@login_required
def dashboard(request):
    context = {
        **_workspace_summary(request.user),
        "recent_listings": request.user.listings.with_related()[:3],
        "recent_files": request.user.files.all()[:5],
        "recent_inquiries": ListingInquiry.objects.filter(listing__owner=request.user).select_related(
            "listing", "sender"
        )[:5],
    }
    return render(request, "users/dashboard.html", context)


@login_required
def posts(request):
    listings_qs = (
        request.user.listings.with_related().annotate(inquiry_count=Count("inquiries")).order_by("-created_at")
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


def _admin_guard(request):
    if not request.user.is_bc_admin:
        return HttpResponseForbidden("Admin access required.")
    return None


@login_required
def admin_dashboard(request):
    guard_response = _admin_guard(request)
    if guard_response:
        return guard_response

    query = request.GET.get("q", "").strip()
    selected_status = request.GET.get("status", "").strip()
    listings_qs = admin_listings_queryset(query=query, selected_status=selected_status)

    User = get_user_model()
    filtered_listings_count = listings_qs.count()
    context = {
        "listings": listings_qs[:10],
        "filtered_listings_count": filtered_listings_count,
        "total_listings": Listing.objects.count(),
        "pending_listings": Listing.objects.filter(status="PENDING").count(),
        "approved_listings": Listing.objects.filter(status="AVAILABLE").count(),
        "student_users": User.objects.filter(role=Role.STUDENT).count(),
        "realtor_users": User.objects.filter(role=Role.REALTOR).count(),
        "admin_users_total": User.objects.filter(role=Role.ADMIN).count(),
        "total_inquiries": ListingInquiry.objects.count(),
        "query": query,
        "selected_status": selected_status,
        "status_options": Listing.STATUS_CHOICES,
    }
    return render(request, "users/admin_dashboard.html", context)


@login_required
def admin_listings(request):
    guard_response = _admin_guard(request)
    if guard_response:
        return guard_response

    query = request.GET.get("q", "").strip()
    selected_status = request.GET.get("status", "").strip()
    listings_qs = admin_listings_queryset(query=query, selected_status=selected_status)

    listings_page = get_page(listings_qs, request.GET.get("page"), ADMIN_LISTINGS_PER_PAGE)

    context = {
        "listings": listings_page,
        "listings_total": listings_page.paginator.count,
        "pagination_query": preserved_query_suffix(request.GET, "page"),
        "query": query,
        "selected_status": selected_status,
        "status_options": Listing.STATUS_CHOICES,
    }
    return render(request, "users/admin_listings.html", context)


@login_required
@require_POST
def admin_delete_listing(request, listing_id):
    guard_response = _admin_guard(request)
    if guard_response:
        return guard_response

    listing = get_object_or_404(Listing, id=listing_id)
    listing.delete()
    redirect_to = safe_next_url(
        request,
        request.POST.get("next"),
        reverse("users:admin_listings"),
    )
    return redirect(redirect_to)


@login_required
def admin_users(request):
    guard_response = _admin_guard(request)
    if guard_response:
        return guard_response

    query = request.GET.get("q", "").strip()
    selected_role = request.GET.get("role", "").strip()
    selected_active = request.GET.get("active", "").strip()
    users_qs = admin_users_queryset(
        query=query,
        selected_role=selected_role,
        selected_active=selected_active,
    )

    users_page = get_page(users_qs, request.GET.get("page"), ADMIN_USERS_PER_PAGE)

    context = {
        "users": users_page,
        "users_total": users_page.paginator.count,
        "pagination_query": preserved_query_suffix(request.GET, "page"),
        "query": query,
        "selected_role": selected_role,
        "selected_active": selected_active,
        "role_options": Role.choices,
    }
    return render(request, "users/admin_users.html", context)


@login_required
def admin_user_detail(request, user_id):
    guard_response = _admin_guard(request)
    if guard_response:
        return guard_response

    User = get_user_model()
    user_obj = get_object_or_404(User, id=user_id)
    listings_qs = user_obj.listings.with_related()
    files_qs = user_obj.files.all()
    inquiries_qs = ListingInquiry.objects.filter(listing__owner=user_obj).select_related("listing", "sender")

    context = {
        "managed_user": user_obj,
        "managed_listings": listings_qs[:ADMIN_USER_DETAIL_PREVIEW_LIMIT],
        "managed_files": files_qs[:ADMIN_USER_DETAIL_PREVIEW_LIMIT],
        "managed_inquiries": inquiries_qs[:ADMIN_USER_DETAIL_PREVIEW_LIMIT],
        "managed_listings_count": listings_qs.count(),
        "managed_files_count": files_qs.count(),
        "managed_inquiries_count": inquiries_qs.count(),
        "activity_preview_limit": ADMIN_USER_DETAIL_PREVIEW_LIMIT,
    }
    return render(request, "users/admin_user_detail.html", context)


@login_required
@require_POST
def admin_set_role(request, user_id):
    guard_response = _admin_guard(request)
    if guard_response:
        return guard_response

    User = get_user_model()
    user_obj = get_object_or_404(User, id=user_id)
    if user_obj.id == request.user.id:
        return HttpResponseForbidden("You cannot change your own role.")

    action = request.POST.get("action", "").strip()
    if action == "grant_admin":
        user_obj.set_admin_access(True)
    elif action == "restore_default":
        user_obj.set_admin_access(False)
    else:
        return HttpResponseForbidden("Invalid role action.")

    user_obj.save(update_fields=["role"])
    return redirect("users:admin_users")


@login_required
@require_POST
def admin_toggle_active(request, user_id):
    guard_response = _admin_guard(request)
    if guard_response:
        return guard_response

    User = get_user_model()
    user_obj = get_object_or_404(User, id=user_id)
    if user_obj.id == request.user.id:
        return HttpResponseForbidden("You cannot deactivate your own account.")

    user_obj.is_active = not user_obj.is_active
    user_obj.save(update_fields=["is_active"])
    return redirect("users:admin_users")


@login_required
@require_POST
def delete_file(request, file_id):
    user_file = get_object_or_404(UserFile, id=file_id, owner=request.user)
    user_file.delete()
    return _files_redirect(request)
