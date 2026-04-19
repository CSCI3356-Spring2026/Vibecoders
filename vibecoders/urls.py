from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from listings import views as listing_views
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

urlpatterns += [
    path("media/listing_photos/<path:path>", listing_views.public_listing_photo),
    path("media/avatars/<path:path>", user_views.public_avatar),
]
