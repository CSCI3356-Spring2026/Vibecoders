from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from ..models import Listing, ListingInquiry
from ..sample_data import DEMO_USERS, demo_inquiry_definitions, demo_listing_definitions
from .base import User


class SeedDemoListingsCommandTests(TestCase):
    def test_command_creates_demo_marketplace_data(self):
        stdout = StringIO()

        call_command("seed_demo_listings", stdout=stdout)

        self.assertEqual(User.objects.count(), len(DEMO_USERS))
        self.assertEqual(Listing.objects.count(), len(demo_listing_definitions()))
        self.assertEqual(ListingInquiry.objects.count(), len(demo_inquiry_definitions()))
        self.assertTrue(User.objects.get(email="maya.sullivan@bc.edu").is_student)
        self.assertTrue(User.objects.get(email="olivia@chestnuthillrealty.com").is_realtor)
        self.assertIn("Seeded demo marketplace data", stdout.getvalue())

    def test_command_is_idempotent(self):
        call_command("seed_demo_listings", stdout=StringIO())
        call_command("seed_demo_listings", stdout=StringIO())

        self.assertEqual(User.objects.count(), len(DEMO_USERS))
        self.assertEqual(Listing.objects.count(), len(demo_listing_definitions()))
        self.assertEqual(ListingInquiry.objects.count(), len(demo_inquiry_definitions()))
