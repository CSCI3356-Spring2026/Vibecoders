"""
Management command: seed_listings

Creates fake realtor users and approved listings for development/demo.

Usage:
    python manage.py seed_listings
    python manage.py seed_listings --clear   # remove seeded data first
"""

import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from listings.models import Listing
from users.models import Role

SEED_TAG = "seed_listing_"

REALTORS = [
    {
        "username": "seed_listing_realtor_burke",
        "first_name": "Patrick",
        "last_name": "Burke",
        "email": "patrick.burke.seed@realtor.com",
    },
    {
        "username": "seed_listing_realtor_hayes",
        "first_name": "Claire",
        "last_name": "Hayes",
        "email": "claire.hayes.seed@realtor.com",
    },
    {
        "username": "seed_listing_realtor_santos",
        "first_name": "Maria",
        "last_name": "Santos",
        "email": "maria.santos.seed@realtor.com",
    },
]

LISTINGS = [
    {
        "realtor_index": 0,
        "title": "Sunny 2BR Near Cleveland Circle",
        "address": "45 Strathmore Rd, Brighton, MA 02135",
        "price": 1650,
        "description": "Bright 2-bedroom apartment steps from the C line. Hardwood floors, updated kitchen, coin laundry in building. Perfect for two BC students.",
        "start_date": datetime.date(2026, 9, 1),
        "end_date": datetime.date(2027, 8, 31),
        "lease_type": "FULL",
        "rooms": 2,
        "bathrooms": 1.0,
        "sq_ft": 850,
        "property_type": "apartment",
        "has_yard": False,
        "has_parking": False,
        "is_furnished": False,
        "distance_to_campus": 0.8,
        "utilities_estimate": 120,
        "security_deposit": 1650,
        "amenities": "Hardwood floors, Updated kitchen, Coin laundry",
        "utilities_included": "Heat, Hot water",
    },
    {
        "realtor_index": 0,
        "title": "Spacious 3BR House in Chestnut Hill",
        "address": "12 Beacon St, Chestnut Hill, MA 02467",
        "price": 1450,
        "description": "Three-bedroom house with a backyard and driveway parking. Quiet street, 5-min walk to campus. In-unit washer/dryer included.",
        "start_date": datetime.date(2026, 9, 1),
        "end_date": datetime.date(2027, 8, 31),
        "lease_type": "FULL",
        "rooms": 3,
        "bathrooms": 1.5,
        "sq_ft": 1200,
        "property_type": "house",
        "has_yard": True,
        "has_parking": True,
        "is_furnished": False,
        "distance_to_campus": 0.4,
        "utilities_estimate": 150,
        "security_deposit": 1450,
        "amenities": "In-unit washer/dryer, Backyard, Driveway parking",
        "utilities_included": "Heat",
    },
    {
        "realtor_index": 1,
        "title": "Modern Studio on Commonwealth Ave",
        "address": "600 Commonwealth Ave, Boston, MA 02215",
        "price": 1950,
        "description": "Fully furnished studio on the B line. Modern finishes, rooftop deck access, gym in building. Great for a single BC student interning downtown.",
        "start_date": datetime.date(2026, 6, 1),
        "end_date": datetime.date(2027, 5, 31),
        "lease_type": "FULL",
        "rooms": 1,
        "bathrooms": 1.0,
        "sq_ft": 450,
        "property_type": "studio",
        "has_yard": False,
        "has_parking": False,
        "is_furnished": True,
        "distance_to_campus": 1.2,
        "utilities_estimate": 80,
        "security_deposit": 1950,
        "amenities": "Rooftop deck, Gym, Doorman",
        "utilities_included": "WiFi, Heat, Hot water",
    },
    {
        "realtor_index": 1,
        "title": "4BR Apartment in Allston — Big Rooms",
        "address": "88 Brighton Ave, Allston, MA 02134",
        "price": 1250,
        "description": "Four large bedrooms in the heart of Allston. Two full baths, updated common areas, steps from multiple T lines and restaurants.",
        "start_date": datetime.date(2026, 9, 1),
        "end_date": datetime.date(2027, 8, 31),
        "lease_type": "FULL",
        "rooms": 4,
        "bathrooms": 2.0,
        "sq_ft": 1500,
        "property_type": "apartment",
        "has_yard": False,
        "has_parking": False,
        "is_furnished": False,
        "distance_to_campus": 1.5,
        "utilities_estimate": 100,
        "security_deposit": 1250,
        "amenities": "Updated kitchen, Large living room, Bike storage",
        "utilities_included": "Heat",
    },
    {
        "realtor_index": 2,
        "title": "Cozy 1BR in Brookline Village",
        "address": "21 Station St, Brookline, MA 02445",
        "price": 1800,
        "description": "Charming one-bedroom in quiet Brookline Village. Exposed brick, private parking spot, steps from D line and shops.",
        "start_date": datetime.date(2026, 8, 15),
        "end_date": datetime.date(2027, 8, 14),
        "lease_type": "FULL",
        "rooms": 1,
        "bathrooms": 1.0,
        "sq_ft": 620,
        "property_type": "apartment",
        "has_yard": False,
        "has_parking": True,
        "is_furnished": False,
        "distance_to_campus": 1.0,
        "utilities_estimate": 90,
        "security_deposit": 1800,
        "amenities": "Exposed brick, Private parking, Storage unit",
        "utilities_included": "Heat, Hot water",
    },
    {
        "realtor_index": 2,
        "title": "3BR Newton Centre — Quiet & Spacious",
        "address": "5 Langley Rd, Newton Centre, MA 02459",
        "price": 1550,
        "description": "Three-bedroom apartment in residential Newton Centre. Large bedrooms, two parking spots, coin laundry in building. D line nearby.",
        "start_date": datetime.date(2026, 9, 1),
        "end_date": datetime.date(2027, 8, 31),
        "lease_type": "FULL",
        "rooms": 3,
        "bathrooms": 1.0,
        "sq_ft": 1100,
        "property_type": "apartment",
        "has_yard": False,
        "has_parking": True,
        "is_furnished": False,
        "distance_to_campus": 2.1,
        "utilities_estimate": 130,
        "security_deposit": 1550,
        "amenities": "Large closets, Coin laundry, Two parking spots",
        "utilities_included": "Heat, Hot water",
    },
    {
        "realtor_index": 0,
        "title": "Summer Sublet — Furnished 2BR Brighton",
        "address": "33 Lake St, Brighton, MA 02135",
        "price": 1100,
        "description": "Short-term furnished sublet available May–August. Two bedrooms, full kitchen, utilities included. Ideal for summer internships.",
        "start_date": datetime.date(2026, 5, 15),
        "end_date": datetime.date(2026, 8, 31),
        "lease_type": "SUBLEASE",
        "rooms": 2,
        "bathrooms": 1.0,
        "sq_ft": 780,
        "property_type": "apartment",
        "has_yard": False,
        "has_parking": False,
        "is_furnished": True,
        "distance_to_campus": 0.9,
        "utilities_estimate": 0,
        "security_deposit": 500,
        "amenities": "Furnished, Fast WiFi, Smart TV",
        "utilities_included": "WiFi, Heat, Hot water, Electricity",
    },
    {
        "realtor_index": 1,
        "title": "5BR Student House — Cleveland Circle",
        "address": "76 Sutherland Rd, Brighton, MA 02135",
        "price": 1100,
        "description": "Classic BC student house steps from Cleveland Circle. Five bedrooms, huge living room, backyard with grill. This one fills up fast every year.",
        "start_date": datetime.date(2026, 9, 1),
        "end_date": datetime.date(2027, 8, 31),
        "lease_type": "FULL",
        "rooms": 5,
        "bathrooms": 2.0,
        "sq_ft": 1800,
        "property_type": "house",
        "has_yard": True,
        "has_parking": True,
        "is_furnished": False,
        "distance_to_campus": 0.6,
        "utilities_estimate": 160,
        "security_deposit": 1100,
        "amenities": "Backyard with grill, Parking, Large living room, Coin laundry",
        "utilities_included": "Heat",
    },
]


def _make_realtor(User, username, first_name, last_name, email):
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "role": Role.REALTOR,
            "is_active": True,
        },
    )
    if created:
        user.set_unusable_password()
        user.save()
    return user, created


class Command(BaseCommand):
    help = "Seed fake listings for development/demo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete previously seeded listings and realtor users before re-seeding.",
        )

    def handle(self, *args, **options):
        User = get_user_model()

        if options["clear"]:
            deleted, _ = User.objects.filter(username__startswith=SEED_TAG).delete()
            self.stdout.write(self.style.WARNING(f"Cleared {deleted} seeded realtor(s) and related listings."))

        # Create realtors
        realtors = []
        for r in REALTORS:
            user, created = _make_realtor(User, r["username"], r["first_name"], r["last_name"], r["email"])
            realtors.append(user)
            status = "created" if created else "exists"
            self.stdout.write(f"  realtor {status}: {user.get_full_name()}")

        # Create listings
        self.stdout.write("\n--- Listings ---")
        count = 0
        for data in LISTINGS:
            owner = realtors[data["realtor_index"]]
            listing, created = Listing.objects.get_or_create(
                owner=owner,
                title=data["title"],
                defaults={
                    "address": data["address"],
                    "price": data["price"],
                    "description": data["description"],
                    "start_date": data["start_date"],
                    "end_date": data["end_date"],
                    "lease_type": data["lease_type"],
                    "rooms": data["rooms"],
                    "bathrooms": data["bathrooms"],
                    "sq_ft": data["sq_ft"],
                    "property_type": data["property_type"],
                    "has_yard": data["has_yard"],
                    "has_parking": data["has_parking"],
                    "is_furnished": data["is_furnished"],
                    "distance_to_campus": data["distance_to_campus"],
                    "utilities_estimate": data["utilities_estimate"],
                    "security_deposit": data["security_deposit"],
                    "amenities": data["amenities"],
                    "utilities_included": data["utilities_included"],
                    "approval_status": Listing.APPROVAL_APPROVED,
                    "approved_at": timezone.now(),
                    "submitted_for_approval_at": timezone.now(),
                    "status": "AVAILABLE",
                },
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"  created: {listing.title} (${data['price']}/mo)"))
                count += 1
            else:
                self.stdout.write(f"  skipped (exists): {listing.title}")

        self.stdout.write(self.style.SUCCESS(f"\nDone. {count} listing(s) seeded."))
