from django.urls import path

from . import views

app_name = "users"

urlpatterns = [
    path("login/", views.login_page, name="login"),
    path("profile/", views.profile, name="profile"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("posts/", views.posts, name="posts"),
]
