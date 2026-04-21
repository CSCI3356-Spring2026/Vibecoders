from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("healthz/", views.healthz, name="healthz"),
    path("readyz/", views.readyz, name="readyz"),
    path("welcome/", views.welcome, name="welcome"),
    path("terms/", views.terms_of_service, name="terms"),
    path("privacy/", views.privacy_policy, name="privacy"),
]
