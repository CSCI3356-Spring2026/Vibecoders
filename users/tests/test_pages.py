import subprocess
from datetime import timedelta
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
from listings.models import Listing, ListingReport, ListingReview, RoommatePost

from ..session_security import RECENT_AUTH_SESSION_KEY
from .helpers import User


class UserPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")

    def _complete_roommate_profile(self, user, *, first_name=None):
        if first_name is not None:
            user.first_name = first_name
        user.profile_completed_at = timezone.now()
        update_fields = ["first_name", "profile_completed_at"] if first_name is not None else ["profile_completed_at"]
        user.save(update_fields=update_fields)

        profile = user.student_profile
        profile.preferred_name = first_name or user.username
        profile.major = "Computer Science"
        profile.bio = "Easygoing roommate."
        profile.messy_level = 3
        profile.guest_level = 3
        profile.bedtime = 22
        profile.noise_level = 3
        profile.smoke = False
        profile.drink = 3
        profile.party = 2
        profile.pets = False
        profile.save()

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

    def test_student_profile_setup_renders_grouped_sections_and_choice_controls(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("users:profile_setup"))

        self.assertContains(response, "Student profile")
        self.assertContains(response, "Living preferences")
        self.assertContains(response, "Habits")
        self.assertContains(response, "Typical bedtime")
        self.assertContains(response, "profile-scale-grid")
        self.assertContains(response, 'type="radio"')
        self.assertNotContains(response, 'type="range"')

    @override_settings(PROFILE_COMPLETION_REQUIRED=True)
    def test_realtor_profile_setup_completion_does_not_require_age_or_gender(self):
        realtor = User.objects.create_user(username="agent", email="agent@gmail.com", password="test")
        self.client.force_login(realtor)

        response = self.client.post(
            reverse("users:profile_setup"),
            {
                "preferred_name": "Beacon Realty",
                "age": "",
                "gender": "",
                "gender_other": "",
                "bio": "Managing listings near campus.",
            },
            follow=False,
        )

        realtor.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("users:dashboard"))
        self.assertIsNotNone(realtor.profile_completed_at)

    def test_realtor_profile_setup_is_lighter_than_student_questionnaire(self):
        realtor = User.objects.create_user(username="agent2", email="agent2@gmail.com", password="test")
        self.client.force_login(realtor)

        response = self.client.get(reverse("users:profile_setup"))

        self.assertContains(response, "Listing profile")
        self.assertContains(response, "About this account")
        self.assertNotContains(response, "Living preferences")
        self.assertNotContains(response, 'name="messy_level"')
        self.assertNotContains(response, 'type="radio"')

    def test_login_page_has_google_call_to_action(self):
        response = self.client.get("/users/login/")

        self.assertContains(response, 'class="auth-acceptance-form"')
        self.assertContains(response, "Continue with Google")
        self.assertContains(response, "One Google account for your listings, inbox, and document library.")
        self.assertContains(response, "Boston College Housing")
        self.assertContains(response, 'class="auth-layout auth-layout-login"')
        self.assertNotContains(response, '<header class="site-header">')
        self.assertNotContains(response, "Guest User")

    def test_allauth_login_page_uses_custom_google_ui(self):
        response = self.client.get("/accounts/login/")

        self.assertContains(response, 'class="auth-acceptance-form"')
        self.assertContains(response, "Continue with Google")
        self.assertContains(response, "Continue with Google.")
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
        self.assertContains(response, "auth-review-stepper")
        self.assertContains(response, "Continue to Terms")
        self.assertContains(response, "auth-layout-review")
        self.assertContains(response, "auth-panel-review")

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
        self.assertEqual(response["Location"], "/accounts/google/login/")

    def test_allauth_login_post_preserves_next_without_extra_bounce(self):
        response = self.client.post("/accounts/login/?next=/listings/", {}, follow=False)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/accounts/google/login/?next=%2Flistings%2F")

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

    def test_authenticated_header_hides_messages_badge_when_no_unread_threads(self):
        self.client.force_login(self.user)

        response = self.client.get("/")

        self.assertContains(response, "data-nav-unread-count")
        self.assertContains(response, 'class="nav-badge is-hidden"')
        self.assertContains(response, 'aria-hidden="true"')

    def test_authenticated_header_shows_unread_messages_badge(self):
        self.client.force_login(self.user)
        empty_response = self.client.get("/")
        self.assertContains(empty_response, 'class="nav-badge is-hidden"')

        listing = self.user.listings.create(
            title="Unread listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
            approval_status="approved",
        )
        participant = User.objects.create_user(username="reader", email="reader@bc.edu", password="test")
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=self.user,
            participant=participant,
        )
        conversation.add_message(sender=participant, body="Unread note.")

        response = self.client.get("/")

        self.assertContains(response, "data-nav-unread-count")
        self.assertContains(response, "data-nav-unread-count")
        self.assertContains(response, "1")
        self.assertNotContains(response, 'class="nav-badge is-hidden"')

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
        self.assertNotContains(response, ">Browse<", html=False)

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
        self.assertContains(dashboard_response, ">Roommates<", html=False)
        self.assertNotContains(dashboard_response, ">Browse<", html=False)
        self.assertNotContains(dashboard_response, "Workspace")
        self.assertNotContains(dashboard_response, "Permissions")
        self.assertNotContains(dashboard_response, "Email verification")
        self.assertNotContains(dashboard_response, "Student domains")
        self.assertNotContains(dashboard_response, "Admin access")

    def test_browse_roommates_renders_for_authenticated_user(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("users:browse_roommates"))

        self.assertEqual(response.status_code, 200)

    def test_browse_roommates_people_results_are_paginated(self):
        self._complete_roommate_profile(self.user, first_name="Viewer")
        for index in range(13):
            candidate = User.objects.create_user(
                username=f"candidate{index}",
                email=f"candidate{index}@bc.edu",
                password="test",
            )
            self._complete_roommate_profile(candidate, first_name=f"Student{index:02d}")

        self.client.force_login(self.user)

        response = self.client.get(reverse("users:browse_roommates"), {"page": "2"})

        self.assertEqual(response.status_code, 200)
        results_page = response.context["results"]
        self.assertEqual(results_page.paginator.count, 13)
        self.assertEqual(results_page.number, 2)
        self.assertEqual(len(results_page.object_list), 1)

    def test_public_profile_shows_direct_message_entry_point(self):
        target = User.objects.create_user(username="match", email="match@bc.edu", password="test", first_name="Riley")
        self.user.profile_completed_at = timezone.now()
        self.user.save(update_fields=["profile_completed_at"])
        target.profile_completed_at = timezone.now()
        target.save(update_fields=["profile_completed_at"])
        target.student_profile.major = "Biology"
        target.student_profile.save(update_fields=["major"])
        RoommatePost.objects.create(
            author=target,
            title="Looking for one more roommate in Brighton",
            description="We need one more roommate for a late-summer move and a quiet apartment.",
            housing_status=RoommatePost.HOUSING_NEED_HOME,
            current_group_size=2,
            open_spots=1,
            budget_min="1200",
            budget_max="1500",
            move_in_date=timezone.localdate() + timedelta(days=30),
            neighborhoods="Brighton",
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("users:public_profile", args=[target.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Message Riley")
        self.assertContains(response, reverse("communications:start_direct_conversation", args=[target.id]))
        self.assertContains(response, "Start chat")

    def test_user_can_start_direct_conversation_from_public_profile(self):
        target = User.objects.create_user(username="match", email="match@bc.edu", password="test", first_name="Riley")
        self.user.profile_completed_at = timezone.now()
        self.user.save(update_fields=["profile_completed_at"])
        target.profile_completed_at = timezone.now()
        target.save(update_fields=["profile_completed_at"])
        RoommatePost.objects.create(
            author=target,
            title="Looking for one more roommate in Allston",
            description="We want one more roommate for a fall lease and an easygoing apartment.",
            housing_status=RoommatePost.HOUSING_NEED_HOME,
            current_group_size=2,
            open_spots=1,
            budget_min="1200",
            budget_max="1500",
            move_in_date=timezone.localdate() + timedelta(days=30),
            neighborhoods="Allston",
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("communications:start_direct_conversation", args=[target.id]),
            {"body": "Hey, want to compare housing plans?"},
        )

        self.assertEqual(response.status_code, 302)
        conversation = ListingConversation.objects.get()
        self.assertTrue(conversation.is_direct)
        self.assertIsNone(conversation.listing)
        self.assertRedirects(
            response,
            reverse("communications:detail", args=[conversation.id]),
            fetch_redirect_response=False,
        )

    def test_public_profile_hides_new_message_entry_when_target_has_no_active_roommate_post(self):
        target = User.objects.create_user(username="match", email="match@bc.edu", password="test", first_name="Riley")
        self.user.profile_completed_at = timezone.now()
        self.user.save(update_fields=["profile_completed_at"])
        target.profile_completed_at = timezone.now()
        target.save(update_fields=["profile_completed_at"])
        self.client.force_login(self.user)

        response = self.client.get(reverse("users:public_profile", args=[target.id]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Message Riley")
        self.assertNotContains(response, "Start chat")

    def test_public_profile_requires_completed_roommate_profile(self):
        target = User.objects.create_user(username="match", email="match@bc.edu", password="test", first_name="Riley")
        self.client.force_login(self.user)

        response = self.client.get(reverse("users:public_profile", args=[target.id]))

        self.assertEqual(response.status_code, 404)

    def test_direct_message_post_requires_completed_roommate_profile(self):
        target = User.objects.create_user(username="match", email="match@bc.edu", password="test", first_name="Riley")
        target.profile_completed_at = timezone.now()
        target.save(update_fields=["profile_completed_at"])
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("communications:start_direct_conversation", args=[target.id]),
            {"body": "Hey, want to compare housing plans?"},
            follow=True,
        )

        self.assertEqual(ListingConversation.objects.count(), 0)
        self.assertContains(response, "Complete your roommate profile before messaging matches.")

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
        self.assertContains(response, "Messages")
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

    def test_messages_page_renders_direct_conversation_context(self):
        participant = User.objects.create_user(username="student", email="student@bc.edu", password="test")
        participant.student_profile.major = "Nursing"
        participant.student_profile.save(update_fields=["major"])
        conversation = ListingConversation.objects.create(
            conversation_type=ListingConversation.CONVERSATION_TYPE_DIRECT,
            owner=self.user,
            participant=participant,
        )
        conversation.add_message(sender=participant, body="Want to search together?")
        self.client.force_login(self.user)

        response = self.client.get(reverse("communications:messages"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Roommate chat")
        self.assertContains(response, "View profile")
        self.assertContains(response, "Direct chat")

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
        listing.refresh_from_db()
        self.assertEqual(listing.approval_status, Listing.APPROVAL_REJECTED)
        self.assertFalse(listing.is_hidden)
        queue_response = self.client.get(reverse("users:admin_reports"))
        self.assertNotContains(queue_response, "Reported listing")

    def test_admin_reports_page_dismisses_report_without_closing_listing(self):
        admin = User.objects.create_user(username="admin", email="admin@bc.edu", password="test", role="admin")
        owner = User.objects.create_user(username="owner-four", email="owner-four@bc.edu", password="test")
        reporter = User.objects.create_user(username="reporter-four", email="reporter-four@bc.edu", password="test")
        listing = owner.listings.create(
            title="Dismissed report listing",
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
            details="Looks like a duplicate.",
        )
        self.client.force_login(admin)

        response = self.client.post(
            reverse("users:admin_update_report", args=[report.id]),
            {
                f"report-{report.id}-status": ListingReport.STATUS_DISMISSED,
                f"report-{report.id}-resolution_notes": "Confirmed this listing is legitimate.",
                "next": reverse("users:admin_reports"),
            },
            follow=False,
        )

        report.refresh_from_db()
        listing.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(report.status, ListingReport.STATUS_DISMISSED)
        self.assertEqual(listing.approval_status, Listing.APPROVAL_APPROVED)
        self.assertFalse(listing.is_hidden)

    def test_admin_reports_page_can_update_historical_report_after_reporter_role_changes(self):
        admin = User.objects.create_user(username="admin", email="admin@bc.edu", password="test", role="admin")
        owner = User.objects.create_user(username="owner-three", email="owner-three@bc.edu", password="test")
        reporter = User.objects.create_user(username="reporter-three", email="reporter-three@bc.edu", password="test")
        listing = owner.listings.create(
            title="Historic report listing",
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
            reason=ListingReport.REASON_SAFETY,
            details="The lockbox code is posted in the photos.",
        )
        reporter.set_admin_access(True)
        reporter.save(update_fields=["role"])
        self.client.force_login(admin)

        response = self.client.post(
            reverse("users:admin_update_report", args=[report.id]),
            {
                f"report-{report.id}-status": ListingReport.STATUS_IN_REVIEW,
                f"report-{report.id}-resolution_notes": "Escalated to the trust and safety queue.",
                "next": reverse("users:admin_reports"),
            },
            follow=False,
        )

        report.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(report.status, ListingReport.STATUS_IN_REVIEW)
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
        self.assertContains(response, "Add a moderator note before closing out a report.")
        self.assertEqual(report.status, ListingReport.STATUS_OPEN)

    def test_admin_reports_page_defaults_to_active_reports_only(self):
        admin = User.objects.create_user(username="admin", email="admin@bc.edu", password="test", role="admin")
        owner = User.objects.create_user(username="owner-five", email="owner-five@bc.edu", password="test")
        reporter = User.objects.create_user(username="reporter-five", email="reporter-five@bc.edu", password="test")
        listing = owner.listings.create(
            title="Queue visibility listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
            approval_status="approved",
        )
        open_report = ListingReport.objects.create(
            listing=listing,
            reporter=reporter,
            reason=ListingReport.REASON_SPAM,
            details="Open report.",
        )
        dismissed_report = ListingReport.objects.create(
            listing=listing,
            reporter=User.objects.create_user(username="reporter-six", email="reporter-six@bc.edu", password="test"),
            reason=ListingReport.REASON_SAFETY,
            details="Closed report.",
            status=ListingReport.STATUS_DISMISSED,
            resolution_notes="Handled.",
            reviewed_by=admin,
            reviewed_at=timezone.now(),
        )
        self.client.force_login(admin)

        response = self.client.get(reverse("users:admin_reports"))

        self.assertContains(response, open_report.details)
        self.assertNotContains(response, dismissed_report.details)

    def test_admin_reports_page_shows_report_update_history(self):
        admin = User.objects.create_user(username="admin", email="admin@bc.edu", password="test", role="admin")
        owner = User.objects.create_user(username="owner-six", email="owner-six@bc.edu", password="test")
        reporter = User.objects.create_user(username="reporter-seven", email="reporter-seven@bc.edu", password="test")
        listing = owner.listings.create(
            title="Timeline listing",
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
            reason=ListingReport.REASON_SAFETY,
            details="Initial report.",
        )
        report.mark_status(
            status=ListingReport.STATUS_IN_REVIEW,
            reviewer=admin,
            resolution_notes="Escalated to campus safety.",
        )
        report.save()
        report.add_update(actor=admin, note="Escalated to campus safety.")
        report.add_update(actor=admin, note="Waiting on follow-up from the lister.")
        self.client.force_login(admin)

        response = self.client.get(reverse("users:admin_listing_detail", args=[listing.id]))

        self.assertContains(response, "Moderation history")
        self.assertContains(response, "Escalated to campus safety.")
        self.assertContains(response, "Waiting on follow-up from the lister.")

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
