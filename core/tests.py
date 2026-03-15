from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


# -----------------------------------------------------------------------------
# View tests
# -----------------------------------------------------------------------------
class CorePageTests(TestCase):
    # Test that the root page renders successfully with the correct template
    def test_root_page_renders(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "core/landing.html")

    def test_welcome_requires_login(self):
        response = self.client.get("/welcome/")

        self.assertEqual(response.status_code, 302)

    def test_welcome_displays_username_and_role(self):
        user = get_user_model().objects.create_user(
            username="alex",
            password="pass12345",
            first_name="Alex",
            last_name="Park",
        )
        self.client.force_login(user)

        response = self.client.get("/welcome/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Welcome, Alex Park")
        self.assertContains(response, user.display_role)

    def test_nav_profile_menu_shows_login_for_anonymous(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("account_login"))
        self.assertContains(response, "Log in")

    def test_nav_profile_menu_shows_logout_for_authenticated(self):
        user = get_user_model().objects.create_user(username="alex", password="pass12345")
        self.client.force_login(user)

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("account_logout"))
        self.assertContains(response, "Log out")
