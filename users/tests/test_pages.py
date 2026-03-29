import subprocess
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from communications.models import ListingConversation
from communications.selectors import accessible_conversations_for_user
from listings.models import Listing, ListingReport, ListingReview

from ..session_security import RECENT_AUTH_SESSION_KEY
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

    @override_settings(PROFILE_COMPLETION_REQUIRED=True)
    def test_profile_completion_redirects_incomplete_user_to_setup(self):
        self.client.force_login(self.user)

        response = self.client.get("/users/dashboard/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("users:profile_setup")))

    @override_settings(PROFILE_COMPLETION_REQUIRED=True)
    def test_profile_setup_requires_questionnaire_fields_before_completion(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("users:profile_setup"),
            {
                "preferred_name": "",
                "age": "",
                "gender": "",
                "gender_other": "",
                "major": "",
                "bio": "",
                "messy_level": "",
                "guest_level": "",
                "bedtime": "",
                "noise_level": "",
                "smoke": "",
                "drink": "",
                "party": "",
                "pets": "",
            },
        )

        self.user.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self.user.profile_completed_at)
        self.assertContains(response, "This field is required.")

    @override_settings(PROFILE_COMPLETION_REQUIRED=True)
    def test_profile_setup_completion_redirects_to_dashboard(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("users:profile_setup"),
            {
                "preferred_name": "Eagle",
                "age": "20",
                "gender": "male",
                "gender_other": "",
                "major": "CS",
                "bio": "Looking for a clean and social apartment.",
                "messy_level": "4",
                "guest_level": "3",
                "bedtime": "23",
                "noise_level": "2",
                "smoke": "",
                "drink": "2",
                "party": "2",
                "pets": "",
            },
            follow=False,
        )

        self.user.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("users:dashboard"))
        self.assertIsNotNone(self.user.profile_completed_at)

    def test_login_page_has_google_call_to_action(self):
        response = self.client.get("/users/login/")

        self.assertContains(response, 'class="auth-acceptance-form"')
        self.assertContains(response, "Continue with Google")
        self.assertContains(response, "marketplace access")
        self.assertContains(response, "Boston College Housing")
        self.assertContains(response, "Use the Google account tied to your BC or listing profile.")
        self.assertNotContains(response, '<header class="site-header">')
        self.assertNotContains(response, "Guest User")

    def test_allauth_login_page_uses_custom_google_ui(self):
        response = self.client.get("/accounts/login/")

        self.assertContains(response, 'class="auth-acceptance-form"')
        self.assertContains(response, "Continue with Google")
        self.assertContains(response, "Secure access for housing, listings, and messages.")
        self.assertNotContains(response, '<header class="site-header">')
        self.assertNotContains(response, "If you have not created an account yet")

    def test_login_page_shows_embedded_legal_review_when_required(self):
        session = self.client.session
        session["legal_review_required"] = settings.LEGAL_DOCUMENT_VERSION
        session.save()

        response = self.client.get("/users/login/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-legal-review-form")
        self.assertContains(response, 'name="accept_terms"')
        self.assertContains(response, 'name="accept_privacy"')
        self.assertContains(response, "Scroll to the end to unlock acknowledgement.")

    def test_login_page_redirects_to_google_without_legal_review_for_returning_flow(self):
        response = self.client.post("/users/login/", {}, follow=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/accounts/google/login/")

    def test_login_page_requires_scroll_review_before_legal_acceptance(self):
        session = self.client.session
        session["legal_review_required"] = settings.LEGAL_DOCUMENT_VERSION
        session.save()

        response = self.client.post(
            "/users/login/",
            {"accept_terms": "on", "accept_privacy": "on"},
            follow=False,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scroll through the Terms of Service before accepting.")
        self.assertContains(response, "Scroll through the Privacy Policy before accepting.")

    def test_login_page_redirects_to_google_after_scrolled_legal_acceptance(self):
        session = self.client.session
        session["legal_review_required"] = settings.LEGAL_DOCUMENT_VERSION
        session.save()

        response = self.client.post(
            "/users/login/",
            {
                "reviewed_terms": "on",
                "reviewed_privacy": "on",
                "accept_terms": "on",
                "accept_privacy": "on",
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/accounts/google/login/")

    @override_settings(LOGIN_INIT_RATE_LIMIT=1, LOGIN_INIT_RATE_WINDOW_SECONDS=300)
    def test_login_page_rate_limit_blocks_repeat_google_redirects(self):
        cache.clear()

        first_response = self.client.post(
            "/users/login/",
            {},
            follow=False,
        )
        second_response = self.client.post(
            "/users/login/",
            {},
            follow=True,
        )

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 200)
        self.assertContains(second_response, "Too many sign-in attempts. Wait a few minutes and try again.")

    def test_google_login_route_redirects_back_to_login_when_legal_review_is_required(self):
        session = self.client.session
        session["legal_review_required"] = settings.LEGAL_DOCUMENT_VERSION
        session.save()

        response = self.client.get("/accounts/google/login/", follow=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/users/login/")

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
        self.user.profile_image_url = "https://example.com/avatar.jpg"
        self.user.save(update_fields=["profile_image_url"])
        self.client.force_login(self.user)

        response = self.client.get("/")

        self.assertContains(response, "profile-menu")
        self.assertContains(response, "https://example.com/avatar.jpg")
        self.assertContains(response, "/users/messages/")
        self.assertContains(response, "Log out")
        self.assertContains(response, "/accounts/logout/")

    def test_authenticated_header_shows_google_avatar_when_available(self):
        SocialAccount.objects.create(
            user=self.user,
            provider="google",
            uid="google-eagle",
            extra_data={"picture": "https://example.com/eagle-avatar.png"},
        )
        self.client.force_login(self.user)

        response = self.client.get("/")

        self.assertContains(response, "user-avatar-image")
        self.assertContains(response, "https://example.com/eagle-avatar.png")
        self.assertNotContains(response, ">Group match<", html=False)

    def test_account_dashboard_shows_google_avatar_when_available(self):
        SocialAccount.objects.create(
            user=self.user,
            provider="google",
            uid="google-profile",
            extra_data={"picture": "https://example.com/profile-avatar.png"},
        )
        self.client.force_login(self.user)

        response = self.client.get("/users/dashboard/")

        self.assertContains(response, "https://example.com/profile-avatar.png")

    def test_authenticated_account_dashboard_renders_and_profile_redirects(self):
        self.user.profile_image_url = "https://example.com/avatar.jpg"
        self.user.save(update_fields=["profile_image_url"])
        self.client.force_login(self.user)

        profile_response = self.client.get("/users/profile/")
        dashboard_response = self.client.get("/users/dashboard/")

        self.assertEqual(profile_response.status_code, 302)
        self.assertEqual(profile_response["Location"], "/users/dashboard/")
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertContains(dashboard_response, "https://example.com/avatar.jpg")
        self.assertContains(dashboard_response, self.user.display_role)
        self.assertContains(dashboard_response, "Open document library")
        self.assertContains(dashboard_response, "Open group match studio")
        self.assertContains(dashboard_response, "Group match studio")
        self.assertContains(dashboard_response, "Workspace")
        self.assertNotContains(dashboard_response, "Permissions")
        self.assertNotContains(dashboard_response, "Email verification")
        self.assertNotContains(dashboard_response, "Student domains")
        self.assertNotContains(dashboard_response, "Admin access")

    def test_stale_legal_acceptance_logs_user_out_until_reaccepted(self):
        self.user.terms_accepted_at = timezone.now()
        self.user.privacy_accepted_at = timezone.now()
        self.user.legal_policy_version = "2025-01-01"
        self.user.save(update_fields=["terms_accepted_at", "privacy_accepted_at", "legal_policy_version"])
        self.client.force_login(self.user)

        response = self.client.get("/users/dashboard/", follow=True)

        final_redirect = response.redirect_chain[-1][0]
        parsed_redirect = urlsplit(final_redirect)

        self.assertEqual(parsed_redirect.path, "/users/login/")
        self.assertEqual(parse_qs(parsed_redirect.query).get("next"), ["/users/dashboard/"])
        self.assertContains(
            response, "Review and accept the latest Terms of Service and Privacy Policy before continuing."
        )
        self.assertContains(response, "data-legal-review-form")
        self.assertContains(response, "Accept and continue with Google")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_account_dashboard_no_longer_allows_self_assigning_role(self):
        self.client.force_login(self.user)

        response = self.client.get("/users/dashboard/")

        self.assertNotContains(response, 'name="role"')
        self.assertNotContains(response, "<select")

    def test_inline_confirm_positions_delete_panel_above_clipping_contexts(self):
        module_url = (Path(__file__).resolve().parents[2] / "static/js/inline-confirm.js").as_uri()
        script = f"""
import assert from "node:assert/strict";

const documentListeners = {{}};
const windowListeners = {{}};

class HTMLElement {{
    constructor() {{
        this.listeners = {{}};
        this.style = {{}};
        this.attributes = {{}};
        this.hidden = false;
        this.className = "";
        this.elements = {{}};
        this.rect = {{ top: 0, right: 0, bottom: 0, left: 0, width: 0, height: 0 }};
        this.classList = {{
            add: (...tokens) => tokens.forEach((token) => this._toggleClass(token, true)),
            remove: (...tokens) => tokens.forEach((token) => this._toggleClass(token, false)),
            contains: (token) => this.className.split(/\\s+/).filter(Boolean).includes(token),
        }};
    }}

    _toggleClass(token, force) {{
        const next = new Set(this.className.split(/\\s+/).filter(Boolean));
        if (force) {{
            next.add(token);
        }} else {{
            next.delete(token);
        }}
        this.className = Array.from(next).join(" ");
    }}

    setAttribute(name, value) {{
        this.attributes[name] = value;
    }}

    addEventListener(type, handler) {{
        this.listeners[type] = handler;
    }}

    dispatch(type, event = {{}}) {{
        this.listeners[type]?.({{ target: this, ...event }});
    }}

    querySelector(selector) {{
        return this.elements[selector] ?? null;
    }}

    contains(target) {{
        return target === this || Object.values(this.elements).includes(target);
    }}

    getBoundingClientRect() {{
        return this.rect;
    }}
}}

const root = new HTMLElement();
const trigger = new HTMLElement();
const panel = new HTMLElement();
const closeButton = new HTMLElement();
root.elements = {{
    "[data-inline-confirm-open]": trigger,
    "[data-inline-confirm-panel]": panel,
    "[data-inline-confirm-close]": closeButton,
}};

trigger.rect = {{ top: 740, right: 1180, bottom: 772, left: 1100, width: 80, height: 32 }};
panel.rect = {{ top: 0, right: 280, bottom: 160, left: 0, width: 280, height: 160 }};

globalThis.document = {{
    querySelectorAll() {{
        return [root];
    }},
    addEventListener(type, handler) {{
        documentListeners[type] = handler;
    }},
}};

globalThis.window = {{
    innerWidth: 1280,
    innerHeight: 800,
    addEventListener(type, handler) {{
        windowListeners[type] = handler;
    }},
}};

await import({module_url!r});

assert.equal(panel.hidden, true);
trigger.dispatch("click");
assert.equal(root.classList.contains("is-open"), true);
assert.equal(panel.hidden, false);
assert.equal(trigger.attributes["aria-expanded"], "true");
assert.equal(panel.style.top, "572px");
assert.equal(panel.style.left, "900px");

trigger.rect = {{ top: 100, right: 200, bottom: 132, left: 120, width: 80, height: 32 }};
windowListeners.resize();
assert.equal(panel.style.top, "140px");
assert.equal(panel.style.left, "12px");

closeButton.dispatch("click");
assert.equal(panel.hidden, true);
assert.equal(root.classList.contains("is-open"), false);
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

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
            approval_status="approved",
        )
        self.client.force_login(self.user)

        response = self.client.get("/users/posts/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your listings")
        self.assertContains(response, listing.title)
        self.assertNotContains(response, "confirm(")

    def test_posts_page_is_paginated(self):
        for index in range(13):
            self.user.listings.create(
                title=f"My listing {index}",
                address=f"{index} Commonwealth Ave",
                price="1200.00",
                lease_type="FULL",
                start_date="2026-09-01",
                end_date="2027-05-31",
                approval_status="approved",
            )
        self.client.force_login(self.user)

        first_page = self.client.get("/users/posts/")
        second_page = self.client.get("/users/posts/?page=2")

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(second_page.status_code, 200)
        self.assertNotContains(first_page, "My listing 0")
        self.assertContains(second_page, "My listing 0")

    def test_posts_page_conversation_count_is_not_inflated_by_feedback_annotations(self):
        listing = self.user.listings.create(
            title="Feedback heavy listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
            approval_status="approved",
        )
        participant = User.objects.create_user(username="connected", email="connected@bc.edu", password="test")
        first_reporter = User.objects.create_user(username="reporter-one", email="reporter-one@bc.edu", password="test")
        second_reporter = User.objects.create_user(
            username="reporter-two",
            email="reporter-two@bc.edu",
            password="test",
        )
        ListingConversation.objects.create(listing=listing, owner=self.user, participant=participant)
        ListingReview.objects.create(listing=listing, author=participant, rating=4, comment="Real feedback.")
        ListingReport.objects.create(
            listing=listing,
            reporter=first_reporter,
            reason=ListingReport.REASON_SPAM,
            details="Needs review.",
        )
        ListingReport.objects.create(
            listing=listing,
            reporter=second_reporter,
            reason=ListingReport.REASON_INACCURATE,
            details="Price looks stale.",
        )
        self.client.force_login(self.user)

        response = self.client.get("/users/posts/")

        page_listing = list(response.context["listings"].object_list)[0]
        self.assertEqual(page_listing.conversation_count, 1)

    def test_realtor_dashboard_shows_listing_only_copy(self):
        realtor = User.objects.create_user(username="agent", email="agent@gmail.com", password="test")
        self.client.force_login(realtor)

        response = self.client.get("/users/dashboard/")

        self.assertContains(response, realtor.display_role)
        self.assertContains(response, "Listing access only")
        self.assertContains(response, "Open document library")

    def test_messages_page_renders_accessible_conversation(self):
        listing = self.user.listings.create(
            title="My listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
            approval_status="approved",
        )
        SocialAccount.objects.create(
            user=self.user,
            provider="google",
            uid="google-owner-thread",
            extra_data={"picture": "https://example.com/owner-thread-avatar.png"},
        )
        participant = User.objects.create_user(username="student", email="student@bc.edu", password="test")
        participant.profile_image_url = "https://example.com/student-avatar.jpg"
        participant.save(update_fields=["profile_image_url"])
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=self.user,
            participant=participant,
        )
        conversation.add_message(sender=participant, body="Is this still available?")
        conversation.add_message(sender=self.user, body="Yes, it is.")
        self.client.force_login(self.user)

        response = self.client.get(reverse("communications:messages"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Listing conversations")
        self.assertContains(response, listing.title)
        self.assertContains(response, "Is this still available?")
        self.assertContains(response, "Yes, it is.")
        self.assertContains(response, "https://example.com/student-avatar.jpg")
        self.assertContains(response, "https://example.com/owner-thread-avatar.png")
        self.assertContains(response, 'class="message-row is-inbound"')
        self.assertContains(response, 'class="message-row is-outbound"')
        self.assertContains(response, "0 / 2000")
        self.assertNotContains(response, "0 / None")

    def test_user_can_delete_message_thread_for_themselves(self):
        listing = self.user.listings.create(
            title="My listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
            approval_status="approved",
        )
        participant = User.objects.create_user(username="student", email="student@bc.edu", password="test")
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=self.user,
            participant=participant,
        )
        conversation.add_message(sender=participant, body="Interested.")
        self.client.force_login(self.user)

        response = self.client.post(reverse("communications:delete_conversation", args=[conversation.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("communications:messages"))
        self.assertFalse(accessible_conversations_for_user(self.user).filter(pk=conversation.pk).exists())
        self.assertTrue(accessible_conversations_for_user(participant).filter(pk=conversation.pk).exists())

    def test_messages_page_shows_counterparty_avatar_when_available(self):
        listing = self.user.listings.create(
            title="My listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
            approval_status="approved",
        )
        participant = User.objects.create_user(username="student", email="student@bc.edu", password="test")
        SocialAccount.objects.create(
            user=participant,
            provider="google",
            uid="google-student",
            extra_data={"picture": "https://example.com/student-avatar.png"},
        )
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=self.user,
            participant=participant,
        )
        conversation.add_message(sender=participant, body="Is this still available?")
        self.client.force_login(self.user)

        response = self.client.get(reverse("communications:messages"))

        self.assertContains(response, "https://example.com/student-avatar.png")

    def test_opening_conversation_marks_it_read_for_current_user(self):
        listing = self.user.listings.create(
            title="My listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
            approval_status="approved",
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
            approval_status="approved",
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
                approval_status="approved",
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
            approval_status="approved",
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

    @override_settings(MESSAGE_SEND_RATE_LIMIT=1, MESSAGE_SEND_RATE_WINDOW_SECONDS=60)
    def test_reply_conversation_rate_limit_blocks_second_reply(self):
        participant = User.objects.create_user(username="student", email="student@bc.edu", password="test")
        listing = self.user.listings.create(
            title="Owner listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
            approval_status="approved",
        )
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=self.user,
            participant=participant,
        )
        self.client.force_login(self.user)
        cache.clear()

        first_response = self.client.post(
            reverse("communications:reply_conversation", args=[conversation.id]),
            {"body": "Hello"},
            follow=False,
        )
        second_response = self.client.post(
            reverse("communications:reply_conversation", args=[conversation.id]),
            {"body": "Following up"},
            follow=True,
        )

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 200)
        self.assertContains(second_response, "Too many messages sent too quickly. Wait a minute and try again.")
        self.assertEqual(conversation.messages.count(), 1)

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
                approval_status="approved",
            )
        self.client.force_login(admin)

        first_page = self.client.get("/users/admin-listings/")
        second_page = self.client.get("/users/admin-listings/?page=2")

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(second_page.status_code, 200)
        self.assertNotContains(first_page, "Admin listing 0")
        self.assertContains(second_page, "Admin listing 0")
        self.assertNotContains(first_page, "confirm(")

    def test_admin_listings_queue_prioritizes_pending_review(self):
        admin = User.objects.create_user(username="admin", email="admin@bc.edu", password="test", role="admin")
        owner = User.objects.create_user(username="queue-owner", email="queue-owner@bc.edu", password="test")
        approved = owner.listings.create(
            title="Approved listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
            approval_status="approved",
        )
        pending = owner.listings.create(
            title="Pending listing",
            address="141 Commonwealth Ave",
            price="1300.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
            approval_status="pending",
        )
        self.client.force_login(admin)

        response = self.client.get("/users/admin-listings/")

        listings = list(response.context["listings"].object_list[:2])
        self.assertEqual([listing.id for listing in listings], [pending.id, approved.id])

    def test_admin_can_approve_listing_from_review_page(self):
        admin = User.objects.create_user(username="admin", email="admin@bc.edu", password="test", role="admin")
        owner = User.objects.create_user(username="owner", email="owner@bc.edu", password="test")
        listing = owner.listings.create(
            title="Queued listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
        )
        self.client.force_login(admin)

        response = self.client.post(
            reverse("users:admin_review_listing", args=[listing.id]),
            {"action": "approve", "review_notes": "Address and photos look consistent."},
            follow=False,
        )

        listing.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("users:admin_listing_detail", args=[listing.id]))
        self.assertEqual(listing.approval_status, Listing.APPROVAL_APPROVED)
        self.assertEqual(listing.reviewed_by, admin)
        self.assertEqual(listing.approval_notes, "Address and photos look consistent.")

    def test_admin_reject_requires_review_notes(self):
        admin = User.objects.create_user(username="admin", email="admin@bc.edu", password="test", role="admin")
        owner = User.objects.create_user(username="queue-owner", email="queue-owner@bc.edu", password="test")
        listing = owner.listings.create(
            title="Needs review notes",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
        )
        self.client.force_login(admin)

        response = self.client.post(
            reverse("users:admin_review_listing", args=[listing.id]),
            {"action": "reject", "review_notes": ""},
            follow=False,
        )

        listing.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add review notes when rejecting a listing.")
        self.assertEqual(listing.approval_status, Listing.APPROVAL_PENDING)

    def test_admin_reports_page_can_update_report_status(self):
        admin = User.objects.create_user(username="admin", email="admin@bc.edu", password="test", role="admin")
        owner = User.objects.create_user(username="owner", email="owner@bc.edu", password="test")
        reporter = User.objects.create_user(username="reporter", email="reporter@bc.edu", password="test")
        listing = owner.listings.create(
            title="Reported listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
            approval_status="approved",
        )
        report = ListingReport.objects.create(
            listing=listing,
            reporter=reporter,
            reason=ListingReport.REASON_SPAM,
            details="Duplicate inventory.",
        )
        self.client.force_login(admin)

        page_response = self.client.get(reverse("users:admin_reports"))
        update_response = self.client.post(
            reverse("users:admin_update_report", args=[report.id]),
            {
                f"report-{report.id}-status": ListingReport.STATUS_RESOLVED,
                f"report-{report.id}-resolution_notes": "Removed the duplicate and kept the canonical listing.",
                "next": reverse("users:admin_reports"),
            },
            follow=False,
        )

        report.refresh_from_db()
        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, "Reported listing")
        self.assertEqual(update_response.status_code, 302)
        self.assertEqual(update_response["Location"], reverse("users:admin_reports"))
        self.assertEqual(report.status, ListingReport.STATUS_RESOLVED)
        self.assertEqual(report.reviewed_by, admin)

    def test_admin_reports_page_requires_resolution_notes_to_close_report(self):
        admin = User.objects.create_user(username="admin", email="admin@bc.edu", password="test", role="admin")
        owner = User.objects.create_user(username="owner-two", email="owner-two@bc.edu", password="test")
        reporter = User.objects.create_user(username="reporter-two", email="reporter-two@bc.edu", password="test")
        listing = owner.listings.create(
            title="Reported listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
            approval_status="approved",
        )
        report = ListingReport.objects.create(
            listing=listing,
            reporter=reporter,
            reason=ListingReport.REASON_SPAM,
            details="Duplicate inventory.",
        )
        self.client.force_login(admin)

        response = self.client.post(
            reverse("users:admin_update_report", args=[report.id]),
            {
                f"report-{report.id}-status": ListingReport.STATUS_RESOLVED,
                f"report-{report.id}-resolution_notes": "",
                "next": reverse("users:admin_reports"),
            },
            follow=True,
        )

        report.refresh_from_db()
        self.assertContains(response, "Add valid resolution notes before updating the report.")
        self.assertEqual(report.status, ListingReport.STATUS_OPEN)

    def test_user_can_delete_their_account(self):
        self.client.force_login(self.user)
        session = self.client.session
        session[RECENT_AUTH_SESSION_KEY] = timezone.now().isoformat()
        session.save()

        response = self.client.post(reverse("users:delete_account"), follow=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("core:landing"))
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_delete_account_requires_recent_auth(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("users:delete_account"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in again before deleting your account.")
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_last_active_admin_cannot_delete_account(self):
        admin = User.objects.create_user(username="admin", email="admin@bc.edu", password="test", role="admin")
        self.client.force_login(admin)
        session = self.client.session
        session[RECENT_AUTH_SESSION_KEY] = timezone.now().isoformat()
        session.save()

        response = self.client.post(reverse("users:delete_account"), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You cannot delete the last active admin account.")
        self.assertTrue(User.objects.filter(pk=admin.pk).exists())

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
            approval_status="approved",
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
