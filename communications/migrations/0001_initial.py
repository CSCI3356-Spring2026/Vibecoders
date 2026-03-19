# Generated manually to adopt existing messaging tables from listings.

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("listings", "0007_listingconversation_listingmessage_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="ListingConversation",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("last_message_at", models.DateTimeField(default=django.utils.timezone.now)),
                        ("last_message_preview", models.CharField(blank=True, max_length=280)),
                        ("owner_has_unread_messages", models.BooleanField(default=False)),
                        ("participant_has_unread_messages", models.BooleanField(default=False)),
                        (
                            "listing",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="conversations",
                                to="listings.listing",
                            ),
                        ),
                        (
                            "owner",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="owned_listing_conversations",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                        (
                            "participant",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="listing_conversations",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "db_table": "listings_listingconversation",
                        "ordering": ["-last_message_at", "-created_at"],
                        "indexes": [
                            models.Index(fields=["listing", "last_message_at"], name="listing_conv_listing_idx"),
                            models.Index(
                                fields=["owner", "owner_has_unread_messages", "last_message_at"],
                                name="listing_conv_owner_idx",
                            ),
                            models.Index(
                                fields=["participant", "participant_has_unread_messages", "last_message_at"],
                                name="listing_conv_participant_idx",
                            ),
                        ],
                        "constraints": [
                            models.UniqueConstraint(
                                fields=("listing", "participant"),
                                name="unique_listing_conversation_participant",
                            ),
                            models.CheckConstraint(
                                condition=models.Q(("owner", models.F("participant")), _negated=True),
                                name="listing_conversation_owner_ne_participant",
                            ),
                        ],
                    },
                ),
                migrations.CreateModel(
                    name="ListingMessage",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        ("body", models.TextField()),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        (
                            "conversation",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="messages",
                                to="communications.listingconversation",
                            ),
                        ),
                        (
                            "sender",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="listing_messages",
                                to=settings.AUTH_USER_MODEL,
                            ),
                        ),
                    ],
                    options={
                        "db_table": "listings_listingmessage",
                        "ordering": ["created_at"],
                        "indexes": [
                            models.Index(fields=["conversation", "created_at"], name="listing_message_thread_idx"),
                            models.Index(fields=["sender", "created_at"], name="listing_message_sender_idx"),
                        ],
                    },
                ),
            ],
        ),
    ]
