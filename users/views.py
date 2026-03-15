from django.shortcuts import redirect, render


# Minimal current views
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


# TODO: Add actual logic, templates, and admin only views
