from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden

from .models import Role, SupportInvestigation


def _is_authenticated_active(user):
    return getattr(user, "is_authenticated", False) and getattr(user, "is_active", False)


def is_staff_role(user):
    return _is_authenticated_active(user) and user.role in {Role.MODERATOR, Role.SUPPORT, Role.ADMIN}


def can_access_staff_console(user):
    return is_staff_role(user)


def can_manage_listing_moderation(user):
    return _is_authenticated_active(user) and user.role in {Role.MODERATOR, Role.ADMIN}


def can_manage_reports(user):
    return _is_authenticated_active(user) and user.role in {Role.MODERATOR, Role.ADMIN}


def can_manage_user_roles(user):
    return _is_authenticated_active(user) and user.role == Role.ADMIN


def can_manage_user_status(user):
    return _is_authenticated_active(user) and user.role == Role.ADMIN


def can_open_support_investigations(user):
    return _is_authenticated_active(user) and user.role in {Role.SUPPORT, Role.ADMIN}


def can_view_sensitive_user_data(user):
    return can_open_support_investigations(user)


def can_browse_marketplace(user):
    return _is_authenticated_active(user) and user.role in {Role.STUDENT, Role.MODERATOR, Role.SUPPORT, Role.ADMIN}


def can_start_listing_conversations(user):
    return _is_authenticated_active(user) and user.role == Role.STUDENT


def can_use_roommate_matching(user):
    return _is_authenticated_active(user) and user.role == Role.STUDENT and user.profile_completed_at is not None


def has_listing_only_access(user):
    return _is_authenticated_active(user) and user.role == Role.REALTOR


def active_investigation_for_viewer(viewer, subject_user):
    if not can_view_sensitive_user_data(viewer) or getattr(subject_user, "pk", None) is None:
        return None
    return (
        SupportInvestigation.objects.active()
        .filter(subject=subject_user, opened_by=viewer)
        .order_by("-created_at", "-id")
        .first()
    )


def has_active_sensitive_access(viewer, subject_user):
    if not _is_authenticated_active(viewer) or getattr(subject_user, "pk", None) is None:
        return False
    if viewer.pk == subject_user.pk:
        return True
    return active_investigation_for_viewer(viewer, subject_user) is not None


def can_access_private_user_file(viewer, user_file):
    owner = getattr(user_file, "owner", None)
    if owner is None:
        return False
    return has_active_sensitive_access(viewer, owner)


def can_access_private_user_messages(viewer, subject_user):
    return has_active_sensitive_access(viewer, subject_user)


def require_permission(permission_check, *, message):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not permission_check(request.user):
                return HttpResponseForbidden(message)
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


staff_required_view = require_permission(
    can_access_staff_console,
    message="Staff access required.",
)
moderation_required_view = require_permission(
    can_manage_listing_moderation,
    message="Moderation access required.",
)
reports_required_view = require_permission(
    can_manage_reports,
    message="Report moderation access required.",
)
platform_admin_required_view = require_permission(
    can_manage_user_roles,
    message="Platform admin access required.",
)
support_required_view = require_permission(
    can_open_support_investigations,
    message="Support access required.",
)
