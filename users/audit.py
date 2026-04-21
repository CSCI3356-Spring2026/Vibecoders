from .models import AuditEvent


def _metadata_payload(metadata):
    if not metadata:
        return {}
    return {key: value for key, value in metadata.items() if value is not None}


def record_audit_event(*, action, actor=None, target=None, target_type="", target_id="", reason="", metadata=None):
    resolved_target_type = target_type
    resolved_target_id = target_id
    resolved_target_repr = ""

    if target is not None:
        target_meta = getattr(target, "_meta", None)
        if target_meta is not None:
            resolved_target_type = target_meta.label_lower
        resolved_target_id = str(getattr(target, "pk", "") or "")
        resolved_target_repr = str(target)

    return AuditEvent.objects.create(
        action=action,
        actor=actor,
        target_type=resolved_target_type,
        target_id=resolved_target_id,
        target_repr=resolved_target_repr,
        reason=reason,
        metadata=_metadata_payload(metadata),
    )
