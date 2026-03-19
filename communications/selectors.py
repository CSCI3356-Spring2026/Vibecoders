from django.db.models import Q

from .models import ListingConversation, ListingMessage


def accessible_conversations_for_user(user):
    return ListingConversation.objects.visible_to(user).order_by("-last_message_at", "-created_at")


def inbox_conversations_for_user(user):
    return accessible_conversations_for_user(user).prefetch_related("listing__images")


def unread_conversations_for_user(user):
    return accessible_conversations_for_user(user).filter(
        Q(owner=user, owner_has_unread_messages=True) | Q(participant=user, participant_has_unread_messages=True)
    )


def conversation_summary_for_user(user):
    conversations_qs = accessible_conversations_for_user(user)
    unread_qs = unread_conversations_for_user(user)
    return {
        "conversations_count": conversations_qs.count(),
        "unread_conversations_count": unread_qs.count(),
    }


def user_related_conversations_queryset(user):
    return ListingConversation.objects.with_related().filter(Q(owner=user) | Q(participant=user))


def user_related_messages_queryset(user):
    return ListingMessage.objects.select_related("conversation__listing", "sender").filter(
        Q(sender=user) | Q(conversation__owner=user) | Q(conversation__participant=user)
    )
