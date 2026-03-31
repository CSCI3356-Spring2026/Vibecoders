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


def direct_conversation_between_users(user, other_user):
    return (
        accessible_conversations_for_user(user)
        .filter(conversation_type=ListingConversation.CONVERSATION_TYPE_DIRECT)
        .filter(Q(owner=other_user) | Q(participant=other_user))
        .first()
    )


def direct_conversations_by_counterparty(user, counterparties):
    counterparty_ids = [counterparty.id for counterparty in counterparties if getattr(counterparty, "id", None)]
    if not counterparty_ids:
        return {}

    conversations = (
        accessible_conversations_for_user(user)
        .filter(conversation_type=ListingConversation.CONVERSATION_TYPE_DIRECT)
        .filter(Q(owner_id__in=counterparty_ids) | Q(participant_id__in=counterparty_ids))
    )

    mapping = {}
    for conversation in conversations:
        counterparty = conversation.counterparty_for(user)
        if counterparty is not None:
            mapping[counterparty.id] = conversation
    return mapping


def user_related_conversations_queryset(user):
    return ListingConversation.objects.with_related().filter(Q(owner=user) | Q(participant=user))


def user_related_messages_queryset(user):
    return ListingMessage.objects.select_related("conversation__listing", "sender").filter(
        Q(sender=user) | Q(conversation__owner=user) | Q(conversation__participant=user)
    )
