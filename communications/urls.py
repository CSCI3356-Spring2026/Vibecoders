from django.urls import path

from . import views

app_name = "communications"

urlpatterns = [
    path("", views.messages_inbox, name="messages"),
    path("<int:conversation_id>/", views.messages_inbox, name="detail"),
    path("<int:conversation_id>/reply/", views.reply_conversation, name="reply_conversation"),
    path("<int:conversation_id>/delete/", views.delete_conversation, name="delete_conversation"),
]
