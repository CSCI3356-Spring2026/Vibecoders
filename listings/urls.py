from django.urls import path

from . import views

app_name = "listings"

urlpatterns = [
    path("", views.listing_list, name="listing_list"),
    path("<int:pk>/", views.listing_detail, name="detail"),
    path("create/", views.create_listing, name="create_listing"),
    path("edit/<int:pk>/", views.edit_listing, name="edit_listing"),
    path("delete/<int:pk>/", views.delete_listing, name="delete_listing"),
]
