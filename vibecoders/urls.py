from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from django.views.static import serve

from users import views as user_views

urlpatterns = [
    path("", include("core.urls")),
    path("roommates/", include("roommates.urls")),
    path("users/messages/", include("communications.urls")),
    path("users/", include("users.urls")),
    path("accounts/login/", user_views.login_page),
    path("accounts/google/login/", user_views.google_login_gate),
    path("accounts/", include("allauth.urls")),
    path("listings/", include("listings.urls")),
]

if settings.DJANGO_ADMIN_ENABLED:
    urlpatterns.insert(0, path("admin/", admin.site.urls))

if settings.DEBUG:
    # Listing images need a simple dev-time media route, but private user uploads must stay behind
    # authenticated preview/download views instead of being served directly.
    urlpatterns += [
        path(
            "media/listing_photos/<path:path>",
            serve,
            {"document_root": settings.MEDIA_ROOT / "listing_photos"},
        ),
        path(
            "media/avatars/<path:path>",
            serve,
            {"document_root": settings.MEDIA_ROOT / "avatars"},
        ),
    ]
