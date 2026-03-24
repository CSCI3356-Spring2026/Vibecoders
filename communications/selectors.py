from django.db.models import Count, Q

from .models import ListingConversation, ListingMessage


def accessible_conversations_for_user(user):
    return ListingConversation.objects.visible_to(user).with_related().order_by("-last_message_at", "-created_at")


def inbox_conversations_for_user(user):
    return accessible_conversations_for_user(user)


def unread_conversations_for_user(user):
    return accessible_conversations_for_user(user).filter(
        Q(owner=user, owner_has_unread_messages=True) | Q(participant=user, participant_has_unread_messages=True)
    )


def conversation_summary_for_user(user):
    summary = ListingConversation.objects.visible_to(user).aggregate(
        conversations_count=Count("id"),
        unread_conversations_count=Count(
            "id",
            filter=Q(owner=user, owner_has_unread_messages=True)
            | Q(participant=user, participant_has_unread_messages=True),
        ),
    )
    return summary


def user_related_conversations_queryset(user):
    return ListingConversation.objects.with_related().filter(Q(owner=user) | Q(participant=user))


def user_related_messages_queryset(user):
    return ListingMessage.objects.select_related("conversation__listing", "sender").filter(
        Q(sender=user) | Q(conversation__owner=user) | Q(conversation__participant=user)
    )
