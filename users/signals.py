from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .legal import get_pending_legal_acceptance, persist_legal_acceptance_for_user


@receiver(user_logged_in)
def persist_login_legal_acceptance(sender, request, user, **kwargs):
    payload = get_pending_legal_acceptance(request)
    if payload is None:
        return
    persist_legal_acceptance_for_user(user, payload)
