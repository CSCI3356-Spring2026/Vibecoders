import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib import messages
from django.test import RequestFactory, TestCase
from django.utils import timezone

from ..adapters import MarketplaceSocialAccountAdapter, NoSignupAccountAdapter
from ..legal import is_legal_review_required, set_pending_legal_acceptance
from ..models import Role
from .helpers import User, add_middleware, message_texts


class NoSignupAccountAdapterTests(TestCase):
    def test_regular_signup_disabled(self):
        adapter = NoSignupAccountAdapter()
        request = RequestFactory().get("/accounts/signup/")

        self.assertFalse(adapter.is_open_for_signup(request))

    def test_auth_status_messages_are_suppressed(self):
        adapter = NoSignupAccountAdapter()

        for template_name in ("account/messages/logged_in.txt", "account/messages/logged_out.txt"):
            with self.subTest(template_name=template_name):
                request = add_middleware(RequestFactory().get("/users/login/"))
                adapter.add_message(request, messages.SUCCESS, template_name)
                self.assertEqual(message_texts(request), [])


class AuthSettingsTests(TestCase):
    def test_google_email_authentication_is_enabled(self):
        self.assertTrue(settings.SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT)
        self.assertTrue(settings.SOCIALACCOUNT_PROVIDERS["google"]["EMAIL_AUTHENTICATION"])
        self.assertEqual(settings.LOGIN_URL, "/accounts/login/")

    def test_production_settings_require_explicit_allowed_hosts(self):
        env = os.environ.copy()
        env.update(
            {
                "DJANGO_DEBUG": "false",
                "DJANGO_SECRET_KEY": "test-secret",
                "DJANGO_ALLOWED_HOSTS": "",
                "DJANGO_CSRF_TRUSTED_ORIGINS": "",
                "CHANNEL_REDIS_URL": "redis://localhost:6379/0",
            }
        )
        result = subprocess.run(
            [sys.executable, "-c", "import vibecoders.settings"],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Set DJANGO_ALLOWED_HOSTS when running with DJANGO_DEBUG=false.", result.stderr)


class MarketplaceSocialAccountAdapterTests(TestCase):
    def make_sociallogin(self, email, verified=True, user=None, picture="https://example.com/avatar.jpg"):
        sociallogin = MagicMock()
        sociallogin.account.extra_data = {
            "email": email,
            "email_verified": verified,
            "picture": picture,
        }
        sociallogin.user = user or User()
        return sociallogin

    def test_student_email_signup_allowed(self):
        adapter = MarketplaceSocialAccountAdapter()
        request = add_middleware(RequestFactory().get("/"))
        set_pending_legal_acceptance(request)
        sociallogin = self.make_sociallogin("eagle@bc.edu")

        self.assertTrue(adapter.is_open_for_signup(request, sociallogin))

    def test_external_email_signup_allowed(self):
        adapter = MarketplaceSocialAccountAdapter()
        request = add_middleware(RequestFactory().get("/"))
        set_pending_legal_acceptance(request)
        sociallogin = self.make_sociallogin("agent@gmail.com")

        self.assertTrue(adapter.is_open_for_signup(request, sociallogin))

    def test_signup_requires_legal_acceptance(self):
        adapter = MarketplaceSocialAccountAdapter()
        request = add_middleware(RequestFactory().get("/"))
        sociallogin = self.make_sociallogin("eagle@bc.edu")

        with self.assertRaises(ImmediateHttpResponse) as ctx:
            adapter.is_open_for_signup(request, sociallogin)

        self.assertEqual(ctx.exception.response.url, "/users/login/")
        self.assertIn(adapter.legal_error_message, message_texts(request))

    def test_missing_signup_email_is_rejected(self):
        adapter = MarketplaceSocialAccountAdapter()

        request = add_middleware(RequestFactory().get("/"))
        set_pending_legal_acceptance(request)
        sociallogin = self.make_sociallogin("", verified=False)

        with self.assertRaises(ImmediateHttpResponse) as ctx:
            adapter.is_open_for_signup(request, sociallogin)

        self.assertEqual(ctx.exception.response.url, "/users/login/")
        self.assertIn(adapter.error_message, message_texts(request))

    def test_unverified_signup_email_is_rejected(self):
        adapter = MarketplaceSocialAccountAdapter()
        request = add_middleware(RequestFactory().get("/"))
        set_pending_legal_acceptance(request)
        sociallogin = self.make_sociallogin("eagle@bc.edu", verified=False)

        with self.assertRaises(ImmediateHttpResponse) as ctx:
            adapter.is_open_for_signup(request, sociallogin)

        self.assertEqual(ctx.exception.response.url, "/users/login/")
        self.assertIn(adapter.error_message, message_texts(request))

    def test_student_email_login_allowed(self):
        adapter = MarketplaceSocialAccountAdapter()
        request = add_middleware(RequestFactory().get("/"))
        set_pending_legal_acceptance(request)
        sociallogin = self.make_sociallogin("eagle@bc.edu")

        adapter.pre_social_login(request, sociallogin)

    def test_external_email_login_allowed(self):
        adapter = MarketplaceSocialAccountAdapter()
        request = add_middleware(RequestFactory().get("/"))
        set_pending_legal_acceptance(request)
        sociallogin = self.make_sociallogin("agent@gmail.com")

        adapter.pre_social_login(request, sociallogin)

    def test_login_requires_legal_acceptance(self):
        adapter = MarketplaceSocialAccountAdapter()
        request = add_middleware(RequestFactory().get("/"))
        sociallogin = self.make_sociallogin("eagle@bc.edu")

        with self.assertRaises(ImmediateHttpResponse) as ctx:
            adapter.pre_social_login(request, sociallogin)

        self.assertEqual(ctx.exception.response.url, "/users/login/")
        self.assertIn(adapter.legal_error_message, message_texts(request))
        self.assertTrue(is_legal_review_required(request))

    def test_existing_user_with_current_legal_acceptance_can_login_without_pending_session_acceptance(self):
        user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")
        accepted_at = timezone.now()
        user.terms_accepted_at = accepted_at
        user.privacy_accepted_at = accepted_at
        user.legal_policy_version = settings.LEGAL_DOCUMENT_VERSION
        user.save(update_fields=["terms_accepted_at", "privacy_accepted_at", "legal_policy_version"])

        adapter = MarketplaceSocialAccountAdapter()
        request = add_middleware(RequestFactory().get("/"))
        sociallogin = self.make_sociallogin("eagle@bc.edu", user=user)

        adapter.pre_social_login(request, sociallogin)

    def test_missing_email_login_raises(self):
        adapter = MarketplaceSocialAccountAdapter()
        request = add_middleware(RequestFactory().get("/"))
        set_pending_legal_acceptance(request)
        sociallogin = self.make_sociallogin("", verified=False)

        with self.assertRaises(ImmediateHttpResponse) as ctx:
            adapter.pre_social_login(request, sociallogin)

        self.assertEqual(ctx.exception.response.url, "/users/login/")
        self.assertIn(adapter.error_message, message_texts(request))

    def test_unverified_email_login_raises(self):
        adapter = MarketplaceSocialAccountAdapter()
        request = add_middleware(RequestFactory().get("/"))
        set_pending_legal_acceptance(request)
        sociallogin = self.make_sociallogin("eagle@bc.edu", verified=False)

        with self.assertRaises(ImmediateHttpResponse) as ctx:
            adapter.pre_social_login(request, sociallogin)

        self.assertEqual(ctx.exception.response.url, "/users/login/")
        self.assertIn(adapter.error_message, message_texts(request))

    def test_populate_user_assigns_student_role_for_bc_email(self):
        adapter = MarketplaceSocialAccountAdapter()
        sociallogin = self.make_sociallogin("student@bc.edu")

        user = adapter.populate_user(RequestFactory().get("/"), sociallogin, {"email": "student@bc.edu"})

        self.assertEqual(user.username, "student")
        self.assertEqual(user.role, Role.STUDENT)
        self.assertEqual(user.profile_image_url, "https://example.com/avatar.jpg")

    def test_populate_user_ignores_non_http_profile_image_urls(self):
        adapter = MarketplaceSocialAccountAdapter()
        sociallogin = self.make_sociallogin("student@bc.edu", picture="javascript:alert(1)")

        user = adapter.populate_user(RequestFactory().get("/"), sociallogin, {"email": "student@bc.edu"})

        self.assertEqual(user.profile_image_url, "")

    def test_populate_user_assigns_realtor_role_for_external_email(self):
        adapter = MarketplaceSocialAccountAdapter()
        sociallogin = self.make_sociallogin("agent@gmail.com")

        user = adapter.populate_user(RequestFactory().get("/"), sociallogin, {"email": "agent@gmail.com"})

        self.assertEqual(user.username, "agent")
        self.assertEqual(user.role, Role.REALTOR)

    def test_populate_user_generates_unique_username_for_matching_local_parts(self):
        User.objects.create_user(username="alex", email="alex@bc.edu", password="test")
        adapter = MarketplaceSocialAccountAdapter()
        sociallogin = self.make_sociallogin("alex@gmail.com")

        user = adapter.populate_user(RequestFactory().get("/"), sociallogin, {"email": "alex@gmail.com"})

        self.assertEqual(user.username, "alex-2")

    def test_populate_user_normalizes_email(self):
        adapter = MarketplaceSocialAccountAdapter()
        sociallogin = self.make_sociallogin("Student@BC.edu")

        user = adapter.populate_user(RequestFactory().get("/"), sociallogin, {"email": "Student@BC.edu"})

        self.assertEqual(user.email, "student@bc.edu")
        self.assertEqual(user.username, "student")
        self.assertEqual(user.role, Role.STUDENT)

    def test_populate_user_does_not_override_existing_user_identity(self):
        existing_user = User.objects.create_user(
            username="admin-user",
            email="admin@bc.edu",
            password="test",
            role=Role.ADMIN,
        )
        adapter = MarketplaceSocialAccountAdapter()
        sociallogin = self.make_sociallogin("admin@bc.edu", user=existing_user)

        user = adapter.populate_user(RequestFactory().get("/"), sociallogin, {"email": "admin@bc.edu"})

        self.assertEqual(user.username, "admin-user")
        self.assertEqual(user.role, Role.ADMIN)

    def test_pre_social_login_updates_existing_user_profile_image(self):
        user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")
        adapter = MarketplaceSocialAccountAdapter()
        request = add_middleware(RequestFactory().get("/"))
        set_pending_legal_acceptance(request)
        sociallogin = self.make_sociallogin(
            "eagle@bc.edu",
            user=user,
            picture="https://example.com/updated-avatar.jpg",
        )

        adapter.pre_social_login(request, sociallogin)
        user.refresh_from_db()

        self.assertEqual(user.profile_image_url, "https://example.com/updated-avatar.jpg")

    def test_pre_social_login_keeps_existing_profile_image_when_google_picture_missing(self):
        user = User.objects.create_user(
            username="eagle",
            email="eagle@bc.edu",
            password="test",
            profile_image_url="https://example.com/original-avatar.jpg",
        )
        SocialAccount.objects.create(
            user=user,
            provider="google",
            uid="google-user-1",
            extra_data={"email": "eagle@bc.edu", "email_verified": True},
        )
        adapter = MarketplaceSocialAccountAdapter()
        request = add_middleware(RequestFactory().get("/"))
        set_pending_legal_acceptance(request)
        sociallogin = self.make_sociallogin("eagle@bc.edu", user=user, picture="")

        adapter.pre_social_login(request, sociallogin)
        user.refresh_from_db()

        self.assertEqual(user.profile_image_url, "https://example.com/original-avatar.jpg")

    def test_pre_social_login_ignores_non_http_profile_image_urls(self):
        user = User.objects.create_user(
            username="eagle",
            email="eagle@bc.edu",
            password="test",
            profile_image_url="https://example.com/original-avatar.jpg",
        )
        adapter = MarketplaceSocialAccountAdapter()
        request = add_middleware(RequestFactory().get("/"))
        set_pending_legal_acceptance(request)
        sociallogin = self.make_sociallogin("eagle@bc.edu", user=user, picture="ftp://example.com/avatar.jpg")

        adapter.pre_social_login(request, sociallogin)
        user.refresh_from_db()

        self.assertEqual(user.profile_image_url, "https://example.com/original-avatar.jpg")
