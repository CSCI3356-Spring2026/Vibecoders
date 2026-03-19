from datetime import date
from io import BytesIO
from tempfile import TemporaryDirectory

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test.utils import override_settings
from PIL import Image

from communications.models import ListingConversation
from communications.services import serialize_conversation_for_user

from ..models import Listing, ListingImage
from .base import ListingTestCase


class ListingModelTests(ListingTestCase):
    def _image_upload(self, name="photo.png"):
        buffer = BytesIO()
        Image.new("RGB", (8, 8), color=(79, 70, 229)).save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def test_database_constraint_rejects_invalid_dates(self):
        with self.assertRaises(IntegrityError):
            Listing.objects.create(
                owner=self.user,
                title="Broken listing",
                address="140 Commonwealth Ave",
                price="1200.00",
                lease_type="FULL",
                start_date=date(2027, 5, 31),
                end_date=date(2026, 9, 1),
            )

    def test_conversation_add_message_updates_unread_state(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        listing = self.create_listing()
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=listing.owner,
            participant=participant,
        )

        conversation.add_message(sender=participant, body="Interested.")
        conversation.refresh_from_db()

        self.assertTrue(conversation.owner_has_unread_messages)
        self.assertFalse(conversation.participant_has_unread_messages)
        self.assertEqual(conversation.last_message_preview, "Interested.")

    def test_conversation_rejects_non_participant_sender(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        outsider = self.user.__class__.objects.create_user(
            username="outsider",
            email="outsider@bc.edu",
            password="test",
        )
        listing = self.create_listing()
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=listing.owner,
            participant=participant,
        )

        with self.assertRaises(ValidationError):
            conversation.add_message(sender=outsider, body="Hello")

    def test_serialized_conversation_payload_only_exposes_required_fields(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        listing = self.create_listing()
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=listing.owner,
            participant=participant,
        )

        payload = serialize_conversation_for_user(conversation, participant)

        self.assertNotIn("counterparty_email", payload)
        self.assertEqual(payload["counterparty_name"], listing.owner.username)

    def test_listing_image_versioned_url_is_exposed_in_conversation_payload(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )

        with TemporaryDirectory() as temp_dir, override_settings(MEDIA_ROOT=temp_dir):
            listing = self.create_listing()
            ListingImage.objects.create(listing=listing, image=self._image_upload())
            conversation = ListingConversation.objects.create(
                listing=listing,
                owner=listing.owner,
                participant=participant,
            )

            payload = serialize_conversation_for_user(conversation, participant)

        self.assertIn("?v=", payload["listing_image_url"])
