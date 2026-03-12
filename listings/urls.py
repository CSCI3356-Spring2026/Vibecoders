from django.urls import path

from . import views

app_name = "listings"

urlpatterns = [
    # Minimal current URLs
    path("", views.search, name="search"),
    path("detail/", views.listing_detail, name="detail"),
    path("create/", views.create_listing, name="create"),
    path('', views.listing_list, name='listing_list'),
    path('create/', views.create_listing, name='create_listing'),
]
