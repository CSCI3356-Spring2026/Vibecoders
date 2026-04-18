from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .legal import clear_pending_legal_acceptance, get_pending_legal_acceptance, persist_legal_acceptance_for_user
from .profile_images import sync_profile_image_for_user
from .profile_integrity import (
    clear_profile_completion,
    should_clear_completion_on_role_transition,
    sync_profiles_for_role,
)
from .session_security import mark_recent_auth

User = get_user_model()


@receiver(user_logged_in)
def persist_login_legal_acceptance(sender, request, user, **kwargs):
    request_path = getattr(request, "path", "") or ""
    if request_path.startswith("/accounts/"):
        mark_recent_auth(request)
    payload = get_pending_legal_acceptance(request)
    if payload is None:
        sync_profile_image_for_user(user)
        return
    persist_legal_acceptance_for_user(user, payload)
    clear_pending_legal_acceptance(request)
    sync_profile_image_for_user(user)


@receiver(post_save, sender=User)
def sync_role_profile(sender, instance, **kwargs):
    previous_role = getattr(instance, "_previous_role", None)
    sync_result = sync_profiles_for_role(instance)
    if should_clear_completion_on_role_transition(instance, previous_role, sync_result):
        clear_profile_completion(instance)


@receiver(pre_save, sender=User)
def capture_previous_role(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_role = None
        return

    instance._previous_role = sender._default_manager.filter(pk=instance.pk).values_list("role", flat=True).first()
