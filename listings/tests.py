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
