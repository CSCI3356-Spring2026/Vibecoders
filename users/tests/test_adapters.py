from unittest.mock import MagicMock

from allauth.core.exceptions import ImmediateHttpResponse
from django.contrib import messages
from django.test import RequestFactory, TestCase

from ..adapters import MarketplaceSocialAccountAdapter, NoSignupAccountAdapter
from ..models import Role
from .helpers import add_middleware, message_texts


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


class MarketplaceSocialAccountAdapterTests(TestCase):
    def make_sociallogin(self, email):
        sociallogin = MagicMock()
        sociallogin.account.extra_data = {"email": email}
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
        sociallogin = self.make_sociallogin("")

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
        sociallogin = self.make_sociallogin("")

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
