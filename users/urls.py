from django.urls import path

from . import admin_views, views

app_name = "users"

urlpatterns = [
    path("login/", views.login_page, name="login"),
    path("profile/", views.profile, name="profile"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("admin-dashboard/", admin_views.admin_dashboard, name="admin_dashboard"),
    path("admin-listings/", admin_views.admin_listings, name="admin_listings"),
    path("admin-listings/<int:listing_id>/delete/", admin_views.admin_delete_listing, name="admin_delete_listing"),
    path("admin-users/", admin_views.admin_users, name="admin_users"),
    path("admin-users/<int:user_id>/", admin_views.admin_user_detail, name="admin_user_detail"),
    path("admin-users/<int:user_id>/role/", admin_views.admin_set_role, name="admin_set_role"),
    path("admin-users/<int:user_id>/active/", admin_views.admin_toggle_active, name="admin_toggle_active"),
    path("posts/", views.posts, name="posts"),
    path("files/", views.files, name="files"),
    path("files/<int:file_id>/preview/", views.file_preview, name="file_preview"),
    path("files/<int:file_id>/download/", views.file_download, name="file_download"),
    path("files/<int:file_id>/delete/", views.delete_file, name="file_delete"),
    path("account/delete/", views.delete_account, name="delete_account"),
]
