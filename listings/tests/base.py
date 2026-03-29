from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from listings.models import Listing

User = get_user_model()


class ListingTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testowner", email="testowner@bc.edu", password="testpass123")

    def create_listing(self, **overrides):
        today = date.today()
        payload = {
            "title": "Test listing",
            "address": "140 Commonwealth Ave",
            "price": "1200.00",
            "lease_type": "FULL",
            "start_date": today + timedelta(days=30),
            "end_date": today + timedelta(days=300),
            "property_type": "apartment",
            "description": "Sunny place near campus.",
            "approval_status": Listing.APPROVAL_APPROVED,
            "submitted_for_approval_at": timezone.now(),
            "reviewed_at": timezone.now(),
            "approved_at": timezone.now(),
        }
        payload.update(overrides)
        return self.user.listings.create(**payload)
