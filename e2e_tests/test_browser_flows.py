import json
import os
import re
import unittest
from contextlib import contextmanager
from datetime import date

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY, get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import expect, sync_playwright

from communications.models import ListingConversation
from listings.models import Listing
from users.models import Role


@unittest.skipUnless(os.environ.get("RUN_E2E_TESTS") == "1", "Browser e2e tests run only in the dedicated e2e job.")
@override_settings(
    LISTING_GEOAPIFY_API_KEY="geoapify-test-key",
    LISTING_GEOAPIFY_MAP_STYLE_URL="https://example.test/styles/mock.json",
    LISTING_MAP_SATELLITE_STYLE_URL="",
)
class BrowserFlowsTests(StaticLiveServerTestCase):
    host = "127.0.0.1"

    @contextmanager
    def browser_session(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                yield browser
            finally:
                browser.close()

    def create_user(
        self,
        username,
        email,
        *,
        role=Role.STUDENT,
        first_name="",
        profile_complete=False,
        legal="current",
    ):
        user = get_user_model().objects.create_user(
            username=username,
            email=email,
            password="testpass123",
            first_name=first_name,
            role=role,
        )

        if profile_complete:
            profile = user.student_profile
            profile.preferred_name = first_name or username
            profile.major = "Computer Science"
            profile.bio = "Easygoing roommate."
            profile.messy_level = 3
            profile.guest_level = 2
            profile.bedtime = 23
            profile.noise_level = 2
            profile.drink = 2
            profile.party = 2
            profile.smoke = False
            profile.pets = False
            profile.save()
            user.profile_completed_at = timezone.now()

        if legal == "current":
            accepted_at = timezone.now()
            user.terms_accepted_at = accepted_at
            user.privacy_accepted_at = accepted_at
            user.legal_policy_version = settings.LEGAL_DOCUMENT_VERSION
        elif legal == "stale":
            accepted_at = timezone.now()
            user.terms_accepted_at = accepted_at
            user.privacy_accepted_at = accepted_at
            user.legal_policy_version = "2025-01-01"
        elif legal == "missing":
            user.terms_accepted_at = None
            user.privacy_accepted_at = None
            user.legal_policy_version = settings.LEGAL_DOCUMENT_VERSION

        user.save()
        return user

    def create_listing(self, owner, *, title="Beacon apartment", latitude=42.3355, longitude=-71.1685):
        return owner.listings.create(
            title=title,
            address="140 Commonwealth Ave",
            latitude=latitude,
            longitude=longitude,
            price="1800.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            property_type="apartment",
            description="Sunny place near campus.",
            approval_status=Listing.APPROVAL_APPROVED,
        )

    def authenticated_session_cookie(self, user):
        session = SessionStore()
        session[SESSION_KEY] = str(user.pk)
        session[BACKEND_SESSION_KEY] = "allauth.account.auth_backends.AuthenticationBackend"
        session[HASH_SESSION_KEY] = user.get_session_auth_hash()
        session.save()

        return {
            "name": settings.SESSION_COOKIE_NAME,
            "value": session.session_key,
            "url": self.live_server_url,
        }

    def authenticated_context(self, browser, session_cookie, *, init_script=None):
        context = browser.new_context(base_url=self.live_server_url)
        if init_script:
            context.add_init_script(init_script)
        context.add_cookies([session_cookie])
        return context

    def test_stale_legal_acceptance_redirects_to_review_flow(self):
        user = self.create_user("stale-user", "stale-user@bc.edu", legal="stale")
        session_cookie = self.authenticated_session_cookie(user)
        with self.browser_session() as browser:
            context = self.authenticated_context(browser, session_cookie)
            page = context.new_page()
            try:
                page.goto(f"{self.live_server_url}{reverse('users:dashboard')}")

                expect(page).to_have_url(re.compile(r".*/users/login/.*"))
                expect(page.locator("[data-legal-review-form]")).to_be_visible()
                expect(page.locator("[data-legal-review-form]")).to_contain_text("Accept and continue with Google")
            finally:
                context.close()

    def test_owner_can_archive_listing_and_existing_participant_can_open_archived_detail(self):
        owner = self.create_user("owner-e2e", "owner-e2e@bc.edu", profile_complete=True)
        participant = self.create_user("participant-e2e", "participant-e2e@bc.edu", profile_complete=True)
        listing = self.create_listing(owner)
        conversation = ListingConversation.objects.create(listing=listing, owner=owner, participant=participant)
        conversation.add_message(sender=participant, body="Interested in this place.")
        detail_url = f"{self.live_server_url}{reverse('listings:detail', args=[listing.pk])}"
        owner_session_cookie = self.authenticated_session_cookie(owner)
        participant_session_cookie = self.authenticated_session_cookie(participant)

        with self.browser_session() as browser:
            owner_context = self.authenticated_context(browser, owner_session_cookie)
            owner_page = owner_context.new_page()
            try:
                owner_page.goto(f"{self.live_server_url}{reverse('users:posts')}")
                owner_page.get_by_role("button", name="Archive").click()
                owner_page.get_by_role("button", name="Confirm archive").click()

                expect(owner_page.get_by_text("Archived")).to_be_visible()
                owner_page.goto(detail_url)
                expect(owner_page.get_by_text("Listing archived")).to_be_visible()
            finally:
                owner_context.close()

            participant_context = self.authenticated_context(browser, participant_session_cookie)
            participant_page = participant_context.new_page()
            try:
                participant_page.goto(detail_url)
                expect(participant_page.get_by_text("Listing archived")).to_be_visible()
            finally:
                participant_context.close()

    def test_roommates_surface_uses_single_canonical_navigation(self):
        student = self.create_user("roommate-user", "roommate-user@bc.edu", first_name="Riley", profile_complete=True)
        session_cookie = self.authenticated_session_cookie(student)
        with self.browser_session() as browser:
            context = self.authenticated_context(browser, session_cookie)
            page = context.new_page()
            try:
                page.goto(f"{self.live_server_url}{reverse('roommates:hub')}")

                expect(page.get_by_role("link", name="Posts")).to_be_visible()
                expect(page.get_by_role("link", name="People")).to_be_visible()
                expect(page.get_by_role("link", name="Groups")).to_be_visible()
                expect(page.locator("body")).not_to_contain_text("Group match")

                page.get_by_role("link", name="People").click()
                expect(page).to_have_url(re.compile(r".*/roommates/\?tab=people$"))
                page.get_by_role("link", name="Groups").click()
                expect(page).to_have_url(re.compile(r".*/roommates/\?tab=groups$"))
            finally:
                context.close()

    def test_listings_page_updates_results_without_full_reload(self):
        viewer = self.create_user("listings-viewer", "listings-viewer@bc.edu")
        self.create_listing(viewer, title="Beacon search hit")
        self.create_listing(viewer, title="Cleveland Circle listing", latitude=42.3365, longitude=-71.1695)
        session_cookie = self.authenticated_session_cookie(viewer)
        with self.browser_session() as browser:
            context = self.authenticated_context(browser, session_cookie)
            page = context.new_page()
            try:
                page.route(
                    "https://example.test/styles/mock.json",
                    lambda route: route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({"version": 8, "sources": {}, "layers": []}),
                    ),
                )
                page.goto(f"{self.live_server_url}{reverse('listings:listing_list')}")

                expect(page.locator("[data-listings-map-root]")).to_be_visible()
                expect(page.locator("[data-listings-results-list]")).to_be_visible()

                with page.expect_response(
                    lambda response: "/listings/results/" in response.url and "Beacon" in response.url
                ):
                    page.locator("#filter-query").fill("Beacon")

                expect(page.locator("[data-listings-results-content]")).to_contain_text("Beacon search hit")
                expect(page.locator("[data-listings-results-content]")).not_to_contain_text("Cleveland Circle listing")
            finally:
                context.close()

    def test_message_draft_is_preserved_when_socket_drops_before_ack(self):
        owner = self.create_user("socket-owner", "socket-owner@bc.edu")
        participant = self.create_user("socket-participant", "socket-participant@bc.edu")
        listing = self.create_listing(owner)
        conversation = ListingConversation.objects.create(listing=listing, owner=owner, participant=participant)
        conversation.add_message(sender=participant, body="Is this still available?")

        init_script = """
            class FailingWebSocket {
                static OPEN = 1;
                static CLOSED = 3;

                constructor(url) {
                    this.url = url;
                    this.readyState = FailingWebSocket.OPEN;
                    this.listeners = {};
                    setTimeout(() => this.emit("open", {}), 0);
                }

                addEventListener(type, handler) {
                    this.listeners[type] = this.listeners[type] || [];
                    this.listeners[type].push(handler);
                }

                send(payload) {
                    this.lastPayload = payload;
                    this.readyState = FailingWebSocket.CLOSED;
                    setTimeout(() => this.emit("close", { code: 1011 }), 0);
                }

                close() {
                    this.readyState = FailingWebSocket.CLOSED;
                }

                emit(type, event) {
                    for (const handler of this.listeners[type] || []) {
                        handler(event);
                    }
                }
            }

            window.WebSocket = FailingWebSocket;
        """
        session_cookie = self.authenticated_session_cookie(owner)
        with self.browser_session() as browser:
            context = self.authenticated_context(browser, session_cookie, init_script=init_script)
            page = context.new_page()
            try:
                page.goto(f"{self.live_server_url}{reverse('communications:messages')}")

                textarea = page.locator("[data-reply-form] textarea")
                submit_button = page.locator("[data-message-submit]")

                textarea.fill("Draft survives socket failure.")
                submit_button.click()

                expect(page.locator("[data-message-errors]")).to_contain_text(
                    "Realtime connection dropped before delivery. Your draft is still here."
                )
                expect(textarea).to_have_value("Draft survives socket failure.")
                expect(submit_button).to_be_enabled()
            finally:
                context.close()
