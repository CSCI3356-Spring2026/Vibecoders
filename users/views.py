<<<<<<< HEAD
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
=======
import mimetypes
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from users.forms import UserFileUploadForm
from users.models import UserFile
>>>>>>> 4dc2daa (documents feature)


def login_page(request):
    if request.user.is_authenticated:
        return redirect("core:landing")
    if request.method == "POST":
        return redirect("users:login")
    return render(request, "users/login.html")


def profile(request):
    return render(request, "users/profile.html")


def dashboard(request):
    return render(request, "users/dashboard.html")


@login_required
<<<<<<< HEAD
def posts(request):
    listings = request.user.listings.all().order_by("-created_at")
    return render(request, "users/posts.html", {"listings": listings})
=======
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

    selected_file = None
    if selected_id:
        selected_file = get_object_or_404(files_qs, id=selected_id)
    else:
        selected_file = files_qs.first()

    selected_is_image = False
    selected_is_pdf = False
    if selected_file and selected_file.file:
        mime_type, _ = mimetypes.guess_type(selected_file.file.name)
        if mime_type:
            selected_is_image = mime_type.startswith("image/")
            selected_is_pdf = mime_type == "application/pdf"

    context = {
        "form": form,
        "files": files_qs,
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
    return redirect("users:files")
>>>>>>> 4dc2daa (documents feature)
