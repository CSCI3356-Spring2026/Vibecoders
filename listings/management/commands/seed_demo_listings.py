from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from communications.models import ListingConversation

from ...models import Listing, ListingImage
from ...sample_data import (
    DEMO_LISTING_IMAGE_FILENAMES,
    DEMO_USERS,
    demo_conversation_definitions,
    demo_listing_definitions,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Seed the local database with deterministic demo users, listings, and message conversations."

    def handle(self, *args, **options):
        created_users = 0
        updated_users = 0
        created_listings = 0
        updated_listings = 0
        created_listing_images = 0
        updated_listing_images = 0
        created_conversations = 0
        updated_conversations = 0
        created_messages = 0
        users_by_email = {}
        listing_definitions = demo_listing_definitions()

        for user_data in DEMO_USERS:
            user, created = self._upsert_user(user_data)
            users_by_email[user.email] = user
            if created:
                created_users += 1
            else:
                updated_users += 1

        for listing_data in listing_definitions:
            owner_email = listing_data["owner_email"]
            owner = users_by_email.get(owner_email)
            if owner is None:
                raise CommandError(
                    f'Cannot seed listing "{listing_data["title"]}" because owner "{owner_email}" is missing.'
                )

            defaults = {key: value for key, value in listing_data.items() if key != "owner_email"}
            _, created = Listing.objects.update_or_create(
                owner=owner,
                title=listing_data["title"],
                defaults=defaults,
            )
            if created:
                created_listings += 1
            else:
                updated_listings += 1

        listing_titles = [data["title"] for data in listing_definitions]
        listings_by_title = {listing.title: listing for listing in Listing.objects.filter(title__in=listing_titles)}
        for listing_title, image_filename in DEMO_LISTING_IMAGE_FILENAMES.items():
            listing = listings_by_title.get(listing_title)
            if listing is None:
                raise CommandError(f'Cannot seed image because listing "{listing_title}" is missing.')

            created, updated = self._sync_listing_image(listing, image_filename)
            if created:
                created_listing_images += 1
            elif updated:
                updated_listing_images += 1

        for conversation_data in demo_conversation_definitions():
            listing = listings_by_title.get(conversation_data["listing_title"])
            participant = users_by_email.get(conversation_data["participant_email"])
            if listing is None:
                raise CommandError(
                    f'Cannot seed conversation because listing "{conversation_data["listing_title"]}" is missing.'
                )
            if participant is None:
                raise CommandError(
                    "Cannot seed conversation because participant "
                    f'"{conversation_data["participant_email"]}" is missing.'
                )
            if listing.owner_id == participant.id:
                raise CommandError(
                    f'Seed conversation participant "{participant.email}" cannot own listing "{listing.title}".'
                )

            conversation, created = ListingConversation.objects.get_or_create(
                listing=listing,
                participant=participant,
                defaults={"owner": listing.owner},
            )
            if created:
                created_conversations += 1
            else:
                updated_conversations += 1

            if conversation.owner_id != listing.owner_id:
                conversation.owner = listing.owner
                conversation.save(update_fields=["owner"])

            conversation.messages.all().delete()
            conversation.owner_has_unread_messages = False
            conversation.participant_has_unread_messages = False
            conversation.owner_deleted_at = None
            conversation.participant_deleted_at = None
            conversation.last_message_preview = ""
            conversation.save(
                update_fields=[
                    "owner_has_unread_messages",
                    "participant_has_unread_messages",
                    "owner_deleted_at",
                    "participant_deleted_at",
                    "last_message_preview",
                ]
            )

            for message_data in conversation_data["messages"]:
                sender = users_by_email.get(message_data["sender_email"])
                if sender is None:
                    raise CommandError(
                        f'Cannot seed message because sender "{message_data["sender_email"]}" is missing.'
                    )
                conversation.add_message(sender=sender, body=message_data["body"])
                created_messages += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded demo marketplace data: "
                f"{created_users} users created, {updated_users} users updated; "
                f"{created_listings} listings created, {updated_listings} listings updated; "
                f"{created_listing_images} listing images created, {updated_listing_images} listing images updated; "
                f"{created_conversations} conversations created, {updated_conversations} conversations updated; "
                f"{created_messages} messages created."
            )
        )

    def _upsert_user(self, user_data):
        email_user = User.objects.filter(email=user_data["email"]).order_by("pk").first()
        username_user = User.objects.filter(username=user_data["username"]).order_by("pk").first()

        if email_user and username_user and email_user.pk != username_user.pk:
            raise CommandError(
                "Seed user lookup matched different records for "
                f'email "{user_data["email"]}" and username "{user_data["username"]}".'
            )

        user = email_user or username_user
        created = user is None
        field_names = ["username", "email", "first_name", "last_name"]

        if created:
            user = User.objects.create_user(
                username=user_data["username"],
                email=user_data["email"],
                first_name=user_data["first_name"],
                last_name=user_data["last_name"],
            )
            return user, True

        for field_name in field_names:
            setattr(user, field_name, user_data[field_name])
        user.save(update_fields=[*field_names, "role"])
        return user, False

    def _sync_listing_image(self, listing, image_filename):
        desired_name = f"listing_photos/{image_filename}"
        source_path = Path(settings.MEDIA_ROOT) / desired_name
        if not source_path.exists():
            raise CommandError(
                f'Cannot seed image for listing "{listing.title}" because "{desired_name}" is missing from MEDIA_ROOT.'
            )

        existing_images = list(listing.images.order_by("id"))
        desired_image = next((image for image in existing_images if image.image.name == desired_name), None)
        created = False
        updated = False

        if desired_image is None:
            if existing_images:
                desired_image = existing_images[0]
                old_name = desired_image.image.name
                desired_image.image.name = desired_name
                desired_image.save(update_fields=["image"])
                if old_name and old_name != desired_name and desired_image.image.storage.exists(old_name):
                    desired_image.image.storage.delete(old_name)
                updated = True
            else:
                ListingImage.objects.create(listing=listing, image=desired_name)
                created = True
                return created, updated

        for stale_image in existing_images:
            if stale_image.pk == desired_image.pk or stale_image.image.name == desired_name:
                continue
            stale_image.delete()
            updated = True

        return created, updated
