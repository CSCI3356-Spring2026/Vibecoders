from django.test import TestCase

from .helpers import User


class UserPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")

    def test_login_page_renders(self):
        response = self.client.get("/users/login/")

        self.assertEqual(response.status_code, 200)

    def test_profile_and_dashboard_require_login(self):
        for path in ("/users/profile/", "/users/dashboard/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/accounts/login/", response.url)

    def test_login_page_has_google_call_to_action(self):
        response = self.client.get("/users/login/")

        self.assertContains(response, "Sign in with Google")
        self.assertContains(response, "Continue with Google")
        self.assertContains(response, "Create Listing")
        self.assertContains(response, "/accounts/google/login/")
        self.assertNotContains(response, "Guest User")

    def test_allauth_login_page_uses_custom_google_ui(self):
        response = self.client.get("/accounts/login/")

        self.assertContains(response, "Sign in with Google")
        self.assertContains(response, "Continue with Google")
        self.assertContains(response, "Create Listing")
        self.assertNotContains(response, "If you have not created an account yet")

    def test_allauth_login_post_redirects_back_to_google_only_login(self):
        response = self.client.post("/accounts/login/", {"login": "user@bc.edu"}, follow=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/users/login/")

    def test_non_google_account_routes_are_disabled(self):
        for path in (
            "/accounts/signup/",
            "/accounts/password/reset/",
            "/accounts/login/code/",
            "/accounts/login/code/confirm/",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 404)

    def test_authenticated_login_page_redirects_to_dashboard(self):
        self.client.force_login(self.user)

        response = self.client.get("/users/login/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/users/dashboard/")

    def test_authenticated_header_shows_profile_menu_and_logout(self):
        self.client.force_login(self.user)

        response = self.client.get("/")

        self.assertContains(response, "profile-menu")
        self.assertContains(response, "Log out")
        self.assertContains(response, "/accounts/logout/")

    def test_authenticated_profile_and_dashboard_render(self):
        self.client.force_login(self.user)

        profile_response = self.client.get("/users/profile/")
        dashboard_response = self.client.get("/users/dashboard/")

        self.assertEqual(profile_response.status_code, 200)
        self.assertContains(profile_response, self.user.display_role)
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertContains(dashboard_response, f"Welcome, {self.user.username} - {self.user.display_role}")

    def test_posts_page_requires_login(self):
        response = self.client.get("/users/posts/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_authenticated_posts_page_renders_user_listings(self):
        listing = self.user.listings.create(
            title="My listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
        )
        self.client.force_login(self.user)

        response = self.client.get("/users/posts/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Posts")
        self.assertContains(response, listing.title)

    def test_logout_page_uses_custom_ui(self):
        self.client.force_login(self.user)

        response = self.client.get("/accounts/logout/")

        self.assertContains(response, "Log out")
        self.assertContains(response, "Stay signed in")

    def test_logout_post_signs_user_out(self):
        self.client.force_login(self.user)

        response = self.client.post("/accounts/logout/", follow=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")
        self.assertNotIn("_auth_user_id", self.client.session)
