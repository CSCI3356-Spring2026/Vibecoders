from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from core.rate_limits import consume_rate_limit

from .models import ListingConversation

MESSAGE_SEND_RATE_LIMIT_ERROR = "Too many messages sent too quickly. Wait a minute and try again."


def user_messages_group_name(user_id):
    return f"messages-user-{user_id}"


def _publish_to_user_group(user_id, payload):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(user_messages_group_name(user_id), payload)


def get_or_create_listing_conversation(listing, participant):
    try:
        conversation, created = ListingConversation.objects.get_or_create(
            listing=listing,
            participant=participant,
            defaults={"owner": listing.owner},
        )
    except IntegrityError:
        conversation = ListingConversation.objects.get(listing=listing, participant=participant)
        created = False
    if conversation.owner_id != listing.owner_id:
        conversation.owner = listing.owner
        conversation.save(update_fields=["owner"])
    return conversation, created


def _validate_listing_conversation_participant(listing, participant):
    if not getattr(participant, "is_authenticated", False) or not getattr(participant, "is_active", False):
        raise ValidationError({"body": "Active account access is required to message about listings."})
    if not type(listing).objects.public().filter(pk=listing.pk).exists():
        raise ValidationError({"body": "This listing is no longer accepting new messages."})
    if participant.id == listing.owner_id:
        raise ValidationError({"body": "You cannot message yourself about your own listing."})
    if not getattr(participant, "can_start_listing_conversations", False):
        raise ValidationError({"body": "Verified student access is required to message about listings."})


def _listing_image_url(conversation):
    primary_image = conversation.listing.primary_image
    if primary_image and primary_image.image:
        return primary_image.versioned_url
    return ""


def _summary_delta(conversation_delta=0, unread_delta=0):
    return {
        "conversation_delta": conversation_delta,
        "unread_delta": unread_delta,
    }


def _profile_image_url(user):
    return getattr(user, "avatar_url", "") or ""


def consume_message_send_rate_limit(user):
    user_id = getattr(user, "id", None)
    if not user_id:
        return False

    return consume_rate_limit(
        scope="message-send",
        identifier=str(user_id),
        limit=getattr(settings, "MESSAGE_SEND_RATE_LIMIT", 20),
        window_seconds=getattr(settings, "MESSAGE_SEND_RATE_WINDOW_SECONDS", 60),
    )


def serialize_conversation_for_user(conversation, user):
    counterparty = conversation.counterparty_for(user)
    if counterparty is None:
        raise ValidationError("Conversation access denied.")
    return {
        "id": conversation.id,
        "listing_id": conversation.listing_id,
        "listing_title": conversation.listing.title,
        "listing_address": conversation.listing.address,
        "listing_price": str(conversation.listing.price),
        "listing_status": conversation.listing.get_status_display(),
        "listing_image_url": _listing_image_url(conversation),
        "counterparty_name": counterparty.display_name,
        "counterparty_avatar_url": _profile_image_url(counterparty),
        "counterparty_role_label": conversation.counterparty_role_label_for(user),
        "last_message_at": conversation.last_message_at.isoformat(),
        "last_message_preview": conversation.last_message_preview,
        "has_unread": conversation.has_unread_for(user),
    }


def serialize_message(message):
    sender = message.sender
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "sender_id": sender.id,
        "sender_name": sender.display_name,
        "sender_avatar_url": _profile_image_url(sender),
        "body": message.body,
        "created_at": message.created_at.isoformat(),
    }


def publish_conversation_message(message, *, summary_deltas=None):
    conversation = message.conversation
    recipients = (conversation.owner, conversation.participant)
    serialized_message = serialize_message(message)
    summary_deltas = summary_deltas or {}
    for recipient in recipients:
        summary = summary_deltas.get(recipient.id, _summary_delta())
        _publish_to_user_group(
            recipient.id,
            {
                "type": "message.event",
                "event": "message.created",
                "conversation": serialize_conversation_for_user(conversation, recipient),
                "message": serialized_message,
                "summary": summary,
            },
        )


def publish_conversation_read(conversation, user, *, unread_delta=0):
    _publish_to_user_group(
        user.id,
        {
            "type": "message.event",
            "event": "conversation.read",
            "conversation": serialize_conversation_for_user(conversation, user),
            "summary": _summary_delta(unread_delta=unread_delta),
        },
    )


def mark_conversation_read(conversation, user):
    changed = False
    with transaction.atomic():
        locked_conversation = ListingConversation.objects.with_related().select_for_update().get(pk=conversation.pk)
        changed = locked_conversation.mark_read_for(user)
        if changed:
            transaction.on_commit(lambda: publish_conversation_read(locked_conversation, user, unread_delta=-1))
    return changed


def _message_summary_deltas(
    conversation,
    sender_id,
    owner_had_unread,
    participant_had_unread,
    owner_was_deleted,
    participant_was_deleted,
    *,
    conversation_created=False,
):
    owner_conversation_delta = 1 if conversation_created or owner_was_deleted else 0
    participant_conversation_delta = 1 if conversation_created or participant_was_deleted else 0

    if sender_id == conversation.owner_id:
        return {
            conversation.owner_id: _summary_delta(
                conversation_delta=owner_conversation_delta,
                unread_delta=-1 if owner_had_unread else 0,
            ),
            conversation.participant_id: _summary_delta(
                conversation_delta=participant_conversation_delta,
                unread_delta=1 if not participant_had_unread else 0,
            ),
        }
    return {
        conversation.owner_id: _summary_delta(
            conversation_delta=owner_conversation_delta,
            unread_delta=1 if not owner_had_unread else 0,
        ),
        conversation.participant_id: _summary_delta(
            conversation_delta=participant_conversation_delta,
            unread_delta=-1 if participant_had_unread else 0,
        ),
    }


def _send_listing_message_locked(conversation, sender, body, *, conversation_created=False):
    owner_had_unread = conversation.owner_has_unread_messages
    participant_had_unread = conversation.participant_has_unread_messages
    owner_was_deleted = conversation.owner_deleted_at is not None
    participant_was_deleted = conversation.participant_deleted_at is not None
    message = conversation.add_message(sender=sender, body=body)
    summary_deltas = _message_summary_deltas(
        conversation,
        sender.id,
        owner_had_unread,
        participant_had_unread,
        owner_was_deleted,
        participant_was_deleted,
        conversation_created=conversation_created,
    )
    transaction.on_commit(
        lambda: publish_conversation_message(
            message,
            summary_deltas=summary_deltas,
        )
    )
    return message


def send_listing_message(conversation, sender, body, *, conversation_created=False):
    with transaction.atomic():
        locked_conversation = ListingConversation.objects.with_related().select_for_update().get(pk=conversation.pk)
        message = _send_listing_message_locked(
            locked_conversation,
            sender,
            body,
            conversation_created=conversation_created,
        )
    return message


def start_listing_conversation(listing, participant, body):
    _validate_listing_conversation_participant(listing, participant)
    with transaction.atomic():
        conversation, created = get_or_create_listing_conversation(listing, participant)
        locked_conversation = ListingConversation.objects.with_related().select_for_update().get(pk=conversation.pk)
        message = _send_listing_message_locked(
            locked_conversation,
            participant,
            body,
            conversation_created=created,
        )
    return locked_conversation, message, created


def delete_conversation_for_user(conversation, user):
    with transaction.atomic():
        locked_conversation = ListingConversation.objects.select_for_update().get(pk=conversation.pk)
        return locked_conversation.delete_for(user)
