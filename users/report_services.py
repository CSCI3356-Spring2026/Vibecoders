from django.db import transaction

from .account_lifecycle import deactivate_user, issue_user_warning, restrict_roommate_access
from .models import UserReportUpdate


def _apply_user_report_enforcement(report, *, enforcement_action, reviewer, note):
    if enforcement_action == "warn":
        issue_user_warning(report.reported_user, actor=reviewer, message=note or "Staff warning issued.")
        report.add_update(actor=reviewer, note=note, action=UserReportUpdate.ACTION_WARNED)
        return
    if enforcement_action == "restrict_roommate":
        restrict_roommate_access(report.reported_user, actor=reviewer, reason=note or "User report enforcement")
        report.add_update(actor=reviewer, note=note, action=UserReportUpdate.ACTION_ROOMMATE_RESTRICTED)
        return
    if enforcement_action == "deactivate":
        deactivate_user(report.reported_user, actor=reviewer, reason=note or "User report enforcement")
        report.add_update(actor=reviewer, note=note, action=UserReportUpdate.ACTION_USER_DEACTIVATED)


def update_user_report(report, *, status, reviewer, resolution_notes="", enforcement_action="none"):
    previous_status = report.status
    note = (resolution_notes or "").strip()

    with transaction.atomic():
        report.mark_status(
            status=status,
            reviewer=reviewer,
            resolution_notes=note,
        )
        report.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "resolution_notes",
                "updated_at",
            ]
        )

        action = report.activity_action_for_status(status)
        if previous_status == status:
            action = UserReportUpdate.ACTION_NOTE if note else ""
        if action:
            report.add_update(actor=reviewer, note=note, action=action)
        _apply_user_report_enforcement(
            report,
            enforcement_action=enforcement_action,
            reviewer=reviewer,
            note=note,
        )
