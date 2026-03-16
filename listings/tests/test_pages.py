from datetime import date

from django.urls import reverse

from .base import ListingTestCase


class ListingPageTests(ListingTestCase):
    def test_listing_pages_render(self):
        listing = self.create_listing()

        for path in (
            reverse("listings:listing_list"),
            reverse("listings:detail", args=[listing.pk]),
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)

    def test_listing_list_includes_detail_page_link(self):
        listing = self.create_listing()

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

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(response, visible_listing.title)
        self.assertNotContains(response, "Hidden listing")

    def test_listing_list_filters_by_budget_and_lease_type(self):
        affordable_listing = self.create_listing(title="Affordable", price="950.00", lease_type="SUBLEASE")
        self.create_listing(title="Expensive", price="2200.00", lease_type="FULL")

        response = self.client.get(
            reverse("listings:listing_list"),
            {"max_price": "1000", "lease_type": "SUBLEASE"},
        )

        self.assertContains(response, affordable_listing.title)
        self.assertNotContains(response, "Expensive")

    def test_listing_list_filters_by_search_query(self):
        matching_listing = self.create_listing(title="Beacon apartment", address="1731 Beacon St")
        self.create_listing(title="Comm Ave house", address="140 Commonwealth Ave")

        response = self.client.get(
            reverse("listings:listing_list"),
            {"q": "Beacon"},
        )

        self.assertContains(response, matching_listing.title)
        self.assertNotContains(response, "Comm Ave house")

    def test_listing_list_is_paginated(self):
        for index in range(13):
            self.create_listing(title=f"Listing {index}")

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
