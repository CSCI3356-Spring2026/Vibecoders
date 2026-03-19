from django.test import TestCase
from django.urls import reverse

from communications.models import ListingConversation

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
        self.assertContains(response, "full student access")
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
        self.assertContains(response, "/users/messages/")
        self.assertContains(response, "Log out")
        self.assertContains(response, "/accounts/logout/")

    def test_authenticated_profile_and_dashboard_render(self):
        self.client.force_login(self.user)

        profile_response = self.client.get("/users/profile/")
        dashboard_response = self.client.get("/users/dashboard/")

        self.assertEqual(profile_response.status_code, 200)
        self.assertContains(profile_response, self.user.display_role)
        self.assertContains(profile_response, "Access model")
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertContains(dashboard_response, f"Welcome, {self.user.username} - {self.user.display_role}")

    def test_profile_no_longer_allows_self_assigning_role(self):
        self.client.force_login(self.user)

        response = self.client.get("/users/profile/")

        self.assertNotContains(response, 'name="role"')
        self.assertNotContains(response, "<select")

    def test_posts_page_requires_login(self):
        response = self.client.get("/users/posts/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_messages_page_requires_login(self):
        response = self.client.get("/users/messages/")

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
        self.assertContains(response, "Your listings")
        self.assertContains(response, listing.title)

    def test_posts_page_is_paginated(self):
        for index in range(13):
            self.user.listings.create(
                title=f"My listing {index}",
                address=f"{index} Commonwealth Ave",
                price="1200.00",
                lease_type="FULL",
                start_date="2026-09-01",
                end_date="2027-05-31",
            )
        self.client.force_login(self.user)

        first_page = self.client.get("/users/posts/")
        second_page = self.client.get("/users/posts/?page=2")

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(second_page.status_code, 200)
        self.assertNotContains(first_page, "My listing 0")
        self.assertContains(second_page, "My listing 0")

    def test_realtor_dashboard_shows_listing_only_copy(self):
        realtor = User.objects.create_user(username="agent", email="agent@gmail.com", password="test")
        self.client.force_login(realtor)

        response = self.client.get("/users/dashboard/")

        self.assertContains(response, realtor.display_role)
        self.assertContains(response, "listing-only")

    def test_messages_page_renders_accessible_conversation(self):
        listing = self.user.listings.create(
            title="My listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
        )
        participant = User.objects.create_user(username="student", email="student@bc.edu", password="test")
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=self.user,
            participant=participant,
        )
        conversation.add_message(sender=participant, body="Is this still available?")
        self.client.force_login(self.user)

        response = self.client.get(reverse("communications:messages"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Listing conversations")
        self.assertContains(response, listing.title)
        self.assertContains(response, "Is this still available?")

    def test_opening_conversation_marks_it_read_for_current_user(self):
        listing = self.user.listings.create(
            title="My listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
        )
        participant = User.objects.create_user(username="student", email="student@bc.edu", password="test")
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=self.user,
            participant=participant,
        )
        conversation.add_message(sender=participant, body="Interested.")
        self.client.force_login(self.user)

        response = self.client.get(reverse("communications:detail", args=[conversation.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "0 unread")
        conversation.refresh_from_db()
        self.assertFalse(conversation.owner_has_unread_messages)

    def test_message_thread_is_paginated_to_latest_messages(self):
        listing = self.user.listings.create(
            title="My listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
        )
        participant = User.objects.create_user(username="student", email="student@bc.edu", password="test")
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=self.user,
            participant=participant,
        )
        for index in range(51):
            conversation.add_message(sender=participant, body=f"Message {index}")

        self.client.force_login(self.user)

        latest_page = self.client.get(reverse("communications:detail", args=[conversation.id]))
        older_page = self.client.get(reverse("communications:detail", args=[conversation.id]) + "?thread_page=2")

        self.assertEqual(latest_page.status_code, 200)
        self.assertEqual(older_page.status_code, 200)
        self.assertNotContains(latest_page, "Message 0")
        self.assertContains(latest_page, "Message 50")
        self.assertContains(older_page, "Message 0")

    def test_selected_conversation_stays_visible_when_not_on_current_inbox_page(self):
        selected_conversation = None

        for index in range(13):
            participant = User.objects.create_user(
                username=f"student{index}",
                email=f"student{index}@bc.edu",
                password="test",
            )
            listing = self.user.listings.create(
                title=f"Listing {index}",
                address=f"{index} Commonwealth Ave",
                price="1200.00",
                lease_type="FULL",
                start_date="2026-09-01",
                end_date="2027-05-31",
            )
            conversation = ListingConversation.objects.create(
                listing=listing,
                owner=self.user,
                participant=participant,
            )
            conversation.add_message(sender=participant, body=f"Message {index}")
            if index == 0:
                selected_conversation = conversation

        self.client.force_login(self.user)

        response = self.client.get(reverse("communications:detail", args=[selected_conversation.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="messages-list-item is-active"')
        self.assertContains(response, selected_conversation.listing.address)

    def test_reply_conversation_requires_membership(self):
        owner = User.objects.create_user(username="owner", email="owner@bc.edu", password="test")
        listing = owner.listings.create(
            title="Owner listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
        )
        participant = User.objects.create_user(username="student", email="student@bc.edu", password="test")
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=owner,
            participant=participant,
        )
        conversation.add_message(sender=participant, body="Interested.")
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("communications:reply_conversation", args=[conversation.id]), {"body": "Hello"}
        )

        self.assertEqual(response.status_code, 404)

    def test_admin_nav_includes_admin_dashboard_link(self):
        admin = User.objects.create_user(username="admin", email="admin@bc.edu", password="test", role="admin")
        self.client.force_login(admin)

        response = self.client.get("/")

        self.assertContains(response, "/users/admin-dashboard/")
        self.assertContains(response, "Admin Dashboard")

    def test_admin_listings_page_is_paginated(self):
        admin = User.objects.create_user(username="admin", email="admin@bc.edu", password="test", role="admin")
        owner = User.objects.create_user(username="owner", email="owner@bc.edu", password="test")
        for index in range(21):
            owner.listings.create(
                title=f"Admin listing {index}",
                address=f"{index} Beacon St",
                price="1800.00",
                lease_type="FULL",
                start_date="2026-09-01",
                end_date="2027-05-31",
            )
        self.client.force_login(admin)

        first_page = self.client.get("/users/admin-listings/")
        second_page = self.client.get("/users/admin-listings/?page=2")

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(second_page.status_code, 200)
        self.assertNotContains(first_page, "Admin listing 0")
        self.assertContains(second_page, "Admin listing 0")

    def test_admin_users_page_is_paginated(self):
        admin = User.objects.create_user(username="admin", email="admin@bc.edu", password="test", role="admin")
        for index in range(21):
            User.objects.create_user(username=f"member{index:02d}", email=f"member{index:02d}@bc.edu", password="test")
        self.client.force_login(admin)

        first_page = self.client.get("/users/admin-users/")
        second_page = self.client.get("/users/admin-users/?page=2")

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(second_page.status_code, 200)
        self.assertNotContains(first_page, "member20@bc.edu")
        self.assertContains(second_page, "member20@bc.edu")

    def test_admin_delete_listing_ignores_external_next_url(self):
        admin = User.objects.create_user(username="admin", email="admin@bc.edu", password="test", role="admin")
        owner = User.objects.create_user(username="owner", email="owner@bc.edu", password="test")
        listing = owner.listings.create(
            title="Admin listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
        )
        self.client.force_login(admin)

        response = self.client.post(
            reverse("users:admin_delete_listing", args=[listing.id]),
            {"next": "https://example.com/malicious"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("users:admin_listings"))
        self.assertFalse(owner.listings.filter(pk=listing.pk).exists())

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
