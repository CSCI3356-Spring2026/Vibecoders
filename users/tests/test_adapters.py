from unittest.mock import MagicMock

from allauth.core.exceptions import ImmediateHttpResponse
from django.contrib import messages
from django.test import RequestFactory, TestCase

from ..adapters import BCEmailAdapter, NoSignupAccountAdapter
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


class BCEmailAdapterTests(TestCase):
    def make_sociallogin(self, email):
        sociallogin = MagicMock()
        sociallogin.account.extra_data = {"email": email}
        return sociallogin

    def test_bc_email_signup_allowed(self):
        adapter = BCEmailAdapter()
        request = RequestFactory().get("/")
        sociallogin = self.make_sociallogin("eagle@bc.edu")

        self.assertTrue(adapter.is_open_for_signup(request, sociallogin))

    def test_invalid_signup_emails_are_rejected(self):
        adapter = BCEmailAdapter()

        for email in ("user@gmail.com", ""):
            with self.subTest(email=email):
                request = add_middleware(RequestFactory().get("/"))
                sociallogin = self.make_sociallogin(email)

                with self.assertRaises(ImmediateHttpResponse) as ctx:
                    adapter.is_open_for_signup(request, sociallogin)

                self.assertEqual(ctx.exception.response.url, "/users/login/")
                self.assertIn(adapter.error_message, message_texts(request))

    def test_bc_email_login_allowed(self):
        adapter = BCEmailAdapter()
        request = RequestFactory().get("/")
        sociallogin = self.make_sociallogin("eagle@bc.edu")

        adapter.pre_social_login(request, sociallogin)

    def test_non_bc_email_login_raises(self):
        adapter = BCEmailAdapter()
        request = add_middleware(RequestFactory().get("/"))
        sociallogin = self.make_sociallogin("user@gmail.com")

        with self.assertRaises(ImmediateHttpResponse) as ctx:
            adapter.pre_social_login(request, sociallogin)

        self.assertEqual(ctx.exception.response.url, "/users/login/")
        self.assertIn(adapter.error_message, message_texts(request))
