from django.utils import timezone

from .forms import AdminProfileForm, StudentProfileForm
from .models import ADMIN_PROFILE_COPY_FIELDS, STAFF_ROLE_VALUES, AdminProfile, Role, StudentProfile


def _completion_value_present(value):
    return value not in (None, "")


def completion_fields_for_role(role):
    if role == Role.STUDENT:
        return StudentProfileForm.completion_fields
    if role == Role.REALTOR:
        return (*AdminProfileForm.completion_fields, "organization_type")
    if role in STAFF_ROLE_VALUES:
        return AdminProfileForm.completion_fields
    return ()


def _student_profile_for_user(user):
    try:
        return user.student_profile
    except StudentProfile.DoesNotExist:
        return None


def _admin_profile_for_user(user):
    try:
        return user.admin_profile
    except AdminProfile.DoesNotExist:
        return None


def current_completion_profile(user):
    if user.role == Role.STUDENT:
        return _student_profile_for_user(user)
    if user.role in STAFF_ROLE_VALUES | {Role.REALTOR}:
        return _admin_profile_for_user(user)
    return None


def profile_satisfies_completion_requirements(user):
    completion_fields = completion_fields_for_role(user.role)
    if not completion_fields:
        return False

    profile = current_completion_profile(user)
    if profile is None:
        return False

    return all(_completion_value_present(getattr(profile, field_name, None)) for field_name in completion_fields)


def _seed_admin_profile_from_student_profile(admin_profile, student_profile):
    if student_profile is None:
        return

    update_fields = []
    for field_name in ADMIN_PROFILE_COPY_FIELDS:
        value = getattr(student_profile, field_name, None)
        if not _completion_value_present(value):
            continue
        setattr(admin_profile, field_name, value)
        update_fields.append(field_name)

    if update_fields:
        admin_profile.save(update_fields=update_fields)


def sync_profiles_for_role(user):
    student_created = False
    admin_created = False
    student_profile = _student_profile_for_user(user)

    if user.role == Role.STUDENT:
        _, student_created = StudentProfile.objects.get_or_create(user=user)
        AdminProfile.objects.filter(user=user).delete()
    elif user.role in STAFF_ROLE_VALUES:
        admin_profile, admin_created = AdminProfile.objects.get_or_create(user=user)
        if admin_created:
            _seed_admin_profile_from_student_profile(admin_profile, student_profile)
    elif user.role == Role.REALTOR:
        admin_profile, admin_created = AdminProfile.objects.get_or_create(user=user)
        if admin_created:
            _seed_admin_profile_from_student_profile(admin_profile, student_profile)
        StudentProfile.objects.filter(user=user).delete()
    else:
        StudentProfile.objects.filter(user=user).delete()
        AdminProfile.objects.filter(user=user).delete()

    return {
        "student_created": student_created,
        "admin_created": admin_created,
    }


def should_clear_completion_on_role_transition(user, previous_role, sync_result):
    if previous_role == user.role:
        return False
    if user.role == Role.REALTOR:
        return True
    if user.role == Role.STUDENT:
        return sync_result["student_created"]
    return False


def clear_profile_completion(user):
    if user.profile_completed_at is None:
        return False

    user.__class__._default_manager.filter(pk=user.pk).update(profile_completed_at=None)
    user.profile_completed_at = None
    return True


def mark_profile_completed_now(user):
    if user.profile_completed_at is not None:
        return False

    completed_at = timezone.now()
    user.__class__._default_manager.filter(pk=user.pk).update(profile_completed_at=completed_at)
    user.profile_completed_at = completed_at
    return True
