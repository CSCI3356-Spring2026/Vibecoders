from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render


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
def posts(request):
    listings = request.user.listings.all().order_by("-created_at")
    return render(request, "users/posts.html", {"listings": listings})
