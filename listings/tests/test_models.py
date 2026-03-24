from datetime import date, timedelta
from io import BytesIO
from tempfile import TemporaryDirectory

from allauth.socialaccount.models import SocialAccount
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test.utils import override_settings
from PIL import Image

from communications.models import ListingConversation
from communications.selectors import accessible_conversations_for_user
from communications.services import (
    delete_conversation_for_user,
    send_listing_message,
    serialize_conversation_for_user,
    start_listing_conversation,
)

from ..forms import ListingForm
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

    def test_database_constraint_rejects_negative_distance_to_campus(self):
        with self.assertRaises(IntegrityError):
            Listing.objects.create(
                owner=self.user,
                title="Broken listing",
                address="140 Commonwealth Ave",
                price="1200.00",
                lease_type="FULL",
                start_date=date(2026, 9, 1),
                end_date=date(2027, 5, 31),
                distance_to_campus="-1.00",
            )

    def test_database_constraint_rejects_invalid_listing_status(self):
        with self.assertRaises(IntegrityError):
            Listing.objects.create(
                owner=self.user,
                title="Broken listing",
                address="140 Commonwealth Ave",
                price="1200.00",
                lease_type="FULL",
                start_date=date(2026, 9, 1),
                end_date=date(2027, 5, 31),
                status="BROKEN",
            )

    def test_public_queryset_only_returns_active_marketplace_listings(self):
        today = date.today()
        active_listing = self.create_listing(title="Active listing")
        self.create_listing(title="Taken listing", status=Listing.STATUS_TAKEN)
        self.create_listing(
            title="Expired listing",
            start_date=today - timedelta(days=90),
            end_date=today - timedelta(days=30),
        )
        self.create_listing(title="Hidden listing", is_hidden=True)

        listings = list(Listing.objects.public())

        self.assertEqual([listing.pk for listing in listings], [active_listing.pk])

    def test_listing_owner_cannot_be_reassigned_after_creation(self):
        listing = self.create_listing()
        new_owner = self.user.__class__.objects.create_user(
            username="new-owner",
            email="new-owner@bc.edu",
            password="test",
        )
        listing.owner = new_owner

        with self.assertRaises(ValidationError) as exc:
            listing.save()

        self.assertIn("Listing ownership cannot be reassigned after creation.", exc.exception.message_dict["owner"][0])

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
        self.user.profile_image_url = "https://example.com/owner-avatar.jpg"
        self.user.save(update_fields=["profile_image_url"])
        listing = self.create_listing()
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=listing.owner,
            participant=participant,
        )

        payload = serialize_conversation_for_user(conversation, participant)

        self.assertNotIn("counterparty_email", payload)
        self.assertEqual(payload["counterparty_name"], listing.owner.username)
        self.assertEqual(payload["counterparty_avatar_url"], "https://example.com/owner-avatar.jpg")

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

    def test_listing_image_file_is_not_deleted_when_transaction_rolls_back(self):
        with TemporaryDirectory() as temp_dir, override_settings(MEDIA_ROOT=temp_dir):
            listing = self.create_listing()
            listing_image = ListingImage.objects.create(listing=listing, image=self._image_upload("one.png"))
            stored_name = listing_image.image.name

            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    listing_image.delete()
                    self.assertTrue(listing_image.image.storage.exists(stored_name))
                    raise RuntimeError("rollback")

            self.assertTrue(listing_image.image.storage.exists(stored_name))

    def test_listing_estimated_totals_include_optional_cost_fields(self):
        listing = self.create_listing(
            price="1800.00",
            utilities_estimate="125.00",
            parking_fee="150.00",
            security_deposit="1800.00",
            application_fee="45.00",
        )

        self.assertEqual(listing.estimated_monthly_total, 2075)
        self.assertEqual(listing.estimated_upfront_total, 3645)

    def test_listing_form_prepopulates_known_and_other_utilities(self):
        listing = self.create_listing(utilities_included="Water, WiFi, Heat")

        form = ListingForm(instance=listing)

        self.assertEqual(form.fields["common_utilities"].initial, ["Water", "WiFi"])
        self.assertEqual(form.fields["other_utilities"].initial, "Heat")

    def test_start_listing_conversation_rejects_listing_only_user(self):
        listing = self.create_listing()
        realtor = self.user.__class__.objects.create_user(
            username="agent",
            email="agent@gmail.com",
            password="test",
        )

        with self.assertRaises(ValidationError) as exc:
            start_listing_conversation(listing, realtor, "Interested.")

        self.assertIn("Verified student access is required", exc.exception.message_dict["body"][0])

    def test_start_listing_conversation_rejects_owner(self):
        listing = self.create_listing()

        with self.assertRaises(ValidationError) as exc:
            start_listing_conversation(listing, listing.owner, "Interested.")

        self.assertIn("You cannot message yourself", exc.exception.message_dict["body"][0])

    def test_start_listing_conversation_rejects_inactive_listing(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        listing = self.create_listing(status=Listing.STATUS_TAKEN)

        with self.assertRaises(ValidationError) as exc:
            start_listing_conversation(listing, participant, "Interested.")

        self.assertIn("no longer accepting new messages", exc.exception.message_dict["body"][0])

    def test_counterparty_avatar_url_is_exposed_in_conversation_payload(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        SocialAccount.objects.create(
            user=self.user,
            provider="google",
            uid="google-owner",
            extra_data={"picture": "https://example.com/owner-avatar.png"},
        )
        listing = self.create_listing()
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=listing.owner,
            participant=participant,
        )

        payload = serialize_conversation_for_user(conversation, participant)

        self.assertEqual(payload["counterparty_avatar_url"], "https://example.com/owner-avatar.png")

    def test_deleting_conversation_hides_it_for_one_user_only(self):
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

        deleted = delete_conversation_for_user(conversation, participant)
        conversation.refresh_from_db()

        self.assertTrue(deleted)
        self.assertIsNotNone(conversation.participant_deleted_at)
        self.assertFalse(accessible_conversations_for_user(participant).filter(pk=conversation.pk).exists())
        self.assertTrue(accessible_conversations_for_user(listing.owner).filter(pk=conversation.pk).exists())

    def test_new_message_restores_deleted_conversation_visibility(self):
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
        delete_conversation_for_user(conversation, participant)

        send_listing_message(conversation, listing.owner, "Still available.")
        conversation.refresh_from_db()

        self.assertIsNone(conversation.participant_deleted_at)
        self.assertTrue(accessible_conversations_for_user(participant).filter(pk=conversation.pk).exists())

    def test_conversation_is_removed_when_both_users_delete_it(self):
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

        delete_conversation_for_user(conversation, participant)
        delete_conversation_for_user(conversation, listing.owner)

        self.assertFalse(ListingConversation.objects.filter(pk=conversation.pk).exists())

    @override_settings(LISTING_IMAGE_TOTAL_LIMIT=1)
    def test_listing_image_total_limit_applies_to_direct_model_saves(self):
        with TemporaryDirectory() as temp_dir, override_settings(MEDIA_ROOT=temp_dir):
            listing = self.create_listing()
            ListingImage.objects.create(listing=listing, image=self._image_upload("one.png"))

            with self.assertRaises(ValidationError) as exc:
                ListingImage.objects.create(listing=listing, image=self._image_upload("two.png"))

        self.assertIn("Each listing can have up to 1 images total.", exc.exception.message_dict["image"][0])
