import mimetypes
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.utils import get_page, preserved_query_suffix

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


@login_required
@require_POST
def delete_file(request, file_id):
    user_file = get_object_or_404(UserFile, id=file_id, owner=request.user)
    user_file.file.delete(save=False)
    user_file.delete()
    return _files_redirect(request)
