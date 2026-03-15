from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

# -----------------------------------------------------------------------------
# View tests
# -----------------------------------------------------------------------------


# Basic smoke tests to ensure listing-related pages render without error
class ListingPageTests(TestCase):
    def test_listing_pages_render(self):
        for path in ("/listings/", "/listings/detail/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)

    def test_listing_list_omits_hidden_listings(self):
        user = get_user_model().objects.create_user(username="owner", password="testpass123")
        visible_listing = user.listings.create(
            title="Visible listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            description="Visible",
            is_hidden=False,
        )
        user.listings.create(
            title="Hidden listing",
            address="200 Beacon St",
            price="1400.00",
            lease_type="SUBLEASE",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            description="Hidden",
            is_hidden=True,
        )

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(response, visible_listing.title)
        self.assertNotContains(response, "Hidden listing")

    def test_create_listing_requires_login(self):
        response = self.client.get("/listings/create/")
        self.assertEqual(response.status_code, 302)

    def test_create_listing_renders_for_authenticated_user(self):
        user = get_user_model().objects.create_user(
            username="testuser",
            password="testpass123",
        )
        self.client.force_login(user)
        response = self.client.get(reverse("listings:create_listing"))
        self.assertEqual(response.status_code, 200)

    def test_authenticated_user_can_create_listing(self):
        user = get_user_model().objects.create_user(
            username="testuser",
            password="testpass123",
        )
        self.client.force_login(user)
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
        self.assertEqual(user.listings.count(), 1)

    def test_create_listing_rejects_end_date_before_start_date(self):
        user = get_user_model().objects.create_user(
            username="testuser",
            password="testpass123",
        )
        self.client.force_login(user)
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
        self.assertEqual(user.listings.count(), 0)
