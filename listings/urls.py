from django.urls import path

from . import views

app_name = "listings"

urlpatterns = [
    path("", views.listing_list, name="listing_list"),
    path("search/", views.listing_search, name="search"),
    path("address-suggestions/", views.address_suggestions, name="address_suggestions"),
    path("group-match/", views.group_match, name="group_match"),
    path("<int:pk>/", views.listing_detail, name="detail"),
    path("<int:pk>/message/", views.message_listing, name="message_listing"),
    path("<int:pk>/favorite/", views.toggle_favorite, name="toggle_favorite"),
    path("create/", views.create_listing, name="create_listing"),
    path("edit/<int:pk>/", views.edit_listing, name="edit_listing"),
    path("delete/<int:pk>/", views.delete_listing, name="delete_listing"),
]
