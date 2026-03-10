from django.shortcuts import render


# Minimal current views
def login_page(request):
    return render(request, "users/login.html")


def profile(request):
    return render(request, "users/profile.html")


def dashboard(request):
    return render(request, "users/dashboard.html")


# TODO: Add actual logic, templates, and admin only views
