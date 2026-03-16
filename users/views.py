from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
import mimetypes
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.utils import get_page, preserved_query_suffix
from listings.models import Listing

from .forms import UserFileUploadForm
from .models import UserFile

FILES_PER_PAGE = 12


def _files_redirect(request):
    query_string = request.GET.urlencode()
    if not query_string:
        return redirect("users:files")
    return redirect(f"{reverse('users:files')}?{query_string}")


def _workspace_summary(user):
    return {
        "listings_count": user.listings.count(),
        "files_count": user.files.count(),
    }


def _selected_file_flags(user_file):
    if not user_file or not user_file.file:
        return False, False

    mime_type, _ = mimetypes.guess_type(user_file.file.name)
    if not mime_type:
        return False, False
    return mime_type.startswith("image/"), mime_type == "application/pdf"


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
        "recent_listings": request.user.listings.all()[:3],
        "recent_files": request.user.files.all()[:5],
    }
    return render(request, "users/dashboard.html", context)


@login_required
def posts(request):
    listings = request.user.listings.all().order_by("-created_at")
    return render(request, "users/posts.html", {"listings": listings})

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

    files_qs = UserFile.objects.filter(owner=request.user)
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
    status_values = {status for status, _ in Listing.STATUS_CHOICES}

    listings_qs = Listing.objects.with_related()
    if query:
        listings_qs = listings_qs.filter(
            Q(title__icontains=query)
            | Q(address__icontains=query)
            | Q(owner__email__icontains=query)
            | Q(owner__username__icontains=query)
        )
    if selected_status in status_values:
        listings_qs = listings_qs.filter(status=selected_status)

    context = {
        "listings": listings_qs,
        "total_listings": Listing.objects.count(),
        "pending_listings": Listing.objects.filter(status="PENDING").count(),
        "approved_listings": Listing.objects.filter(status="AVAILABLE").count(),
        "reports_count": 0,
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
    status_values = {status for status, _ in Listing.STATUS_CHOICES}

    listings_qs = Listing.objects.with_related()
    if query:
        listings_qs = listings_qs.filter(
            Q(title__icontains=query)
            | Q(address__icontains=query)
            | Q(owner__email__icontains=query)
            | Q(owner__username__icontains=query)
        )
    if selected_status in status_values:
        listings_qs = listings_qs.filter(status=selected_status)

    context = {
        "listings": listings_qs,
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
    redirect_to = request.POST.get("next") or reverse("users:admin_listings")
    return redirect(redirect_to)


@login_required
def admin_users(request):
    guard_response = _admin_guard(request)
    if guard_response:
        return guard_response

    query = request.GET.get("q", "").strip()
    selected_role = request.GET.get("role", "").strip()
    selected_active = request.GET.get("active", "").strip()
    role_values = {"student", "admin"}

    User = get_user_model()
    users_qs = User.objects.all().order_by("username")

    if query:
        users_qs = users_qs.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )

    if selected_role in role_values:
        users_qs = users_qs.filter(role=selected_role)

    if selected_active in {"active", "inactive"}:
        users_qs = users_qs.filter(is_active=(selected_active == "active"))

    context = {
        "users": users_qs,
        "query": query,
        "selected_role": selected_role,
        "selected_active": selected_active,
    }
    return render(request, "users/admin_users.html", context)


@login_required
def admin_user_detail(request, user_id):
    guard_response = _admin_guard(request)
    if guard_response:
        return guard_response

    User = get_user_model()
    user_obj = get_object_or_404(User, id=user_id)
    listings = user_obj.listings.with_related()
    files = user_obj.files.all()

    context = {
        "managed_user": user_obj,
        "managed_listings": listings,
        "managed_files": files,
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

    role = request.POST.get("role", "").strip()
    if role not in {"student", "admin"}:
        return HttpResponseForbidden("Invalid role.")

    user_obj.role = role
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
    user_file.file.delete(save=False)
    user_file.delete()
    return _files_redirect(request)
