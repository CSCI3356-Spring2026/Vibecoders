from unittest.mock import MagicMock

from allauth.core.exceptions import ImmediateHttpResponse
from django.conf import settings
from django.contrib import messages
from django.test import RequestFactory, TestCase

from ..adapters import MarketplaceSocialAccountAdapter, NoSignupAccountAdapter
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


class MarketplaceSocialAccountAdapterTests(TestCase):
    def make_sociallogin(self, email, verified=True, user=None):
        sociallogin = MagicMock()
        sociallogin.account.extra_data = {
            "email": email,
            "email_verified": verified,
        }
        sociallogin.user = user or User()
        return sociallogin

    def test_student_email_signup_allowed(self):
        adapter = MarketplaceSocialAccountAdapter()
        request = RequestFactory().get("/")
        sociallogin = self.make_sociallogin("eagle@bc.edu")

        self.assertTrue(adapter.is_open_for_signup(request, sociallogin))

    def test_external_email_signup_allowed(self):
        adapter = MarketplaceSocialAccountAdapter()
        request = RequestFactory().get("/")
        sociallogin = self.make_sociallogin("agent@gmail.com")

        self.assertTrue(adapter.is_open_for_signup(request, sociallogin))

    def test_missing_signup_email_is_rejected(self):
        adapter = MarketplaceSocialAccountAdapter()

        request = add_middleware(RequestFactory().get("/"))
        sociallogin = self.make_sociallogin("", verified=False)

        with self.assertRaises(ImmediateHttpResponse) as ctx:
            adapter.is_open_for_signup(request, sociallogin)

        self.assertEqual(ctx.exception.response.url, "/users/login/")
        self.assertIn(adapter.error_message, message_texts(request))

    def test_unverified_signup_email_is_rejected(self):
        adapter = MarketplaceSocialAccountAdapter()
        request = add_middleware(RequestFactory().get("/"))
        sociallogin = self.make_sociallogin("eagle@bc.edu", verified=False)

        with self.assertRaises(ImmediateHttpResponse) as ctx:
            adapter.is_open_for_signup(request, sociallogin)

        self.assertEqual(ctx.exception.response.url, "/users/login/")
        self.assertIn(adapter.error_message, message_texts(request))

    def test_student_email_login_allowed(self):
        adapter = MarketplaceSocialAccountAdapter()
        request = RequestFactory().get("/")
        sociallogin = self.make_sociallogin("eagle@bc.edu")

        adapter.pre_social_login(request, sociallogin)

    def test_external_email_login_allowed(self):
        adapter = MarketplaceSocialAccountAdapter()
        request = RequestFactory().get("/")
        sociallogin = self.make_sociallogin("agent@gmail.com")

        adapter.pre_social_login(request, sociallogin)

    def test_missing_email_login_raises(self):
        adapter = MarketplaceSocialAccountAdapter()
        request = add_middleware(RequestFactory().get("/"))
        sociallogin = self.make_sociallogin("", verified=False)

        with self.assertRaises(ImmediateHttpResponse) as ctx:
            adapter.pre_social_login(request, sociallogin)

        self.assertEqual(ctx.exception.response.url, "/users/login/")
        self.assertIn(adapter.error_message, message_texts(request))

    def test_unverified_email_login_raises(self):
        adapter = MarketplaceSocialAccountAdapter()
        request = add_middleware(RequestFactory().get("/"))
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
