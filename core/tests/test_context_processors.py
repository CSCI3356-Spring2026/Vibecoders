from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.test import RequestFactory, TestCase, override_settings

from core.context_processors import branding


class BrandingContextProcessorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_anonymous_user_gets_zero_unread_count_without_summary_lookup(self):
        request = self.factory.get("/")
        request.user = AnonymousUser()

        with patch("core.context_processors.conversation_summary_for_user") as summary_for_user:
            context = branding(request)

        self.assertEqual(context["global_unread_conversations_count"], 0)
        summary_for_user.assert_not_called()

    @override_settings(GLOBAL_UNREAD_COUNT_CACHE_SECONDS=30)
    def test_authenticated_unread_count_is_cached_per_user(self):
        user = get_user_model().objects.create_user(username="cached-count", email="cached-count@bc.edu")
        request = self.factory.get("/")
        request.user = user

        with patch(
            "core.context_processors.conversation_summary_for_user",
            return_value={"unread_conversations_count": 4},
        ) as summary_for_user:
            first_context = branding(request)
            second_context = branding(request)

        self.assertEqual(first_context["global_unread_conversations_count"], 4)
        self.assertEqual(second_context["global_unread_conversations_count"], 4)
        summary_for_user.assert_called_once_with(user)

    @override_settings(GLOBAL_UNREAD_COUNT_CACHE_SECONDS=30)
    def test_authenticated_unread_count_cache_is_scoped_per_user(self):
        first_user = get_user_model().objects.create_user(username="first-count", email="first-count@bc.edu")
        second_user = get_user_model().objects.create_user(username="second-count", email="second-count@bc.edu")
        first_request = self.factory.get("/")
        second_request = self.factory.get("/")
        first_request.user = first_user
        second_request.user = second_user

        def summary_for_user(user):
            return {"unread_conversations_count": 3 if user == first_user else 7}

        with patch("core.context_processors.conversation_summary_for_user", side_effect=summary_for_user):
            first_context = branding(first_request)
            second_context = branding(second_request)

        self.assertEqual(first_context["global_unread_conversations_count"], 3)
        self.assertEqual(second_context["global_unread_conversations_count"], 7)

    @override_settings(GLOBAL_UNREAD_COUNT_CACHE_SECONDS=0)
    def test_authenticated_unread_count_cache_can_be_disabled(self):
        user = get_user_model().objects.create_user(username="uncached-count", email="uncached-count@bc.edu")
        request = self.factory.get("/")
        request.user = user

        with patch(
            "core.context_processors.conversation_summary_for_user",
            return_value={"unread_conversations_count": 2},
        ) as summary_for_user:
            first_context = branding(request)
            second_context = branding(request)

        self.assertEqual(first_context["global_unread_conversations_count"], 2)
        self.assertEqual(second_context["global_unread_conversations_count"], 2)
        self.assertEqual(summary_for_user.call_count, 2)
