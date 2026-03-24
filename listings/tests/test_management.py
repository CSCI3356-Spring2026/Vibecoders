from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase
from django.test.utils import override_settings
from PIL import Image

from communications.models import ListingConversation, ListingMessage
from communications.services import delete_conversation_for_user

from ..models import Listing
from ..sample_data import (
    DEMO_LISTING_IMAGE_FILENAMES,
    DEMO_USERS,
    demo_conversation_definitions,
    demo_listing_definitions,
)
from .base import User


class SeedDemoListingsCommandTests(TestCase):
    def _create_demo_source_images(self, media_root):
        listing_photos_dir = media_root / "listing_photos"
        listing_photos_dir.mkdir(parents=True, exist_ok=True)
        for filename in DEMO_LISTING_IMAGE_FILENAMES.values():
            image = Image.new("RGB", (8, 8), color=(79, 70, 229))
            image.save(listing_photos_dir / filename, format="PNG")

    def test_command_creates_demo_marketplace_data(self):
        stdout = StringIO()
        with TemporaryDirectory() as temp_dir:
            media_root = Path(temp_dir)
            self._create_demo_source_images(media_root)

            with override_settings(MEDIA_ROOT=media_root):
                call_command("seed_demo_listings", stdout=stdout)

            self.assertEqual(User.objects.count(), len(DEMO_USERS))
            self.assertEqual(Listing.objects.count(), len(demo_listing_definitions()))
            self.assertEqual(ListingConversation.objects.count(), len(demo_conversation_definitions()))
            self.assertEqual(
                ListingMessage.objects.count(),
                sum(len(conversation["messages"]) for conversation in demo_conversation_definitions()),
            )
            self.assertTrue(User.objects.get(email="maya.sullivan@bc.edu").is_student)
            self.assertTrue(User.objects.get(email="olivia@chestnuthillrealty.com").is_realtor)
            self.assertIn("Seeded demo marketplace data", stdout.getvalue())
            self.assertTrue(Listing.objects.get(title="Cleveland Circle 2BR with parking").images.exists())

    def test_command_is_idempotent(self):
        with TemporaryDirectory() as temp_dir:
            media_root = Path(temp_dir)
            self._create_demo_source_images(media_root)

            with override_settings(MEDIA_ROOT=media_root):
                call_command("seed_demo_listings", stdout=StringIO())
                call_command("seed_demo_listings", stdout=StringIO())

            self.assertEqual(User.objects.count(), len(DEMO_USERS))
            self.assertEqual(Listing.objects.count(), len(demo_listing_definitions()))
            self.assertEqual(ListingConversation.objects.count(), len(demo_conversation_definitions()))
            self.assertEqual(
                ListingMessage.objects.count(),
                sum(len(conversation["messages"]) for conversation in demo_conversation_definitions()),
            )

    def test_command_updates_stale_demo_listing_images(self):
        with TemporaryDirectory() as temp_dir:
            media_root = Path(temp_dir)
            self._create_demo_source_images(media_root)

            with override_settings(MEDIA_ROOT=media_root):
                call_command("seed_demo_listings", stdout=StringIO())

                listing = Listing.objects.get(title="Cleveland Circle 2BR with parking")
                listing_image = listing.images.get()
                old_path = media_root / "listing_photos" / "old-demo-photo.jpg"
                Image.new("RGB", (8, 8), color=(13, 148, 136)).save(old_path, format="PNG")
                listing_image.image.name = "listing_photos/old-demo-photo.jpg"
                listing_image.save(update_fields=["image"])

                call_command("seed_demo_listings", stdout=StringIO())

                listing.refresh_from_db()
                synced_image = listing.images.get()
                self.assertEqual(
                    synced_image.image.name,
                    "listing_photos/cleveland-circle-2br.jpg",
                )
                self.assertFalse(old_path.exists())

    def test_command_restores_deleted_demo_conversations(self):
        with TemporaryDirectory() as temp_dir:
            media_root = Path(temp_dir)
            self._create_demo_source_images(media_root)

            with override_settings(MEDIA_ROOT=media_root):
                call_command("seed_demo_listings", stdout=StringIO())

                conversation = ListingConversation.objects.first()
                delete_conversation_for_user(conversation, conversation.participant)
                conversation.refresh_from_db()
                self.assertIsNotNone(conversation.participant_deleted_at)

                call_command("seed_demo_listings", stdout=StringIO())

                conversation.refresh_from_db()
                self.assertIsNone(conversation.owner_deleted_at)
                self.assertIsNone(conversation.participant_deleted_at)
