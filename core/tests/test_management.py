import hashlib
import io
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from communications.models import ListingConversation
from core.demo_seed_data import DEMO_LISTINGS, DEMO_PHOTOS, DEMO_USERNAME_PREFIX
from listings.models import Listing
from roommates.models import RoommateGroupInvite, RoommatePost
from users.models import UserFile

User = get_user_model()


def _fake_photo_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (1600, 1200), color=(220, 224, 231)).save(buffer, format="JPEG", quality=92)
    return buffer.getvalue()


def _patched_photo_specs():
    fake_hash = hashlib.sha256(_fake_photo_bytes()).hexdigest()
    return [{**spec, "sha256": fake_hash} for spec in DEMO_PHOTOS]


@override_settings(DEBUG=True)
class SeedDemoDataCommandTests(TestCase):
    def setUp(self):
        self.bundle_dir = tempfile.TemporaryDirectory()
        self.media_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.bundle_dir.cleanup)
        self.addCleanup(self.media_dir.cleanup)
        self.reference_date = timezone.localdate() + timedelta(days=30)

    def _call_command(self, *extra_args):
        output = io.StringIO()
        args = [
            "seed_demo_data",
            "--bundle-root",
            self.bundle_dir.name,
            "--reference-date",
            self.reference_date.isoformat(),
            *extra_args,
        ]
        call_command(*args, stdout=output)
        return output.getvalue()

    def test_seed_demo_data_creates_cross_app_demo_environment(self):
        with self.settings(MEDIA_ROOT=self.media_dir.name):
            with patch("core.demo_seed.DEMO_PHOTOS", _patched_photo_specs()):
                with patch("core.demo_seed.download_photo_source", return_value=_fake_photo_bytes()):
                    self._call_command()

        demo_users = User._default_manager.filter(username__startswith=DEMO_USERNAME_PREFIX)
        self.assertGreaterEqual(demo_users.count(), 1)
        self.assertEqual(
            Listing.objects.filter(owner__username__startswith=DEMO_USERNAME_PREFIX).count(),
            len(DEMO_LISTINGS),
        )
        self.assertEqual(RoommatePost.objects.count(), 6)
        self.assertEqual(RoommateGroupInvite.objects.count(), 3)
        self.assertEqual(UserFile.objects.count(), 4)
        self.assertGreaterEqual(ListingConversation.objects.count(), 8)

        claire = User._default_manager.get(username="demo_claire_brennan")
        self.assertEqual(claire.student_profile.institution_status, "undergraduate")
        jordan = User._default_manager.get(username="demo_jordan_realtor")
        self.assertEqual(jordan.admin_profile.organization_type, "individual_owner")

        student_sublet = Listing.objects.get(title__icontains="Chestnut Hill 2BR")
        self.assertEqual(student_sublet.space_type, Listing.SPACE_PRIVATE_ROOM)
        self.assertTrue(student_sublet.landlord_approval_required)
        self.assertEqual(student_sublet.documentation_type, "sublease")
        self.assertEqual(student_sublet.original_lease_holder, "Claire Brennan")
        self.assertIn("No smoking", student_sublet.renter_requirements)

        archived_listing = Listing.objects.get(title__icontains="archived after lease signing")
        self.assertIsNotNone(archived_listing.archived_at)

        summary_path = Path(self.bundle_dir.name) / "seed_summary.json"
        self.assertTrue(summary_path.exists())
        source_files = list((Path(self.bundle_dir.name) / "photos" / "source").glob("*.jpg"))
        processed_files = list((Path(self.bundle_dir.name) / "photos" / "processed").glob("*.jpg"))
        self.assertEqual(len(source_files), len(DEMO_PHOTOS))
        self.assertEqual(len(processed_files), len(DEMO_PHOTOS))

    def test_seed_demo_data_reuses_cached_photo_bundle_on_repeat_run(self):
        with self.settings(MEDIA_ROOT=self.media_dir.name):
            with patch("core.demo_seed.DEMO_PHOTOS", _patched_photo_specs()):
                with patch("core.demo_seed.download_photo_source", return_value=_fake_photo_bytes()):
                    self._call_command()

                with patch("core.demo_seed.download_photo_source", side_effect=AssertionError("download not expected")):
                    self._call_command("--skip-image-downloads")

        self.assertEqual(
            Listing.objects.filter(owner__username__startswith=DEMO_USERNAME_PREFIX).count(),
            len(DEMO_LISTINGS),
        )

    @override_settings(DEBUG=False)
    def test_seed_demo_data_requires_debug_mode(self):
        with self.settings(MEDIA_ROOT=self.media_dir.name):
            with self.assertRaises(CommandError):
                with patch("core.demo_seed.DEMO_PHOTOS", _patched_photo_specs()):
                    with patch("core.demo_seed.download_photo_source", return_value=_fake_photo_bytes()):
                        self._call_command()
