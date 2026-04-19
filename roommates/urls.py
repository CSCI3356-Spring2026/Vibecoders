from django.urls import path

from . import views

app_name = "roommates"

urlpatterns = [
    path("", views.hub, name="hub"),
    path("browse/", views.browse_redirect, name="browse_redirect"),
    path("profile/<int:user_id>/", views.public_profile, name="public_profile"),
    path("favorite/<int:user_id>/", views.toggle_favorite_roommate, name="toggle_favorite_roommate"),
    path("group-invite/<int:user_id>/", views.send_group_invite, name="send_group_invite"),
    path("group-invite/<int:invite_id>/approve/", views.approve_group_invite, name="approve_group_invite"),
    path("group-invite/<int:invite_id>/reject/", views.reject_group_invite, name="reject_group_invite"),
    path("group-invite/<int:invite_id>/accept/", views.accept_group_invite, name="accept_group_invite"),
    path("group-invite/<int:invite_id>/decline/", views.decline_group_invite, name="decline_group_invite"),
    path("post/", views.save_roommate_post, name="save_roommate_post"),
    path("post/<int:pk>/edit/", views.edit_roommate_post, name="edit_roommate_post"),
    path("post/<int:pk>/delete/", views.delete_roommate_post, name="delete_roommate_post"),
    path("post/pause/", views.deactivate_roommate_post, name="deactivate_roommate_post"),
    path("group/", views.save_roommate_group, name="save_roommate_group"),
    path("group/member/<int:member_pk>/remove/", views.remove_group_member, name="remove_group_member"),
    path("group-post/", views.save_group_roommate_post, name="save_group_roommate_post"),
    path("group-post/pause/", views.deactivate_group_roommate_post, name="deactivate_group_roommate_post"),
]
