from datetime import date
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class CorePageTests(TestCase):
    def test_root_page_renders(self):
        response = self.client.get(reverse("core:landing"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/landing.html")
        self.assertContains(response, "Padly")
        self.assertContains(response, "Terms of Service")
        self.assertContains(response, "Privacy Policy")
        self.assertContains(response, 'class="landing-page-body"')

    def test_root_page_includes_padly_favicon(self):
        response = self.client.get(reverse("core:landing"))

        self.assertContains(response, 'rel="icon"')
        self.assertContains(response, "images/padly-mark.svg")

    def test_landing_page_exposes_listing_search(self):
        response = self.client.get(reverse("core:landing"))

        self.assertContains(response, 'action="%s"' % reverse("listings:listing_list"))
        self.assertContains(response, 'name="q"')

    def test_landing_background_asset_exists(self):
        landing_background = Path(settings.BASE_DIR / "static" / "images" / "landing.jpg")

        self.assertTrue(landing_background.exists())

    def test_landing_page_shows_live_listing_preview(self):
        user = get_user_model().objects.create_user(username="owner", email="owner@bc.edu", password="pass12345")
        user.profile_image_url = "https://example.com/owner-avatar.jpg"
        user.save(update_fields=["profile_image_url"])
        user.listings.create(
            title="Beacon Street apartment",
            address="1731 Beacon St",
            price="1800.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            approval_status="approved",
        )

        response = self.client.get(reverse("core:landing"))

        self.assertContains(response, "Beacon Street apartment")
        self.assertContains(response, "$1800/mo")
        self.assertContains(response, "https://example.com/owner-avatar.jpg")

    def test_realtor_landing_only_surfaces_owned_listings(self):
        realtor = get_user_model().objects.create_user(username="agent", email="agent@gmail.com", password="pass12345")
        realtor.listings.create(
            title="Broker exclusive",
            address="50 Beacon St",
            price="2200.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            approval_status="approved",
        )
        other_user = get_user_model().objects.create_user(
            username="student",
            email="student@bc.edu",
            password="pass12345",
        )
        other_user.listings.create(
            title="Student listing",
            address="60 Beacon St",
            price="1800.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            approval_status="approved",
        )
        self.client.force_login(realtor)

        response = self.client.get(reverse("core:landing"))

        self.assertContains(response, "Listing Workspace")
        self.assertContains(response, "Broker exclusive")
        self.assertNotContains(response, "Student listing")

    def test_welcome_requires_login(self):
        response = self.client.get(reverse("core:welcome"))

        self.assertEqual(response.status_code, 302)

    def test_welcome_redirects_authenticated_user_to_dashboard(self):
        user = get_user_model().objects.create_user(
            username="alex",
            email="alex@bc.edu",
            password="pass12345",
            first_name="Alex",
            last_name="Park",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("core:welcome"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("users:dashboard"))

    def test_nav_profile_menu_shows_login_for_anonymous(self):
        response = self.client.get(reverse("core:landing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("account_login"))
        self.assertContains(response, "Log in")
        self.assertNotContains(response, "Guest User")

    def test_nav_profile_menu_shows_logout_for_authenticated(self):
        user = get_user_model().objects.create_user(username="alex", email="alex@bc.edu", password="pass12345")
        self.client.force_login(user)

        response = self.client.get(reverse("core:landing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("account_logout"))
        self.assertContains(response, "Log out")

    def test_terms_page_renders(self):
        response = self.client.get(reverse("core:terms"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Terms of Service")
        self.assertContains(response, "Padly")

    def test_privacy_page_renders(self):
        response = self.client.get(reverse("core:privacy"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Privacy Policy")
        self.assertContains(response, "Padly")
