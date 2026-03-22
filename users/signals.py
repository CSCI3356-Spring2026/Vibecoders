from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver

from .legal import get_pending_legal_acceptance, persist_legal_acceptance_for_user
from .models import AdminProfile, Role, StudentProfile
from .profile_images import sync_profile_image_for_user

User = get_user_model()


@receiver(user_logged_in)
def persist_login_legal_acceptance(sender, request, user, **kwargs):
    payload = get_pending_legal_acceptance(request)
    if payload is None:
        sync_profile_image_for_user(user)
        return
    persist_legal_acceptance_for_user(user, payload)
    sync_profile_image_for_user(user)


@receiver(post_save, sender=User)
def sync_role_profile(sender, instance, **kwargs):
    if instance.role == Role.STUDENT:
        StudentProfile.objects.get_or_create(user=instance)
        AdminProfile.objects.filter(user=instance).delete()
    elif instance.role == Role.ADMIN:
        AdminProfile.objects.get_or_create(user=instance)
        StudentProfile.objects.filter(user=instance).delete()
    else:
        StudentProfile.objects.filter(user=instance).delete()
        AdminProfile.objects.filter(user=instance).delete()
