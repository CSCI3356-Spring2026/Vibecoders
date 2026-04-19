from django.db import transaction

from .lifecycle import archive_listing
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
            archive_listing(
                report.listing,
                actor=reviewer,
                reason=report.listing.ARCHIVE_REASON_REPORT,
                notes=note,
            )

        action = report.activity_action_for_status(status)
        if previous_status == status:
            action = ListingReportUpdate.ACTION_NOTE if note else ""
        if action:
            report.add_update(actor=reviewer, note=note, action=action)

    return status == ListingReport.STATUS_RESOLVED
