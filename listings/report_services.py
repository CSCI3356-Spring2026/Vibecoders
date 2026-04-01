from django.db import transaction

from .models import ListingReport, ListingReportUpdate


def update_listing_report(report, *, status, reviewer, resolution_notes=""):
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
        if status == ListingReport.STATUS_RESOLVED:
            report.listing.close_from_report(reviewer=reviewer, notes=note)
            report.listing.save(
                update_fields=[
                    "approval_status",
                    "reviewed_by",
                    "reviewed_at",
                    "approved_at",
                    "approval_notes",
                ]
            )

        action = report.activity_action_for_status(status)
        if previous_status == status:
            action = ListingReportUpdate.ACTION_NOTE if note else ""
        if action:
            report.add_update(actor=reviewer, note=note, action=action)

    return status == ListingReport.STATUS_RESOLVED
