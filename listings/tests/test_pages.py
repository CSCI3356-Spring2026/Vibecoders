import io
import tempfile
from datetime import date, timedelta
from unittest.mock import patch

from allauth.socialaccount.models import SocialAccount
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image

from communications.models import ListingConversation, ListingMessage
from users.models import Role

from ..address_signing import sign_address_selection, unsign_address_selection
from ..models import Listing, ListingImage
from .base import ListingTestCase


@override_settings(
    LISTING_GEOAPIFY_API_KEY="geoapify-test-key",
    LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
)
class ListingPageTests(ListingTestCase):
    def make_verified_address_token(
        self,
        *,
        label="140 Commonwealth Ave, Chestnut Hill, MA 02467, US",
        address_line_1="140 Commonwealth Ave",
        city="Chestnut Hill",
        state="MA",
        postal_code="02467",
        country="US",
        latitude=42.3355,
        longitude=-71.1685,
        provider_id="geoapify:place-140-commonwealth",
    ):
        return sign_address_selection(
            {
                "provider_id": provider_id,
                "label": label,
                "address_line_1": address_line_1,
                "address_line_2": "",
                "city": city,
                "state": state,
                "postal_code": postal_code,
                "country": country,
                "latitude": latitude,
                "longitude": longitude,
            }
        )

    def listing_payload(self, **overrides):
        payload = {
            "title": "Quiet dorm near campus",
            "address": "140 Commonwealth Ave, Chestnut Hill, MA 02467, US",
            "verified_address_token": self.make_verified_address_token(),
            "price": "1200.00",
            "lease_type": "FULL",
            "start_date": date(2026, 9, 1),
            "end_date": date(2027, 5, 31),
            "description": "Close to dining hall.",
        }
        payload.update(overrides)
        return payload

    def make_image_upload(self, name="photo.png"):
        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), color="white").save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    @override_settings(
        LISTING_GEOAPIFY_API_KEY="geoapify-test-key",
        LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
    )
    @patch("requests.get")
    def test_address_autocomplete_endpoint_returns_signed_suggestions_for_valid_query(self, requests_get):
        requests_get.return_value.json.return_value = {
            "results": [
                {
                    "place_id": "geoapify-place-1",
                    "formatted": "140 Commonwealth Ave, Chestnut Hill, MA 02467, United States",
                    "address_line1": "140 Commonwealth Ave",
                    "address_line2": "",
                    "city": "Chestnut Hill",
                    "state_code": "MA",
                    "postcode": "02467",
                    "country_code": "us",
                    "lat": 42.3355,
                    "lon": -71.1685,
                }
            ]
        }
        requests_get.return_value.raise_for_status.return_value = None
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:address_suggestions"), {"q": "140 Commonwealth"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["results"]), 1)
        result = payload["results"][0]
        self.assertEqual(result["label"], "140 Commonwealth Ave, Chestnut Hill, MA 02467, United States")
        self.assertEqual(result["address_line_1"], "140 Commonwealth Ave")
        self.assertEqual(result["latitude"], 42.3355)
        self.assertEqual(result["longitude"], -71.1685)
        self.assertIn("token", result)
        signed_payload = unsign_address_selection(result["token"], max_age=300)
        self.assertEqual(signed_payload["provider_id"], "geoapify:geoapify-place-1")
        self.assertEqual(signed_payload["address_line_1"], "140 Commonwealth Ave")
        requests_get.assert_called_once()

    @override_settings(
        LISTING_GEOAPIFY_API_KEY="geoapify-test-key",
        LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
    )
    @patch("requests.get")
    def test_address_autocomplete_endpoint_returns_empty_results_for_blank_or_short_query(self, requests_get):
        self.client.force_login(self.user)

        blank_response = self.client.get(reverse("listings:address_suggestions"), {"q": ""})
        short_response = self.client.get(reverse("listings:address_suggestions"), {"q": "12"})

        self.assertEqual(blank_response.status_code, 200)
        self.assertEqual(blank_response.json(), {"results": []})
        self.assertEqual(short_response.status_code, 200)
        self.assertEqual(short_response.json(), {"results": []})
        requests_get.assert_not_called()

    @override_settings(
        LISTING_GEOAPIFY_API_KEY="geoapify-test-key",
        LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
    )
    @patch("requests.get", side_effect=Exception("provider unavailable"))
    def test_address_autocomplete_endpoint_returns_retry_friendly_inline_error_contract(self, requests_get):
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:address_suggestions"), {"q": "140 Commonwealth"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "results": [],
                "error": {
                    "message": "Address suggestions are temporarily unavailable. Try again.",
                    "retryable": True,
                },
            },
        )
        requests_get.assert_called_once()

    @override_settings(LISTING_ADDRESS_AUTOCOMPLETE_RATE_LIMIT=1, LISTING_ADDRESS_AUTOCOMPLETE_RATE_WINDOW_SECONDS=60)
    @patch("requests.get")
    def test_address_autocomplete_endpoint_throttles_repeat_requests(self, requests_get):
        requests_get.return_value.json.return_value = {
            "results": [
                {
                    "place_id": "geoapify-place-1",
                    "formatted": "140 Commonwealth Ave, Chestnut Hill, MA 02467, United States",
                    "address_line1": "140 Commonwealth Ave",
                    "address_line2": "",
                    "city": "Chestnut Hill",
                    "state_code": "MA",
                    "postcode": "02467",
                    "country_code": "us",
                    "lat": 42.3355,
                    "lon": -71.1685,
                }
            ]
        }
        requests_get.return_value.raise_for_status.return_value = None
        cache.clear()
        self.client.force_login(self.user)

        first_response = self.client.get(reverse("listings:address_suggestions"), {"q": "140 Commonwealth"})
        second_response = self.client.get(reverse("listings:address_suggestions"), {"q": "140 Commonwealth"})

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 429)
        self.assertEqual(
            second_response.json(),
            {
                "results": [],
                "error": {
                    "message": "Too many address lookups. Wait a moment and try again.",
                    "retryable": True,
                },
            },
        )
        requests_get.assert_called_once()

    def test_listing_pages_require_login(self):
        listing = self.create_listing()

        for path in (
            reverse("listings:listing_list"),
            reverse("listings:detail", args=[listing.pk]),
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/accounts/login/", response.url)

    def test_listing_pages_render_for_authenticated_user(self):
        listing = self.create_listing()
        self.client.force_login(self.user)

        for path in (
            reverse("listings:listing_list"),
            reverse("listings:detail", args=[listing.pk]),
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)

    def test_listing_list_includes_detail_page_link(self):
        listing = self.create_listing()
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(response, reverse("listings:detail", args=[listing.pk]))

    def test_listing_list_context_includes_map_data_for_geocoded_results(self):
        mapped_listing = self.create_listing(title="Mapped listing", latitude=42.3355, longitude=-71.1685)
        self.create_listing(title="Unmapped listing", address="200 Beacon St")
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(response, "data-listing-map-root")
        map_data = response.context["map_data"]
        self.assertEqual(len(map_data), 1)
        self.assertEqual(map_data[0]["title"], mapped_listing.title)
        self.assertEqual(map_data[0]["url"], reverse("listings:detail", args=[mapped_listing.pk]))
        self.assertAlmostEqual(map_data[0]["lat"], 42.3355)
        self.assertAlmostEqual(map_data[0]["lng"], -71.1685)

    @override_settings(LISTING_MAPS_ENABLED=False)
    def test_listing_list_hides_map_when_feature_flag_is_disabled(self):
        self.create_listing(title="Mapped listing", latitude=42.3355, longitude=-71.1685)
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertNotContains(response, "data-listing-map-root")
        self.assertEqual(response.context["map_data"], [])

    def test_listing_list_shows_owner_avatar(self):
        self.user.profile_image_url = "https://example.com/owner-avatar.jpg"
        self.user.save(update_fields=["profile_image_url"])
        self.create_listing()
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(response, "https://example.com/owner-avatar.jpg")

    def test_listing_list_omits_hidden_listings(self):
        visible_listing = self.create_listing(
            title="Visible listing",
            description="Visible",
            is_hidden=False,
        )
        self.create_listing(
            title="Hidden listing",
            address="200 Beacon St",
            price="1400.00",
            lease_type="SUBLEASE",
            description="Hidden",
            is_hidden=True,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(response, visible_listing.title)
        self.assertNotContains(response, "Hidden listing")

    def test_listing_list_omits_taken_and_expired_listings(self):
        today = date.today()
        visible_listing = self.create_listing(title="Visible listing")
        self.create_listing(
            title="Taken listing",
            address="200 Beacon St",
            price="1400.00",
            lease_type="SUBLEASE",
            description="Taken",
            status=Listing.STATUS_TAKEN,
        )
        self.create_listing(
            title="Expired listing",
            address="300 Beacon St",
            price="1500.00",
            lease_type="FULL",
            description="Expired",
            start_date=today - timedelta(days=90),
            end_date=today - timedelta(days=30),
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(response, visible_listing.title)
        self.assertNotContains(response, "Taken listing")
        self.assertNotContains(response, "Expired listing")

    def test_listing_list_shows_owner_avatar_when_available(self):
        listing = self.create_listing()
        SocialAccount.objects.create(
            user=self.user,
            provider="google",
            uid="google-owner",
            extra_data={"picture": "https://example.com/listing-owner.png"},
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(response, listing.owner.display_name)
        self.assertContains(response, "https://example.com/listing-owner.png")

    def test_listing_list_filters_by_budget_and_lease_type(self):
        affordable_listing = self.create_listing(title="Affordable", price="950.00", lease_type="SUBLEASE")
        self.create_listing(title="Expensive", price="2200.00", lease_type="FULL")
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("listings:listing_list"),
            {"max_price": "1000", "lease_type": "SUBLEASE"},
        )

        self.assertContains(response, affordable_listing.title)
        self.assertNotContains(response, "Expensive")

    def test_listing_list_filters_by_search_query(self):
        matching_listing = self.create_listing(title="Beacon apartment", address="1731 Beacon St")
        self.create_listing(title="Comm Ave house", address="140 Commonwealth Ave")
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("listings:listing_list"),
            {"q": "Beacon"},
        )

        self.assertContains(response, matching_listing.title)
        self.assertNotContains(response, "Comm Ave house")

    def test_listing_list_ignores_invalid_max_price_filter(self):
        listing = self.create_listing(title="Beacon apartment", price="1800.00")
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"), {"max_price": "invalid"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, listing.title)

    def test_listing_list_is_paginated(self):
        for index in range(13):
            self.create_listing(title=f"Listing {index}")
        self.client.force_login(self.user)

        first_page = self.client.get(reverse("listings:listing_list"))
        second_page = self.client.get(reverse("listings:listing_list"), {"page": 2})

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(second_page.status_code, 200)
        self.assertNotContains(first_page, "Listing 0")
        self.assertContains(second_page, "Listing 0")

    def test_create_listing_requires_login(self):
        response = self.client.get(reverse("listings:create_listing"))

        self.assertEqual(response.status_code, 302)

    def test_create_listing_renders_for_authenticated_user(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:create_listing"))

        self.assertEqual(response.status_code, 200)

    def test_create_listing_uses_guided_wizard_flow(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:create_listing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-listing-form-wizard")
        self.assertContains(response, 'data-step-panel="0"')
        self.assertContains(response, "data-step-next")
        self.assertContains(response, "Publishing flow")

    def test_create_listing_renders_verified_address_picker_contract(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:create_listing"))

        self.assertContains(response, "data-address-picker")
        self.assertContains(response, "data-address-input")
        self.assertContains(response, "data-address-token-input")
        self.assertContains(response, "data-address-suggestions")
        self.assertContains(response, "data-address-status")
        self.assertContains(response, reverse("listings:address_suggestions"))

    def test_authenticated_user_can_create_listing(self):
        self.client.force_login(self.user)
        payload = self.listing_payload(
            utilities_estimate="90.00",
            security_deposit="1200.00",
        )

        response = self.client.post(reverse("listings:create_listing"), payload)

        self.assertEqual(response.status_code, 302)
        created_listing = self.user.listings.get()
        self.assertEqual(response["Location"], reverse("listings:detail", args=[created_listing.pk]))
        self.assertEqual(self.user.listings.count(), 1)
        self.assertEqual(created_listing.utilities_estimate, 90)
        self.assertEqual(created_listing.security_deposit, 1200)

    def test_authenticated_user_can_create_listing_and_persist_verified_coordinates(self):
        self.client.force_login(self.user)
        payload = self.listing_payload()

        response = self.client.post(reverse("listings:create_listing"), payload)

        self.assertEqual(response.status_code, 302)
        created_listing = self.user.listings.get()
        self.assertAlmostEqual(created_listing.latitude, 42.3355)
        self.assertAlmostEqual(created_listing.longitude, -71.1685)

    def test_create_listing_rejects_submission_without_selected_signed_token(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("listings:create_listing"),
            self.listing_payload(verified_address_token=""),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "address", "Select a verified address suggestion.")
        self.assertFalse(self.user.listings.exists())

    def test_create_listing_rejects_end_date_before_start_date(self):
        self.client.force_login(self.user)
        payload = self.listing_payload(
            start_date=date(2027, 5, 31),
            end_date=date(2026, 9, 1),
        )

        response = self.client.post(reverse("listings:create_listing"), payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "End date must be on or after the start date.")
        self.assertEqual(self.user.listings.count(), 0)

    def test_create_listing_rejects_invalid_uploaded_image(self):
        self.client.force_login(self.user)
        payload = self.listing_payload()
        invalid_upload = SimpleUploadedFile("bad.txt", b"not an image", content_type="text/plain")

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                response = self.client.post(reverse("listings:create_listing"), {**payload, "images": invalid_upload})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload a JPG, PNG, or WebP image.")
        self.assertFalse(self.user.listings.exists())

    def test_create_listing_can_save_multiple_images(self):
        self.client.force_login(self.user)
        payload = self.listing_payload(images=[self.make_image_upload("one.png"), self.make_image_upload("two.png")])

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                response = self.client.post(reverse("listings:create_listing"), payload)

        self.assertEqual(response.status_code, 302)
        listing = self.user.listings.get()
        self.assertEqual(listing.images.count(), 2)

    def test_listing_owner_can_edit_listing(self):
        listing = self.create_listing(latitude=42.3355, longitude=-71.1685)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("listings:edit_listing", args=[listing.pk]),
            {
                "title": "Updated listing",
                "address": listing.address,
                "price": listing.price,
                "lease_type": listing.lease_type,
                "start_date": listing.start_date,
                "end_date": listing.end_date,
                "property_type": listing.property_type,
                "description": listing.description,
                "status": "PENDING",
            },
        )

        listing.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("listings:detail", args=[listing.pk]))
        self.assertEqual(listing.title, "Updated listing")
        self.assertEqual(listing.status, "PENDING")

    @override_settings(
        LISTING_GEOAPIFY_API_KEY="",
        LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
    )
    def test_listing_owner_can_edit_listing_with_unchanged_address_without_token_when_lookup_is_unavailable(self):
        listing = self.create_listing(latitude=42.3355, longitude=-71.1685)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("listings:edit_listing", args=[listing.pk]),
            {
                "title": "Updated listing",
                "address": listing.address,
                "price": listing.price,
                "lease_type": listing.lease_type,
                "start_date": listing.start_date,
                "end_date": listing.end_date,
                "property_type": listing.property_type,
                "description": listing.description,
                "status": listing.status,
            },
        )

        listing.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(listing.title, "Updated listing")
        self.assertEqual(listing.latitude, 42.3355)
        self.assertEqual(listing.longitude, -71.1685)

    @override_settings(
        LISTING_GEOAPIFY_API_KEY="",
        LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
    )
    def test_listing_owner_cannot_bypass_verified_address_on_unchanged_edit_without_coordinates(self):
        listing = self.create_listing(latitude=None, longitude=None)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("listings:edit_listing", args=[listing.pk]),
            {
                "title": "Updated listing",
                "address": listing.address,
                "price": listing.price,
                "lease_type": listing.lease_type,
                "start_date": listing.start_date,
                "end_date": listing.end_date,
                "property_type": listing.property_type,
                "description": listing.description,
                "status": listing.status,
            },
        )

        listing.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "address", "Verified address lookup is unavailable right now. Try again later."
        )
        self.assertEqual(listing.title, "Test listing")
        self.assertIsNone(listing.latitude)
        self.assertIsNone(listing.longitude)

    def test_listing_owner_edit_rejects_changed_freeform_address_without_reselection(self):
        listing = self.create_listing(latitude=42.3355, longitude=-71.1685)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("listings:edit_listing", args=[listing.pk]),
            {
                "title": listing.title,
                "address": "215 Commonwealth Ave",
                "verified_address_token": self.make_verified_address_token(label=listing.address),
                "price": listing.price,
                "lease_type": listing.lease_type,
                "start_date": listing.start_date,
                "end_date": listing.end_date,
                "property_type": listing.property_type,
                "description": listing.description,
                "status": listing.status,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "address",
            "Choose the updated address from the verified suggestions.",
        )

    @override_settings(
        LISTING_GEOAPIFY_API_KEY="",
        LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
    )
    def test_missing_geoapify_config_blocks_authoring_instead_of_silently_falling_back(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("listings:create_listing"), self.listing_payload())

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "address", "Verified address lookup is unavailable right now. Try again later."
        )
        self.assertFalse(self.user.listings.exists())

    def test_listing_detail_shows_owner_avatar_when_available(self):
        listing = self.create_listing()
        SocialAccount.objects.create(
            user=self.user,
            provider="google",
            uid="google-owner-detail",
            extra_data={"picture": "https://example.com/listing-owner-detail.png"},
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:detail", args=[listing.pk]))

        self.assertContains(response, listing.owner.display_name)
        self.assertContains(response, "https://example.com/listing-owner-detail.png")

    def test_edit_listing_rejects_total_image_limit(self):
        listing = self.create_listing()
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir, LISTING_IMAGE_TOTAL_LIMIT=2):
                ListingImage.objects.create(listing=listing, image=self.make_image_upload("one.png"))
                ListingImage.objects.create(listing=listing, image=self.make_image_upload("two.png"))

                response = self.client.post(
                    reverse("listings:edit_listing", args=[listing.pk]),
                    {
                        "title": listing.title,
                        "address": listing.address,
                        "verified_address_token": self.make_verified_address_token(label=listing.address),
                        "price": listing.price,
                        "lease_type": listing.lease_type,
                        "start_date": listing.start_date,
                        "end_date": listing.end_date,
                        "property_type": listing.property_type,
                        "description": listing.description,
                        "images": self.make_image_upload("three.png"),
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Each listing can have up to 2 images total.")
        self.assertEqual(listing.images.count(), 2)

    def test_edit_listing_can_remove_existing_images(self):
        listing = self.create_listing()
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                image_one = ListingImage.objects.create(listing=listing, image=self.make_image_upload("one.png"))
                image_two = ListingImage.objects.create(listing=listing, image=self.make_image_upload("two.png"))

                response = self.client.post(
                    reverse("listings:edit_listing", args=[listing.pk]),
                    {
                        "title": listing.title,
                        "address": listing.address,
                        "verified_address_token": self.make_verified_address_token(label=listing.address),
                        "price": listing.price,
                        "lease_type": listing.lease_type,
                        "start_date": listing.start_date,
                        "end_date": listing.end_date,
                        "property_type": listing.property_type,
                        "description": listing.description,
                        "remove_images": [str(image_one.pk)],
                    },
                )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(listing.images.count(), 1)
        self.assertFalse(listing.images.filter(pk=image_one.pk).exists())
        self.assertTrue(listing.images.filter(pk=image_two.pk).exists())

    def test_listing_owner_can_delete_listing(self):
        listing = self.create_listing()
        self.client.force_login(self.user)

        response = self.client.post(reverse("listings:delete_listing", args=[listing.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("users:posts"))
        self.assertFalse(self.user.listings.filter(pk=listing.pk).exists())

    def test_delete_listing_cleans_up_image_files(self):
        listing = self.create_listing()
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                listing_image = ListingImage.objects.create(
                    listing=listing, image=self.make_image_upload("cleanup.png")
                )
                stored_name = listing_image.image.name

                self.assertTrue(listing.images.exists())
                self.assertTrue(listing_image.image.storage.exists(stored_name))

                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.post(reverse("listings:delete_listing", args=[listing.pk]))

                self.assertEqual(response.status_code, 302)
                self.assertFalse(listing_image.image.storage.exists(stored_name))

    def test_realtor_listing_list_shows_only_owned_listings(self):
        realtor = get_user_model().objects.create_user(username="agent", email="agent@gmail.com", password="test")
        owned_listing = realtor.listings.create(
            title="Owned listing",
            address="10 Main St",
            price="2100.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
        )
        self.create_listing(title="Student listing", address="20 Main St")
        self.client.force_login(realtor)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(response, "This account can manage its own listings only.")
        self.assertContains(response, owned_listing.title)
        self.assertNotContains(response, "Student listing")

    def test_realtor_cannot_view_other_listing_detail(self):
        realtor = get_user_model().objects.create_user(username="agent", email="agent@gmail.com", password="test")
        listing = self.create_listing()
        self.client.force_login(realtor)

        response = self.client.get(reverse("listings:detail", args=[listing.pk]))

        self.assertEqual(response.status_code, 404)

    def test_listing_owner_can_view_own_taken_listing_detail(self):
        listing = self.create_listing(status=Listing.STATUS_TAKEN)
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:detail", args=[listing.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, listing.title)

    def test_student_can_start_listing_conversation(self):
        student = get_user_model().objects.create_user(username="student", email="student@bc.edu", password="test")
        listing = self.create_listing()
        self.client.force_login(student)

        response = self.client.post(
            reverse("listings:message_listing", args=[listing.pk]),
            {"body": "Interested for fall."},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ListingConversation.objects.count(), 1)
        self.assertEqual(ListingMessage.objects.count(), 1)
        conversation = ListingConversation.objects.get()
        self.assertEqual(conversation.participant, student)
        self.assertEqual(conversation.owner, listing.owner)
        self.assertEqual(conversation.listing, listing)
        self.assertEqual(conversation.last_message_preview, "Interested for fall.")
        self.assertTrue(conversation.owner_has_unread_messages)
        self.assertFalse(conversation.participant_has_unread_messages)
        message = ListingMessage.objects.get()
        self.assertEqual(message.sender, student)
        self.assertEqual(message.body, "Interested for fall.")

    def test_student_reuses_existing_listing_conversation(self):
        student = get_user_model().objects.create_user(username="student", email="student@bc.edu", password="test")
        listing = self.create_listing()
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=listing.owner,
            participant=student,
        )
        conversation.add_message(sender=student, body="First note.")
        self.client.force_login(student)

        response = self.client.post(
            reverse("listings:message_listing", args=[listing.pk]),
            {"body": "Following up on availability."},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ListingConversation.objects.count(), 1)
        self.assertEqual(ListingMessage.objects.count(), 2)
        conversation.refresh_from_db()
        self.assertEqual(conversation.last_message_preview, "Following up on availability.")

    @override_settings(MESSAGE_SEND_RATE_LIMIT=1, MESSAGE_SEND_RATE_WINDOW_SECONDS=60)
    def test_student_message_rate_limit_blocks_follow_up_post(self):
        student = get_user_model().objects.create_user(username="student", email="student@bc.edu", password="test")
        listing = self.create_listing()
        self.client.force_login(student)
        cache.clear()

        first_response = self.client.post(
            reverse("listings:message_listing", args=[listing.pk]),
            {"body": "Interested for fall."},
            follow=False,
        )
        second_response = self.client.post(
            reverse("listings:message_listing", args=[listing.pk]),
            {"body": "Following up."},
            follow=True,
        )

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 200)
        self.assertContains(second_response, "Too many messages sent too quickly. Wait a minute and try again.")
        self.assertEqual(ListingMessage.objects.count(), 1)

    def test_realtor_cannot_start_listing_conversation(self):
        realtor = get_user_model().objects.create_user(username="agent", email="agent@gmail.com", password="test")
        listing = self.create_listing()
        self.client.force_login(realtor)

        response = self.client.post(reverse("listings:message_listing", args=[listing.pk]), {"body": "Interested."})

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ListingConversation.objects.exists())

    def test_blank_message_does_not_create_conversation(self):
        student = get_user_model().objects.create_user(username="student", email="student@bc.edu", password="test")
        listing = self.create_listing()
        self.client.force_login(student)

        response = self.client.post(reverse("listings:message_listing", args=[listing.pk]), {"body": "   "})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ListingConversation.objects.exists())

    def test_message_endpoint_requires_post(self):
        listing = self.create_listing()
        student = get_user_model().objects.create_user(username="student", email="student@bc.edu", password="test")
        self.client.force_login(student)

        response = self.client.get(reverse("listings:message_listing", args=[listing.pk]))

        self.assertEqual(response.status_code, 405)
        self.assertFalse(ListingConversation.objects.exists())

    def test_delete_listing_endpoint_requires_post(self):
        listing = self.create_listing()
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:delete_listing", args=[listing.pk]))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(self.user.listings.filter(pk=listing.pk).exists())

    def test_student_cannot_message_taken_listing(self):
        student = get_user_model().objects.create_user(username="student", email="student@bc.edu", password="test")
        listing = self.create_listing(status=Listing.STATUS_TAKEN)
        self.client.force_login(student)

        response = self.client.post(reverse("listings:message_listing", args=[listing.pk]), {"body": "Interested."})

        self.assertEqual(response.status_code, 404)
        self.assertFalse(ListingConversation.objects.exists())

    def test_admin_can_start_listing_conversation_for_public_listing(self):
        admin = get_user_model().objects.create_user(
            username="admin",
            email="admin@bc.edu",
            password="test",
            role=Role.ADMIN,
        )
        listing = self.create_listing()
        self.client.force_login(admin)

        response = self.client.post(
            reverse("listings:message_listing", args=[listing.pk]),
            {"body": "I need to follow up on this listing."},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ListingConversation.objects.count(), 1)
        conversation = ListingConversation.objects.get()
        self.assertEqual(conversation.participant, admin)
        self.assertEqual(conversation.listing, listing)

    def test_admin_non_public_listing_post_redirects_with_error_instead_of_404(self):
        admin = get_user_model().objects.create_user(
            username="admin",
            email="admin@bc.edu",
            password="test",
            role=Role.ADMIN,
        )
        listing = self.create_listing(status=Listing.STATUS_TAKEN)
        self.client.force_login(admin)

        response = self.client.post(
            reverse("listings:message_listing", args=[listing.pk]),
            {"body": "Still available?"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This listing is no longer accepting new messages.")
        self.assertContains(response, "This listing is no longer accepting new conversations.")
        self.assertFalse(ListingConversation.objects.exists())

    def test_listing_owner_sees_conversations_on_detail_page(self):
        listing = self.create_listing()
        student = get_user_model().objects.create_user(username="student", email="student@bc.edu", password="test")
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=listing.owner,
            participant=student,
        )
        conversation.add_message(sender=student, body="Can I tour this week?")
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:detail", args=[listing.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Conversation threads")
        self.assertContains(response, "Can I tour this week?")

    def test_listing_detail_shows_owner_avatar(self):
        self.user.profile_image_url = "https://example.com/owner-avatar.jpg"
        self.user.save(update_fields=["profile_image_url"])
        listing = self.create_listing()
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:detail", args=[listing.pk]))

        self.assertContains(response, "https://example.com/owner-avatar.jpg")
