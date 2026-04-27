from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .audit import record_audit_event


def _anonymized_username(user):
    return f"deleted-user-{user.pk}"


def _anonymized_email(user):
    return f"deleted-user-{user.pk}@deleted.padly.invalid"


def _resolve_user_instance(user):
    if user is None:
        return None
    if hasattr(type(user), "_default_manager"):
        return user
    return get_user_model()._default_manager.get(pk=user.pk)


def deactivate_user(user, *, actor=None, reason=""):
    user = _resolve_user_instance(user)
    actor = _resolve_user_instance(actor)
    timestamp = timezone.now()
    user.is_active = False
    user.deactivated_at = timestamp
    user.deactivated_by = actor
    user.deactivation_reason = reason
    user.save(update_fields=["is_active", "deactivated_at", "deactivated_by", "deactivation_reason"])
    record_audit_event(
        action="user.deactivated",
        actor=actor,
        target=user,
        reason=reason,
        metadata={"deleted_at": getattr(user, "deleted_at", None) and user.deleted_at.isoformat()},
    )
    return timestamp


def reactivate_user(user, *, actor=None, reason=""):
    user = _resolve_user_instance(user)
    actor = _resolve_user_instance(actor)
    user.is_active = True
    user.deactivated_at = None
    user.deactivated_by = None
    user.deactivation_reason = ""
    user.save(update_fields=["is_active", "deactivated_at", "deactivated_by", "deactivation_reason"])
    record_audit_event(
        action="user.reactivated",
        actor=actor,
        target=user,
        reason=reason,
    )


def anonymize_and_deactivate_user(user, *, actor=None, reason="Account deletion request"):
    user = _resolve_user_instance(user)
    actor = _resolve_user_instance(actor)
    timestamp = timezone.now()
    avatar_name = user.uploaded_avatar.name if user.uploaded_avatar else ""
    storage = user.uploaded_avatar.storage if user.uploaded_avatar else None
    try:
        student_profile = user.student_profile
    except Exception:
        student_profile = None
    try:
        admin_profile = user.admin_profile
    except Exception:
        admin_profile = None

    with transaction.atomic():
        user.files.all().delete()
        user.emailaddress_set.all().delete()
        user.socialaccount_set.all().delete()
        profile_updates = {
            "preferred_name": "",
            "gender": "",
            "gender_other": "",
            "bio": "",
        }
        if student_profile is not None:
            student_profile.age = None
            student_profile.major = ""
            student_profile.messy_level = None
            student_profile.guest_level = None
            student_profile.bedtime = None
            student_profile.noise_level = None
            student_profile.drink = None
            student_profile.party = None
            student_profile.smoke = False
            student_profile.pets = False
            for field_name, value in profile_updates.items():
                setattr(student_profile, field_name, value)
            student_profile.save()
        if admin_profile is not None:
            admin_profile.age = None
            for field_name, value in profile_updates.items():
                setattr(admin_profile, field_name, value)
            admin_profile.save()

        update_values = {
            "is_active": False,
            "deactivated_at": timestamp,
            "deactivated_by": actor,
            "deactivation_reason": reason,
            "deleted_at": timestamp,
            "email": _anonymized_email(user),
            "username": _anonymized_username(user),
            "first_name": "Deleted",
            "last_name": "User",
            "profile_image_url": "",
            "uploaded_avatar": "",
            "terms_accepted_at": None,
            "privacy_accepted_at": None,
            "legal_policy_version": "",
        }
        user_manager = get_user_model()._default_manager
        user_manager.filter(pk=user.pk).update(**update_values)
        for field_name, value in update_values.items():
            setattr(user, field_name, value)
        user.set_unusable_password()
        user_manager.filter(pk=user.pk).update(password=user.password)

        record_audit_event(
            action="user.anonymized",
            actor=actor,
            target=user,
            reason=reason,
            metadata={"deleted_at": timestamp.isoformat()},
        )

    if avatar_name and storage is not None:
        transaction.on_commit(lambda: storage.delete(avatar_name))
    return timestamp
