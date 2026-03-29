from django.test import RequestFactory, SimpleTestCase, override_settings

from core.rate_limits import request_rate_limit_identifier


class RateLimitIdentifierTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @override_settings(TRUST_X_FORWARDED_FOR=False)
    def test_identifier_ignores_forwarded_for_when_proxy_trust_is_disabled(self):
        request = self.factory.get(
            "/",
            HTTP_X_FORWARDED_FOR="1.2.3.4",
            HTTP_USER_AGENT="PadlyTestAgent/1.0",
            REMOTE_ADDR="5.6.7.8",
        )

        identifier = request_rate_limit_identifier(request)

        self.assertTrue(identifier.startswith("5.6.7.8:"))

    @override_settings(TRUST_X_FORWARDED_FOR=True)
    def test_identifier_uses_forwarded_for_when_proxy_trust_is_enabled(self):
        request = self.factory.get(
            "/",
            HTTP_X_FORWARDED_FOR="1.2.3.4, 9.9.9.9",
            HTTP_USER_AGENT="PadlyTestAgent/1.0",
            REMOTE_ADDR="5.6.7.8",
        )

        identifier = request_rate_limit_identifier(request)

        self.assertTrue(identifier.startswith("1.2.3.4:"))
