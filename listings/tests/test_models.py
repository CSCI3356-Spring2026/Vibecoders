from datetime import date, timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from allauth.socialaccount.models import SocialAccount
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.signing import BadSignature, SignatureExpired
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

from ..address_provider import get_geoapify_autocomplete_config, normalize_geoapify_suggestions
from ..address_signing import sign_address_selection, unsign_address_selection
from ..forms import ListingForm
from ..geocoding import geocode_listing_address
from ..models import Listing, ListingFavorite, ListingImage
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

    def test_listing_owner_cannot_favorite_their_own_listing(self):
        listing = self.create_listing()

        with self.assertRaises(ValidationError) as exc:
            ListingFavorite.objects.create(user=self.user, listing=listing)

        self.assertIn("You cannot save your own listing.", exc.exception.message_dict["listing"][0])

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


class ListingGeocodingTests(ListingTestCase):
    def _image_upload(self, name="photo.png"):
        buffer = BytesIO()
        Image.new("RGB", (8, 8), color=(79, 70, 229)).save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    @override_settings(LISTING_GEOCODING_ENABLED=False)
    @patch("listings.geocoding.requests.get")
    def test_geocode_listing_address_returns_none_without_network_when_disabled(self, requests_get_mock):
        latitude, longitude = geocode_listing_address("140 Commonwealth Ave")

        self.assertIsNone(latitude)
        self.assertIsNone(longitude)
        requests_get_mock.assert_not_called()

    @override_settings(
        LISTING_GEOCODING_ENABLED=True,
        LISTING_GEOCODER_URL="https://photon.example/api/",
        LISTING_GEOCODER_USER_AGENT="PadlyTests/1.0",
        LISTING_GEOCODER_TIMEOUT_SECONDS=7,
    )
    @patch("listings.geocoding.requests.get")
    def test_geocode_listing_address_parses_first_feature_coordinates(self, requests_get_mock):
        response_mock = Mock()
        response_mock.raise_for_status.return_value = None
        response_mock.json.return_value = {
            "features": [
                {"geometry": {"coordinates": [-71.1685, 42.3355]}},
            ]
        }
        requests_get_mock.return_value = response_mock

        latitude, longitude = geocode_listing_address("140 Commonwealth Ave")

        self.assertEqual((latitude, longitude), (42.3355, -71.1685))
        requests_get_mock.assert_called_once_with(
            "https://photon.example/api/",
            params={"q": "140 Commonwealth Ave", "limit": 1, "lat": 42.3355, "lon": -71.1685},
            headers={"User-Agent": "PadlyTests/1.0"},
            timeout=7,
        )

    @override_settings(LISTING_GEOCODING_ENABLED=True)
    @patch("listings.geocoding.requests.get")
    def test_geocode_listing_address_rejects_invalid_coordinate_payload(self, requests_get_mock):
        response_mock = Mock()
        response_mock.raise_for_status.return_value = None
        response_mock.json.return_value = {
            "features": [
                {"geometry": {"coordinates": ["not-a-number", "still-not-a-number"]}},
            ]
        }
        requests_get_mock.return_value = response_mock

        latitude, longitude = geocode_listing_address("140 Commonwealth Ave")

        self.assertIsNone(latitude)
        self.assertIsNone(longitude)

    @override_settings(LISTING_IMAGE_TOTAL_LIMIT=1)
    def test_listing_image_total_limit_applies_to_direct_model_saves(self):
        with TemporaryDirectory() as temp_dir, override_settings(MEDIA_ROOT=temp_dir):
            listing = self.create_listing()
            ListingImage.objects.create(listing=listing, image=self._image_upload("one.png"))

            with self.assertRaises(ValidationError) as exc:
                ListingImage.objects.create(listing=listing, image=self._image_upload("two.png"))

        self.assertIn("Each listing can have up to 1 images total.", exc.exception.message_dict["image"][0])


class ListingAddressPrimitiveTests(ListingTestCase):
    @override_settings(
        LISTING_MAPS_ENABLED=False,
        LISTING_GEOAPIFY_API_KEY="geoapify-test-key",
        LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
    )
    def test_geoapify_config_is_enabled_without_map_browsing_ui(self):
        config = get_geoapify_autocomplete_config()

        self.assertEqual(
            config,
            {
                "enabled": True,
                "url": "https://api.geoapify.com/v1/geocode/autocomplete",
                "api_key": "geoapify-test-key",
            },
        )

    @override_settings(
        LISTING_MAPS_ENABLED=True,
        LISTING_GEOAPIFY_API_KEY="",
        LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
    )
    def test_geoapify_config_fails_closed_without_api_key(self):
        config = get_geoapify_autocomplete_config()

        self.assertEqual(
            config,
            {
                "enabled": False,
                "url": None,
                "api_key": None,
            },
        )

    def test_address_selection_token_round_trip_preserves_normalized_payload(self):
        payload = {
            "provider_id": "geoapify:place:123",
            "label": "140 Commonwealth Ave, Chestnut Hill, MA 02467",
            "address_line_1": "140 Commonwealth Ave",
            "address_line_2": "",
            "city": "Chestnut Hill",
            "state": "MA",
            "postal_code": "02467",
            "country": "US",
            "latitude": 42.3355,
            "longitude": -71.1685,
        }

        token = sign_address_selection(payload)

        self.assertEqual(unsign_address_selection(token, max_age=60), payload)

    def test_address_selection_token_rejects_expired_or_tampered_values(self):
        payload = {
            "provider_id": "geoapify:place:123",
            "label": "140 Commonwealth Ave, Chestnut Hill, MA 02467",
            "address_line_1": "140 Commonwealth Ave",
            "address_line_2": "",
            "city": "Chestnut Hill",
            "state": "MA",
            "postal_code": "02467",
            "country": "US",
            "latitude": 42.3355,
            "longitude": -71.1685,
        }
        token = sign_address_selection(payload)

        with self.assertRaises(SignatureExpired):
            unsign_address_selection(token, max_age=-1)

        with self.assertRaises(BadSignature):
            unsign_address_selection(f"{token}tampered", max_age=60)

    def test_geoapify_normalization_returns_minimal_suggestion_shape(self):
        payload = {
            "results": [
                {
                    "place_id": "abc123",
                    "formatted": "140 Commonwealth Ave, Chestnut Hill, MA 02467, United States of America",
                    "address_line1": "140 Commonwealth Ave",
                    "address_line2": "",
                    "city": "Chestnut Hill",
                    "state_code": "MA",
                    "postcode": "02467",
                    "country_code": "us",
                    "lat": 42.3355,
                    "lon": -71.1685,
                    "timezone": {"name": "America/New_York"},
                    "rank": {"confidence": 0.99},
                }
            ]
        }

        self.assertEqual(
            normalize_geoapify_suggestions(payload),
            [
                {
                    "provider_id": "geoapify:abc123",
                    "label": "140 Commonwealth Ave, Chestnut Hill, MA 02467",
                    "address_line_1": "140 Commonwealth Ave",
                    "address_line_2": "",
                    "city": "Chestnut Hill",
                    "state": "MA",
                    "postal_code": "02467",
                    "country": "US",
                    "primary_label": "140 Commonwealth Ave",
                    "latitude": 42.3355,
                    "longitude": -71.1685,
                }
            ],
        )

    def test_geoapify_normalization_returns_empty_list_for_malformed_payload_items(self):
        payload = {
            "results": [
                "not-a-dict",
                None,
                {"formatted": "missing place id"},
            ]
        }

        self.assertEqual(normalize_geoapify_suggestions(payload), [])

    def test_geoapify_normalization_accepts_fallback_address_fields_without_postcode(self):
        payload = {
            "results": [
                {
                    "place_id": "fallback-1",
                    "formatted": "",
                    "housenumber": "15",
                    "street": "Chiswick Rd",
                    "suburb": "Brighton",
                    "state": "Massachusetts",
                    "state_code": "MA",
                    "country": "United States",
                    "country_code": "us",
                    "lat": 42.3477,
                    "lon": -71.1538,
                }
            ]
        }

        self.assertEqual(
            normalize_geoapify_suggestions(payload),
            [
                {
                    "provider_id": "geoapify:fallback-1",
                    "label": "15 Chiswick Rd, Brighton, MA",
                    "address_line_1": "15 Chiswick Rd",
                    "address_line_2": "",
                    "city": "Brighton",
                    "state": "MA",
                    "postal_code": "",
                    "country": "US",
                    "primary_label": "15 Chiswick Rd",
                    "latitude": 42.3477,
                    "longitude": -71.1538,
                }
            ],
        )

    def test_geoapify_normalization_accepts_geojson_feature_payload_and_dedupes_duplicate_address_matches(self):
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "place_id": "building-1",
                        "formatted": "140 Commonwealth Avenue, Newton, MA 02467, United States of America",
                        "address_line1": "140 Commonwealth Avenue",
                        "housenumber": "140",
                        "street": "Commonwealth Avenue",
                        "city": "Newton",
                        "state_code": "MA",
                        "postcode": "02467",
                        "country_code": "us",
                    },
                    "geometry": {"type": "Point", "coordinates": [-71.168984, 42.33806]},
                },
                {
                    "type": "Feature",
                    "properties": {
                        "place_id": "amenity-1",
                        "formatted": (
                            "Boston College Chestnut Hill Campus, 140 Commonwealth Avenue, Newton, MA 02467, "
                            "United States of America"
                        ),
                        "address_line1": "Boston College Chestnut Hill Campus",
                        "housenumber": "140",
                        "street": "Commonwealth Avenue",
                        "city": "Newton",
                        "state_code": "MA",
                        "postcode": "02467",
                        "country_code": "us",
                    },
                    "geometry": {"type": "Point", "coordinates": [-71.1682664, 42.3354481]},
                },
            ],
        }

        self.assertEqual(
            normalize_geoapify_suggestions(payload),
            [
                {
                    "provider_id": "geoapify:building-1",
                    "label": "140 Commonwealth Avenue, Newton, MA 02467",
                    "address_line_1": "140 Commonwealth Avenue",
                    "address_line_2": "",
                    "city": "Newton",
                    "state": "MA",
                    "postal_code": "02467",
                    "country": "US",
                    "primary_label": "140 Commonwealth Avenue",
                    "latitude": 42.33806,
                    "longitude": -71.168984,
                }
            ],
        )
