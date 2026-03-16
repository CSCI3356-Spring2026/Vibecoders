from django.urls import path

from . import views

app_name = "users"

urlpatterns = [
    path("login/", views.login_page, name="login"),
    path("profile/", views.profile, name="profile"),
    path("dashboard/", views.dashboard, name="dashboard"),
<<<<<<< HEAD
    path("posts/", views.posts, name="posts"),
=======
    path("files/", views.files, name="files"),
    path("files/<int:file_id>/delete/", views.delete_file, name="file_delete"),
>>>>>>> 4dc2daa (documents feature)
]
