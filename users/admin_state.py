from django.contrib.auth import get_user_model

from .models import Role


def _other_active_admins_exist(user):
    user_model = get_user_model()
    return user_model._default_manager.exclude(pk=user.pk).filter(role=Role.ADMIN, is_active=True).exists()


def may_lose_admin_access(user):
    if user.role != Role.ADMIN or not user.is_active:
        return True
    return _other_active_admins_exist(user)


def may_deactivate(user):
    if user.role != Role.ADMIN or not user.is_active:
        return True
    return _other_active_admins_exist(user)


def may_delete(user):
    if user.role != Role.ADMIN or not user.is_active:
        return True
    return _other_active_admins_exist(user)
