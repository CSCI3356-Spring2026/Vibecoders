from django.urls import path

from . import views

app_name = "users"

urlpatterns = [
    # Minimal current URLs
    path("login/", views.login_page, name="login"),
    path("profile/", views.profile, name="profile"),
    path("dashboard/", views.dashboard, name="dashboard"),
    # TODO: Add logic, templates, and admin only urls
]
