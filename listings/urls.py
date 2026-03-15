from django.urls import path

from . import views

app_name = "listings"

urlpatterns = [
    # Minimal current URLs
    path("", views.listing_list, name="listing_list"),
    path("detail/", views.listing_detail, name="detail"),
    path("create/", views.create_listing, name="create_listing"),
]
