from django.db import transaction

from .models import Listing


def archive_listing(listing, *, actor, reason, notes=""):
    with transaction.atomic():
        locked_listing = Listing.objects.select_for_update().get(pk=listing.pk)
        if locked_listing.is_archived:
            return locked_listing, False

        locked_listing.archive(by_user=actor, reason=reason, notes=notes)
        update_fields = [
            "archived_at",
            "archived_by",
            "archive_reason",
            "is_hidden",
            "approval_notes",
        ]
        if reason == Listing.ARCHIVE_REASON_REPORT:
            update_fields.extend(
                [
                    "approval_status",
                    "reviewed_by",
                    "reviewed_at",
                    "approved_at",
                    "submitted_for_approval_at",
                ]
            )
        locked_listing.save(update_fields=update_fields)
        return locked_listing, True
