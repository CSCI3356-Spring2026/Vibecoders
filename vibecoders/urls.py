from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from users import views as user_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
    path("users/", include("users.urls")),
    path("accounts/login/", user_views.login_page),
    path("accounts/", include("allauth.urls")),
    path("listings/", include("listings.urls")),
<<<<<<< HEAD
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
=======
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
