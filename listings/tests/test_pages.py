import io
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image

from ..models import ListingImage, ListingInquiry
from .base import ListingTestCase


class ListingPageTests(ListingTestCase):
    def make_image_upload(self, name="photo.png"):
        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), color="white").save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

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

    def test_authenticated_user_can_create_listing(self):
        self.client.force_login(self.user)
        payload = {
            "title": "Quiet dorm near campus",
            "address": "140 Commonwealth Ave",
            "price": "1200.00",
            "lease_type": "FULL",
            "start_date": date(2026, 9, 1),
            "end_date": date(2027, 5, 31),
            "description": "Close to dining hall.",
        }

        response = self.client.post(reverse("listings:create_listing"), payload)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("listings:listing_list"))
        self.assertEqual(self.user.listings.count(), 1)

    def test_create_listing_rejects_end_date_before_start_date(self):
        self.client.force_login(self.user)
        payload = {
            "title": "Quiet dorm near campus",
            "address": "140 Commonwealth Ave",
            "price": "1200.00",
            "lease_type": "FULL",
            "start_date": date(2027, 5, 31),
            "end_date": date(2026, 9, 1),
            "description": "Close to dining hall.",
        }

        response = self.client.post(reverse("listings:create_listing"), payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "End date must be on or after the start date.")
        self.assertEqual(self.user.listings.count(), 0)

    def test_create_listing_rejects_invalid_uploaded_image(self):
        self.client.force_login(self.user)
        payload = {
            "title": "Quiet dorm near campus",
            "address": "140 Commonwealth Ave",
            "price": "1200.00",
            "lease_type": "FULL",
            "start_date": date(2026, 9, 1),
            "end_date": date(2027, 5, 31),
            "description": "Close to dining hall.",
        }
        invalid_upload = SimpleUploadedFile("bad.txt", b"not an image", content_type="text/plain")

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                response = self.client.post(reverse("listings:create_listing"), {**payload, "images": invalid_upload})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload a JPG, PNG, or WebP image.")
        self.assertFalse(self.user.listings.exists())

    def test_listing_owner_can_edit_listing(self):
        listing = self.create_listing()
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
            },
        )

        listing.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("users:posts"))
        self.assertEqual(listing.title, "Updated listing")

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
                        "price": listing.price,
                        "lease_type": listing.lease_type,
                        "start_date": listing.start_date,
                        "end_date": listing.end_date,
                        "property_type": listing.property_type,
                        "images": self.make_image_upload("three.png"),
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Each listing can have up to 2 images total.")
        self.assertEqual(listing.images.count(), 2)

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

        self.assertContains(response, "listing-only account")
        self.assertContains(response, owned_listing.title)
        self.assertNotContains(response, "Student listing")

    def test_realtor_cannot_view_other_listing_detail(self):
        realtor = get_user_model().objects.create_user(username="agent", email="agent@gmail.com", password="test")
        listing = self.create_listing()
        self.client.force_login(realtor)

        response = self.client.get(reverse("listings:detail", args=[listing.pk]))

        self.assertEqual(response.status_code, 404)

    def test_student_can_send_inquiry(self):
        student = get_user_model().objects.create_user(username="student", email="student@bc.edu", password="test")
        listing = self.create_listing()
        self.client.force_login(student)

        response = self.client.post(reverse("listings:inquire", args=[listing.pk]), {"message": "Interested for fall."})

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ListingInquiry.objects.count(), 1)
        inquiry = ListingInquiry.objects.get()
        self.assertEqual(inquiry.sender, student)
        self.assertEqual(inquiry.listing, listing)
        self.assertEqual(inquiry.message, "Interested for fall.")

    def test_realtor_cannot_send_inquiry(self):
        realtor = get_user_model().objects.create_user(username="agent", email="agent@gmail.com", password="test")
        listing = self.create_listing()
        self.client.force_login(realtor)

        response = self.client.post(reverse("listings:inquire", args=[listing.pk]), {"message": "Interested."})

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ListingInquiry.objects.exists())

    def test_inquiry_endpoint_requires_post(self):
        listing = self.create_listing()
        student = get_user_model().objects.create_user(username="student", email="student@bc.edu", password="test")
        self.client.force_login(student)

        response = self.client.get(reverse("listings:inquire", args=[listing.pk]))

        self.assertEqual(response.status_code, 405)
        self.assertFalse(ListingInquiry.objects.exists())

    def test_delete_listing_endpoint_requires_post(self):
        listing = self.create_listing()
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:delete_listing", args=[listing.pk]))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(self.user.listings.filter(pk=listing.pk).exists())

    def test_listing_owner_sees_incoming_inquiries_on_detail_page(self):
        listing = self.create_listing()
        student = get_user_model().objects.create_user(username="student", email="student@bc.edu", password="test")
        ListingInquiry.objects.create(listing=listing, sender=student, message="Can I tour this week?")
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:detail", args=[listing.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Incoming inquiries")
        self.assertContains(response, "Can I tour this week?")
