from django.conf import settings
from django.test import SimpleTestCase


class TestSettingsTests(SimpleTestCase):
    def test_test_suite_uses_fast_password_hasher(self):
        self.assertEqual(settings.PASSWORD_HASHERS, ["django.contrib.auth.hashers.MD5PasswordHasher"])
