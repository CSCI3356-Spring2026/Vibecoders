from django.urls import path

from . import views

app_name = "listings"

urlpatterns = [
    path("", views.listing_list, name="listing_list"),
    path("search/", views.listing_search, name="search"),
    path("address-suggestions/", views.address_suggestions, name="address_suggestions"),
    path("group-match/", views.group_match, name="group_match"),
    path("group-match/group/", views.save_roommate_group, name="save_roommate_group"),
    path("group-match/post/", views.save_roommate_post, name="save_roommate_post"),
    path("group-match/post/pause/", views.deactivate_roommate_post, name="deactivate_roommate_post"),
    path("group-match/group-post/", views.save_group_roommate_post, name="save_group_roommate_post"),
    path("group-match/group-post/pause/", views.deactivate_group_roommate_post, name="deactivate_group_roommate_post"),
    path("<int:pk>/", views.listing_detail, name="detail"),
    path("<int:pk>/review/", views.submit_listing_review, name="submit_review"),
    path("<int:pk>/report/", views.report_listing, name="report_listing"),
    path("<int:pk>/message/", views.message_listing, name="message_listing"),
    path("<int:pk>/favorite/", views.toggle_favorite, name="toggle_favorite"),
    path("create/", views.create_listing, name="create_listing"),
    path("edit/<int:pk>/", views.edit_listing, name="edit_listing"),
    path("delete/<int:pk>/", views.delete_listing, name="delete_listing"),
]
