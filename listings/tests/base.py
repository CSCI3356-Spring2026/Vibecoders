from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from listings.models import Listing, RoommatePost

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

    def complete_roommate_profile(self, user=None, **overrides):
        user = user or self.user
        profile = user.student_profile
        defaults = {
            "preferred_name": user.first_name or user.username,
            "major": "Computer Science",
            "bio": "Quiet during the week and easy to live with.",
            "messy_level": 4,
            "guest_level": 2,
            "bedtime": 23,
            "noise_level": 2,
            "drink": 2,
            "party": 2,
            "smoke": False,
            "pets": False,
        }
        defaults.update(overrides)
        for field_name, value in defaults.items():
            setattr(profile, field_name, value)
        profile.save()
        user.profile_completed_at = timezone.now()
        user.save(update_fields=["profile_completed_at"])
        return profile

    def create_roommate_post(self, author=None, **overrides):
        author = author or self.user
        if author.profile_completed_at is None:
            self.complete_roommate_profile(author)

        payload = {
            "title": "Two BC seniors looking for one more roommate",
            "description": "We already have a solid two-person group and want one more roommate for an August move.",
            "housing_status": RoommatePost.HOUSING_NEED_HOME,
            "current_group_size": 2,
            "open_spots": 1,
            "budget_min": "1200",
            "budget_max": "1600",
            "move_in_date": date.today() + timedelta(days=45),
            "neighborhoods": "Allston, Brighton",
            "is_active": True,
        }
        payload.update(overrides)
        return RoommatePost.objects.create(author=author, **payload)
