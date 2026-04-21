from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

RECENT_AUTH_SESSION_KEY = "recent_auth_at"


def mark_recent_auth(request, *, authenticated_at=None):
    timestamp = authenticated_at or timezone.now()
    request.session[RECENT_AUTH_SESSION_KEY] = timestamp.isoformat()
    request.session.modified = True
    return timestamp


def get_recent_auth_at(request):
    value = request.session.get(RECENT_AUTH_SESSION_KEY, "")
    authenticated_at = parse_datetime(value)
    if authenticated_at is None:
        return None
    if timezone.is_naive(authenticated_at):
        authenticated_at = timezone.make_aware(authenticated_at, timezone.get_current_timezone())
    return authenticated_at


def has_recent_auth(request, *, max_age_seconds=None):
    authenticated_at = get_recent_auth_at(request)
    if authenticated_at is None:
        return False

    if max_age_seconds is None:
        max_age_seconds = getattr(settings, "ACCOUNT_DELETION_RECENT_AUTH_SECONDS", 900)
    max_age = timedelta(seconds=max_age_seconds)
    return timezone.now() - authenticated_at <= max_age


def has_recent_privileged_auth(request):
    return has_recent_auth(
        request,
        max_age_seconds=getattr(settings, "PRIVILEGED_ACTION_RECENT_AUTH_SECONDS", 600),
    )
