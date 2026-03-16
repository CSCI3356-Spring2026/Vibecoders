from datetime import date

from django.db import IntegrityError

from ..models import Listing
from .base import ListingTestCase


class ListingModelTests(ListingTestCase):
    def test_database_constraint_rejects_invalid_dates(self):
        with self.assertRaises(IntegrityError):
            Listing.objects.create(
                owner=self.user,
                title="Broken listing",
                address="140 Commonwealth Ave",
                price="1200.00",
                lease_type="FULL",
                start_date=date(2027, 5, 31),
                end_date=date(2026, 9, 1),
            )
