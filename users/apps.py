from django.apps import AppConfig
from django.conf import settings


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "users"

    def ready(self):
        from . import signals  # noqa: F401

        if settings.RUNNING_TESTS:
            from .test_client import patch_test_clients

            patch_test_clients()
