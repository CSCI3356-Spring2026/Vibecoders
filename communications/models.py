from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q
from django.utils import timezone

MESSAGE_BODY_MAX_LENGTH = 2000
MESSAGE_PREVIEW_MAX_LENGTH = 280


def normalize_message_body(body):
    normalized = (body or "").replace("\r\n", "\n").strip()
    if not normalized:
        raise ValidationError({"body": "Enter a message before sending."})
    if len(normalized) > MESSAGE_BODY_MAX_LENGTH:
        raise ValidationError({"body": f"Messages must be {MESSAGE_BODY_MAX_LENGTH} characters or fewer."})
    return normalized


class ListingConversationQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related("listing", "owner", "participant")

    def visible_to(self, user):
        if not getattr(user, "is_authenticated", False):
            return self.none()
        return self.with_related().filter(Q(owner=user) | Q(participant=user))


class ListingConversation(models.Model):
    listing = models.ForeignKey("listings.Listing", related_name="conversations", on_delete=models.CASCADE)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="owned_listing_conversations",
        on_delete=models.CASCADE,
    )
    participant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="listing_conversations",
        on_delete=models.CASCADE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(default=timezone.now)
    last_message_preview = models.CharField(max_length=MESSAGE_PREVIEW_MAX_LENGTH, blank=True)
    owner_has_unread_messages = models.BooleanField(default=False)
    participant_has_unread_messages = models.BooleanField(default=False)
    objects = ListingConversationQuerySet.as_manager()

    class Meta:
        db_table = "listings_listingconversation"
        ordering = ["-last_message_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["listing", "participant"], name="unique_listing_conversation_participant"),
            models.CheckConstraint(
                condition=~Q(owner=F("participant")),
                name="listing_conversation_owner_ne_participant",
            ),
        ]
        indexes = [
            models.Index(fields=["listing", "last_message_at"], name="listing_conv_listing_idx"),
            models.Index(
                fields=["owner", "owner_has_unread_messages", "last_message_at"],
                name="listing_conv_owner_idx",
            ),
            models.Index(
                fields=["participant", "participant_has_unread_messages", "last_message_at"],
                name="listing_conv_participant_idx",
            ),
        ]

    def clean(self):
        super().clean()
        if self.listing_id and self.owner_id and self.listing.owner_id != self.owner_id:
            raise ValidationError({"owner": "Conversation owner must match the listing owner."})
        if self.owner_id and self.participant_id and self.owner_id == self.participant_id:
            raise ValidationError({"participant": "Listing owners cannot open a conversation with themselves."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def counterparty_for(self, user):
        if user.id == self.owner_id:
            return self.participant
        if user.id == self.participant_id:
            return self.owner
        return None

    def counterparty_role_label_for(self, user):
        if user.id == self.owner_id:
            return "Interested renter"
        if user.id == self.participant_id:
            return "Listing owner"
        return ""

    def has_unread_for(self, user):
        if user.id == self.owner_id:
            return self.owner_has_unread_messages
        if user.id == self.participant_id:
            return self.participant_has_unread_messages
        return False

    def mark_read_for(self, user):
        if user.id == self.owner_id and self.owner_has_unread_messages:
            self.owner_has_unread_messages = False
            self.save(update_fields=["owner_has_unread_messages"])
            return True
        if user.id == self.participant_id and self.participant_has_unread_messages:
            self.participant_has_unread_messages = False
            self.save(update_fields=["participant_has_unread_messages"])
            return True
        return False

    def add_message(self, sender, body):
        if sender.id not in {self.owner_id, self.participant_id}:
            raise ValidationError("Only conversation participants can send messages.")

        normalized_body = normalize_message_body(body)

        with transaction.atomic():
            message = self.messages.create(sender=sender, body=normalized_body)
            self.last_message_at = message.created_at
            self.last_message_preview = normalized_body[:MESSAGE_PREVIEW_MAX_LENGTH]
            if sender.id == self.owner_id:
                self.owner_has_unread_messages = False
                self.participant_has_unread_messages = True
            else:
                self.owner_has_unread_messages = True
                self.participant_has_unread_messages = False
            self.save(
                update_fields=[
                    "last_message_at",
                    "last_message_preview",
                    "owner_has_unread_messages",
                    "participant_has_unread_messages",
                ]
            )
        return message

    def __str__(self):
        return f"Conversation about {self.listing} with {self.participant}"


class ListingMessage(models.Model):
    conversation = models.ForeignKey(ListingConversation, related_name="messages", on_delete=models.CASCADE)
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="listing_messages", on_delete=models.CASCADE)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "listings_listingmessage"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"], name="listing_message_thread_idx"),
            models.Index(fields=["sender", "created_at"], name="listing_message_sender_idx"),
        ]

    def clean(self):
        super().clean()
        if self.conversation_id and self.sender_id not in {
            self.conversation.owner_id,
            self.conversation.participant_id,
        }:
            raise ValidationError({"sender": "Sender must be part of the conversation."})
        self.body = normalize_message_body(self.body)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Message from {self.sender} in {self.conversation}"
