from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

LEGAL_ACCEPTANCE_SESSION_KEY = "legal_acceptance"


def build_legal_acceptance_payload(accepted_at=None):
    accepted_at = accepted_at or timezone.now()
    return {
        "version": settings.LEGAL_DOCUMENT_VERSION,
        "accepted_at": accepted_at.isoformat(),
    }


def set_pending_legal_acceptance(request, accepted_at=None):
    payload = build_legal_acceptance_payload(accepted_at=accepted_at)
    request.session[LEGAL_ACCEPTANCE_SESSION_KEY] = payload
    request.session.modified = True
    return payload


def get_pending_legal_acceptance(request):
    payload = request.session.get(LEGAL_ACCEPTANCE_SESSION_KEY)
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != settings.LEGAL_DOCUMENT_VERSION:
        return None

    accepted_at = parse_datetime(payload.get("accepted_at", ""))
    if accepted_at is None:
        return None
    if timezone.is_naive(accepted_at):
        accepted_at = timezone.make_aware(accepted_at, timezone.get_current_timezone())

    return {
        "version": payload["version"],
        "accepted_at": accepted_at,
    }


def has_current_legal_acceptance(request):
    return get_pending_legal_acceptance(request) is not None


def persist_legal_acceptance_for_user(user, payload):
    accepted_at = payload["accepted_at"]
    version = payload["version"]
    fields = []

    if user.terms_accepted_at != accepted_at:
        user.terms_accepted_at = accepted_at
        fields.append("terms_accepted_at")
    if user.privacy_accepted_at != accepted_at:
        user.privacy_accepted_at = accepted_at
        fields.append("privacy_accepted_at")
    if user.legal_policy_version != version:
        user.legal_policy_version = version
        fields.append("legal_policy_version")

    if fields:
        user.save(update_fields=fields)
