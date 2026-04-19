from django.contrib.auth import get_user_model
from django.test.client import AsyncClient, Client

from .legal import build_legal_acceptance_payload, persist_legal_acceptance_for_user

_PATCHED = False


def _ensure_current_legal_acceptance(user):
    if not getattr(user, "is_authenticated", False):
        return
    if getattr(user, "has_current_legal_acceptance", False):
        return
    if any(
        (
            getattr(user, "terms_accepted_at", None),
            getattr(user, "privacy_accepted_at", None),
            getattr(user, "legal_policy_version", ""),
        )
    ):
        return

    persist_legal_acceptance_for_user(user, build_legal_acceptance_payload())


def patch_test_clients():
    global _PATCHED
    if _PATCHED:
        return

    original_force_login = Client.force_login
    original_login = Client.login

    def force_login(self, user, backend=None):
        _ensure_current_legal_acceptance(user)
        return original_force_login(self, user, backend=backend)

    def login(self, **credentials):
        success = original_login(self, **credentials)
        if not success:
            return success

        user_id = self.session.get("_auth_user_id")
        if not user_id:
            return success

        user_model = get_user_model()
        try:
            current_user = user_model._default_manager.get(pk=user_id)
        except user_model.DoesNotExist:
            return success

        _ensure_current_legal_acceptance(current_user)
        return success

    Client.force_login = force_login
    Client.login = login

    original_async_force_login = AsyncClient.force_login

    async def async_force_login(self, user, backend=None):
        _ensure_current_legal_acceptance(user)
        return await original_async_force_login(self, user, backend=backend)

    AsyncClient.force_login = async_force_login
    _PATCHED = True
