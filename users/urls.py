from django.urls import path

from . import admin_views, views

app_name = "users"

urlpatterns = [
    path("login/", views.login_page, name="login"),
    path("profile/", views.profile, name="profile"),
    path("profile/setup/", views.profile_setup, name="profile_setup"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("admin-dashboard/", admin_views.admin_dashboard, name="admin_dashboard"),
    path("admin-listings/", admin_views.admin_listings, name="admin_listings"),
    path("admin-listings/<int:listing_id>/", admin_views.admin_listing_detail, name="admin_listing_detail"),
    path("admin-listings/<int:listing_id>/review/", admin_views.admin_review_listing, name="admin_review_listing"),
    path("admin-listings/<int:listing_id>/delete/", admin_views.admin_delete_listing, name="admin_delete_listing"),
    path("admin-reports/", admin_views.admin_reports, name="admin_reports"),
    path("admin-reports/<int:report_id>/status/", admin_views.admin_update_report, name="admin_update_report"),
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
    path("browse/", views.browse_roommates, name="browse_roommates"),
    path("profile/<int:user_id>/", views.public_profile, name="public_profile"),
]
