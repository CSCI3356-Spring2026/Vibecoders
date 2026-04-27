from datetime import date, timedelta
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from allauth.socialaccount.models import SocialAccount
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.signing import BadSignature, SignatureExpired
from django.db import IntegrityError, transaction
from django.test.utils import override_settings
from django.utils import timezone
from PIL import Image

from communications.models import ListingConversation
from communications.selectors import accessible_conversations_for_user
from communications.services import (
    delete_conversation_for_user,
    send_conversation_message,
    send_listing_message,
    serialize_conversation_for_user,
    start_direct_conversation,
    start_listing_conversation,
)

from ..address_provider import get_geoapify_autocomplete_config, normalize_geoapify_suggestions
from ..address_signing import sign_address_selection, unsign_address_selection
from ..forms import ListingForm
from ..geocoding import geocode_listing_address
from ..models import Listing, ListingFavorite, ListingImage, ListingReport, ListingReview, RoommateGroup, RoommatePost
from ..report_services import update_listing_report
from .base import ListingTestCase


class ListingModelTests(ListingTestCase):
    def _complete_roommate_profile(self, user):
        self.complete_roommate_profile(user)

    def _image_upload(self, name="photo.png"):
        buffer = BytesIO()
        Image.new("RGB", (8, 8), color=(79, 70, 229)).save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

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

    def test_database_constraint_rejects_negative_distance_to_campus(self):
        with self.assertRaises(IntegrityError):
            Listing.objects.create(
                owner=self.user,
                title="Broken listing",
                address="140 Commonwealth Ave",
                price="1200.00",
                lease_type="FULL",
                start_date=date(2026, 9, 1),
                end_date=date(2027, 5, 31),
                distance_to_campus="-1.00",
            )

    def test_database_constraint_rejects_invalid_listing_status(self):
        with self.assertRaises(IntegrityError):
            Listing.objects.create(
                owner=self.user,
                title="Broken listing",
                address="140 Commonwealth Ave",
                price="1200.00",
                lease_type="FULL",
                start_date=date(2026, 9, 1),
                end_date=date(2027, 5, 31),
                status="BROKEN",
            )

    def test_public_queryset_only_returns_active_marketplace_listings(self):
        today = date.today()
        active_listing = self.create_listing(title="Active listing")
        self.create_listing(title="Taken listing", status=Listing.STATUS_TAKEN)
        self.create_listing(
            title="Expired listing",
            start_date=today - timedelta(days=90),
            end_date=today - timedelta(days=30),
        )
        self.create_listing(title="Hidden listing", is_hidden=True)

        listings = list(Listing.objects.public())

        self.assertEqual([listing.pk for listing in listings], [active_listing.pk])

    def test_public_queryset_excludes_inactive_owner_listings(self):
        active_listing = self.create_listing(title="Active listing")
        inactive_owner = self.user.__class__.objects.create_user(
            username="inactive-owner",
            email="inactive-owner@bc.edu",
            password="test",
        )
        inactive_listing = inactive_owner.listings.create(
            title="Inactive owner listing",
            address="150 Commonwealth Ave",
            price="1400.00",
            lease_type="FULL",
            start_date=date.today() + timedelta(days=30),
            end_date=date.today() + timedelta(days=300),
            property_type="apartment",
            description="Should disappear from public listing queries.",
            approval_status=Listing.APPROVAL_APPROVED,
            submitted_for_approval_at=timezone.now(),
            reviewed_at=timezone.now(),
            approved_at=timezone.now(),
        )
        inactive_owner.is_active = False
        inactive_owner.save(update_fields=["is_active"])

        listings = list(Listing.objects.public())

        self.assertEqual([listing.pk for listing in listings], [active_listing.pk])
        self.assertNotIn(inactive_listing.pk, [listing.pk for listing in listings])

    def test_public_queryset_excludes_unapproved_listings(self):
        approved_listing = self.create_listing(title="Approved listing")
        self.create_listing(title="Pending review", approval_status=Listing.APPROVAL_PENDING)
        self.create_listing(title="Rejected listing", approval_status=Listing.APPROVAL_REJECTED)

        listings = list(Listing.objects.public())

        self.assertEqual([listing.pk for listing in listings], [approved_listing.pk])

    def test_roommate_post_requires_completed_student_profile(self):
        student = self.user.__class__.objects.create_user(
            username="student-two",
            email="student-two@bc.edu",
            password="test",
        )

        with self.assertRaises(ValidationError) as exc:
            RoommatePost.objects.create(
                author=student,
                title="Need one roommate in Brighton",
                description="We need one roommate for a late-summer move and a quieter apartment.",
                housing_status=RoommatePost.HOUSING_NEED_HOME,
                current_group_size=2,
                open_spots=1,
                budget_min="1200",
                budget_max="1500",
                move_in_date=date.today() + timedelta(days=30),
            )

        self.assertIn(
            "Only students with completed roommate profiles can post.", exc.exception.message_dict["title"][0]
        )

    def test_roommate_post_active_queryset_only_returns_live_completed_student_posts(self):
        live_post = self.create_roommate_post()
        paused_author = self.user.__class__.objects.create_user(
            username="paused-student",
            email="paused-student@bc.edu",
            password="test",
        )
        self.complete_roommate_profile(paused_author)
        self.create_roommate_post(author=paused_author, title="Paused post", is_active=False)

        posts = list(RoommatePost.objects.active())

        self.assertEqual([post.pk for post in posts], [live_post.pk])

    def test_roommate_group_requires_completed_student_lead(self):
        student = self.user.__class__.objects.create_user(
            username="group-lead",
            email="group-lead@bc.edu",
            password="test",
        )

        with self.assertRaises(ValidationError) as exc:
            RoommateGroup.objects.create(
                lead=student,
                name="Late Summer Search",
            )

        self.assertIn(
            "Only students with completed roommate profiles can lead a group.",
            exc.exception.message_dict["name"][0],
        )

    def test_group_roommate_post_uses_group_member_count(self):
        second_member = self.user.__class__.objects.create_user(
            username="groupmate",
            email="groupmate@bc.edu",
            password="test",
        )
        group = self.create_roommate_group(lead=self.user, members=[second_member])

        post = self.create_group_roommate_post(group=group, current_group_size=99)

        self.assertEqual(post.current_group_size, 2)

    def test_roommate_post_active_queryset_includes_live_group_posts(self):
        second_member = self.user.__class__.objects.create_user(
            username="groupmate-two",
            email="groupmate-two@bc.edu",
            password="test",
        )
        group = self.create_roommate_group(lead=self.user, members=[second_member])
        post = self.create_group_roommate_post(group=group)

        posts = list(RoommatePost.objects.active())

        self.assertEqual([item.pk for item in posts], [post.pk])

    def test_roommate_post_active_queryset_excludes_past_move_in_dates(self):
        stale_author = self.user.__class__.objects.create_user(
            username="stale-student",
            email="stale-student@bc.edu",
            password="test",
        )
        self.complete_roommate_profile(stale_author)
        stale_post = self.create_roommate_post(
            author=stale_author,
            title="Stale post",
        )
        RoommatePost.objects.filter(pk=stale_post.pk).update(move_in_date=date.today() - timedelta(days=1))

        posts = list(RoommatePost.objects.active())

        self.assertEqual(posts, [])

    def test_roommate_post_reports_target_household_size(self):
        roommate_post = self.create_roommate_post(current_group_size=3, open_spots=2)

        self.assertEqual(roommate_post.target_household_size, 5)

    def test_roommate_post_target_household_size_allows_missing_open_spots(self):
        roommate_post = self.create_roommate_post(open_spots=None)

        self.assertIsNone(roommate_post.target_household_size)

    def test_roommate_post_requires_open_spots_when_have_home(self):
        self.complete_roommate_profile(self.user)
        with self.assertRaises(ValidationError) as exc:
            RoommatePost.objects.create(
                author=self.user,
                title="We already have a place",
                description="We have housing and want to add roommates.",
                housing_status=RoommatePost.HOUSING_HAVE_HOME,
                current_group_size=2,
                open_spots=None,
                budget_min="1200",
                budget_max="1500",
                move_in_date=date.today() + timedelta(days=30),
            )

        self.assertIn("Add how many open roommate spots you have.", exc.exception.message_dict["open_spots"][0])

    def test_listing_owner_cannot_be_reassigned_after_creation(self):
        listing = self.create_listing()
        new_owner = self.user.__class__.objects.create_user(
            username="new-owner",
            email="new-owner@bc.edu",
            password="test",
        )
        listing.owner = new_owner

        with self.assertRaises(ValidationError) as exc:
            listing.save()

        self.assertIn("Listing ownership cannot be reassigned after creation.", exc.exception.message_dict["owner"][0])

    def test_conversation_add_message_updates_unread_state(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        listing = self.create_listing()
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=listing.owner,
            participant=participant,
        )

        conversation.add_message(sender=participant, body="Interested.")
        conversation.refresh_from_db()

        self.assertTrue(conversation.owner_has_unread_messages)
        self.assertFalse(conversation.participant_has_unread_messages)
        self.assertEqual(conversation.last_message_preview, "Interested.")

    def test_conversation_rejects_non_participant_sender(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        outsider = self.user.__class__.objects.create_user(
            username="outsider",
            email="outsider@bc.edu",
            password="test",
        )
        listing = self.create_listing()
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=listing.owner,
            participant=participant,
        )

        with self.assertRaises(ValidationError):
            conversation.add_message(sender=outsider, body="Hello")

    def test_serialized_conversation_payload_only_exposes_required_fields(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        self.user.profile_image_url = "https://example.com/owner-avatar.jpg"
        self.user.save(update_fields=["profile_image_url"])
        listing = self.create_listing()
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=listing.owner,
            participant=participant,
        )

        payload = serialize_conversation_for_user(conversation, participant)

        self.assertNotIn("counterparty_email", payload)
        self.assertEqual(payload["counterparty_name"], listing.owner.username)
        self.assertEqual(payload["counterparty_avatar_url"], "https://example.com/owner-avatar.jpg")

    def test_listing_image_versioned_url_is_exposed_in_conversation_payload(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )

        with TemporaryDirectory() as temp_dir, override_settings(MEDIA_ROOT=temp_dir):
            listing = self.create_listing()
            ListingImage.objects.create(listing=listing, image=self._image_upload())
            conversation = ListingConversation.objects.create(
                listing=listing,
                owner=listing.owner,
                participant=participant,
            )

            payload = serialize_conversation_for_user(conversation, participant)

        self.assertIn("?v=", payload["listing_image_url"])

    def test_listing_image_file_is_not_deleted_when_transaction_rolls_back(self):
        with TemporaryDirectory() as temp_dir, override_settings(MEDIA_ROOT=temp_dir):
            listing = self.create_listing()
            listing_image = ListingImage.objects.create(listing=listing, image=self._image_upload("one.png"))
            stored_name = listing_image.image.name

            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    listing_image.delete()
                    self.assertTrue(listing_image.image.storage.exists(stored_name))
                    raise RuntimeError("rollback")

            self.assertTrue(listing_image.image.storage.exists(stored_name))

    def test_listing_estimated_totals_include_optional_cost_fields(self):
        listing = self.create_listing(
            price="1800.00",
            utilities_estimate="125.00",
            parking_fee="150.00",
            security_deposit="1800.00",
            application_fee="45.00",
        )

        self.assertEqual(listing.estimated_monthly_total, 2075)
        self.assertEqual(listing.estimated_upfront_total, 3645)

    def test_listing_form_prepopulates_known_and_other_utilities(self):
        listing = self.create_listing(utilities_included="Water, WiFi, Heat")

        form = ListingForm(instance=listing)

        self.assertEqual(form.fields["common_utilities"].initial, ["Water", "WiFi"])
        self.assertEqual(form.fields["other_utilities"].initial, "Heat")

    def test_listing_owner_cannot_favorite_their_own_listing(self):
        listing = self.create_listing()

        with self.assertRaises(ValidationError) as exc:
            ListingFavorite.objects.create(user=self.user, listing=listing)

        self.assertIn("You cannot save your own listing.", exc.exception.message_dict["listing"][0])

    def test_listing_review_requires_approved_listing(self):
        reviewer = self.user.__class__.objects.create_user(
            username="reviewer",
            email="reviewer@bc.edu",
            password="test",
        )
        listing = self.create_listing(approval_status=Listing.APPROVAL_PENDING)

        with self.assertRaises(ValidationError) as exc:
            ListingReview.objects.create(listing=listing, author=reviewer, rating=4, comment="Looks good.")

        self.assertIn("Only approved listings can receive public reviews.", exc.exception.message_dict["comment"][0])

    def test_listing_review_requires_prior_listing_conversation(self):
        reviewer = self.user.__class__.objects.create_user(
            username="prior-contact",
            email="prior-contact@bc.edu",
            password="test",
        )
        listing = self.create_listing()

        with self.assertRaises(ValidationError) as exc:
            ListingReview.objects.create(listing=listing, author=reviewer, rating=4, comment="Solid place.")

        self.assertIn("Contact the lister before leaving a resident review.", exc.exception.message_dict["comment"][0])

    def test_listing_review_accepts_student_with_prior_listing_conversation(self):
        reviewer = self.user.__class__.objects.create_user(
            username="connected-reviewer",
            email="connected-reviewer@bc.edu",
            password="test",
        )
        listing = self.create_listing()
        ListingConversation.objects.create(listing=listing, owner=listing.owner, participant=reviewer)

        review = ListingReview.objects.create(listing=listing, author=reviewer, rating=5, comment="Stayed here.")

        self.assertEqual(review.rating, 5)

    def test_listing_report_blocks_duplicate_active_reports(self):
        reporter = self.user.__class__.objects.create_user(
            username="reporter",
            email="reporter@bc.edu",
            password="test",
        )
        listing = self.create_listing()
        ListingReport.objects.create(
            listing=listing,
            reporter=reporter,
            reason=ListingReport.REASON_SPAM,
            details="Duplicate listing.",
        )

        with self.assertRaises(ValidationError):
            ListingReport.objects.create(
                listing=listing,
                reporter=reporter,
                reason=ListingReport.REASON_INACCURATE,
                details="Still active.",
            )

    def test_listing_report_requires_student_reporter(self):
        reporter = self.user.__class__.objects.create_user(
            username="agent-reporter",
            email="agent-reporter@gmail.com",
            password="test",
        )
        listing = self.create_listing()

        with self.assertRaises(ValidationError) as exc:
            ListingReport.objects.create(
                listing=listing,
                reporter=reporter,
                reason=ListingReport.REASON_SPAM,
                details="Not a student report.",
            )

        self.assertIn("Only student accounts can report listings.", exc.exception.message_dict["details"][0])

    def test_reopening_report_clears_resolution_metadata(self):
        reviewer = self.user.__class__.objects.create_user(
            username="report-reviewer",
            email="report-reviewer@bc.edu",
            password="test",
            role="admin",
        )
        reporter = self.user.__class__.objects.create_user(
            username="report-owner-student",
            email="report-owner-student@bc.edu",
            password="test",
        )
        listing = self.create_listing()
        report = ListingReport.objects.create(
            listing=listing,
            reporter=reporter,
            reason=ListingReport.REASON_SPAM,
            details="Duplicate listing.",
        )

        report.mark_status(
            status=ListingReport.STATUS_RESOLVED,
            reviewer=reviewer,
            resolution_notes="Closed out.",
        )
        report.save()
        report.mark_status(
            status=ListingReport.STATUS_OPEN,
            reviewer=reviewer,
            resolution_notes="",
        )
        report.save()

        self.assertEqual(report.status, ListingReport.STATUS_OPEN)
        self.assertIsNone(report.reviewed_by)
        self.assertIsNone(report.reviewed_at)
        self.assertEqual(report.resolution_notes, "")

    def test_report_resolution_archives_listing_and_preserves_moderation_notes(self):
        reviewer = self.user.__class__.objects.create_user(
            username="report-resolution-reviewer",
            email="report-resolution-reviewer@bc.edu",
            password="test",
            role="admin",
        )
        reporter = self.user.__class__.objects.create_user(
            username="report-resolution-student",
            email="report-resolution-student@bc.edu",
            password="test",
        )
        listing = self.create_listing(is_hidden=False)
        report = ListingReport.objects.create(
            listing=listing,
            reporter=reporter,
            reason=ListingReport.REASON_SPAM,
            details="Duplicate listing.",
        )

        report.mark_status(
            status=ListingReport.STATUS_RESOLVED,
            reviewer=reviewer,
            resolution_notes="Removed from the marketplace while we investigate.",
        )
        report.save()
        listing.archive_from_report(reviewer=reviewer, notes="Removed from the marketplace while we investigate.")
        listing.save()
        listing.refresh_from_db()

        self.assertTrue(listing.is_hidden)
        self.assertTrue(listing.is_archived)
        self.assertFalse(listing.is_publicly_active)
        self.assertEqual(listing.archive_reason, Listing.ARCHIVE_REASON_REPORT)
        self.assertEqual(listing.approval_status, Listing.APPROVAL_REJECTED)
        self.assertEqual(listing.approval_notes, "Removed from the marketplace while we investigate.")
        self.assertEqual(listing.archived_by, reviewer)

    def test_update_listing_report_records_note_when_status_is_unchanged(self):
        reviewer = self.user.__class__.objects.create_user(
            username="report-note-reviewer",
            email="report-note-reviewer@bc.edu",
            password="test",
            role="admin",
        )
        reporter = self.user.__class__.objects.create_user(
            username="report-note-student",
            email="report-note-student@bc.edu",
            password="test",
        )
        report = ListingReport.objects.create(
            listing=self.create_listing(),
            reporter=reporter,
            reason=ListingReport.REASON_SAFETY,
            details="Need a closer look.",
        )

        listing_closed = update_listing_report(
            report,
            status=ListingReport.STATUS_OPEN,
            reviewer=reviewer,
            resolution_notes="Initial moderation note.",
        )

        report.refresh_from_db()
        update = report.updates.get()
        self.assertFalse(listing_closed)
        self.assertEqual(report.status, ListingReport.STATUS_OPEN)
        self.assertEqual(update.action, update.ACTION_NOTE)
        self.assertEqual(update.note, "Initial moderation note.")

    def test_update_listing_report_closes_listing_when_resolved(self):
        reviewer = self.user.__class__.objects.create_user(
            username="report-close-reviewer",
            email="report-close-reviewer@bc.edu",
            password="test",
            role="admin",
        )
        reporter = self.user.__class__.objects.create_user(
            username="report-close-student",
            email="report-close-student@bc.edu",
            password="test",
        )
        listing = self.create_listing()
        report = ListingReport.objects.create(
            listing=listing,
            reporter=reporter,
            reason=ListingReport.REASON_SPAM,
            details="This listing looks fraudulent.",
        )

        listing_closed = update_listing_report(
            report,
            status=ListingReport.STATUS_RESOLVED,
            reviewer=reviewer,
            resolution_notes="Confirmed and removed from the marketplace.",
        )

        report.refresh_from_db()
        listing.refresh_from_db()
        self.assertTrue(listing_closed)
        self.assertEqual(report.status, ListingReport.STATUS_RESOLVED)
        self.assertEqual(listing.approval_status, Listing.APPROVAL_REJECTED)
        self.assertFalse(listing.is_publicly_active)

    def test_start_listing_conversation_rejects_listing_only_user(self):
        listing = self.create_listing()
        realtor = self.user.__class__.objects.create_user(
            username="agent",
            email="agent@gmail.com",
            password="test",
        )

        with self.assertRaises(ValidationError) as exc:
            start_listing_conversation(listing, realtor, "Interested.")

        self.assertIn("Verified student access is required", exc.exception.message_dict["body"][0])

    def test_start_listing_conversation_rejects_owner(self):
        listing = self.create_listing()

        with self.assertRaises(ValidationError) as exc:
            start_listing_conversation(listing, listing.owner, "Interested.")

        self.assertIn("You cannot message yourself", exc.exception.message_dict["body"][0])

    def test_start_listing_conversation_rejects_inactive_listing(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        listing = self.create_listing(status=Listing.STATUS_TAKEN)

        with self.assertRaises(ValidationError) as exc:
            start_listing_conversation(listing, participant, "Interested.")

        self.assertIn("no longer accepting new messages", exc.exception.message_dict["body"][0])

    def test_start_listing_conversation_rejects_inactive_listing_owner(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        listing = self.create_listing()
        listing.owner.is_active = False
        listing.owner.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError) as exc:
            start_listing_conversation(listing, participant, "Interested.")

        self.assertIn("no longer accepting new messages", exc.exception.message_dict["body"][0])

    def test_counterparty_avatar_url_is_exposed_in_conversation_payload(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        SocialAccount.objects.create(
            user=self.user,
            provider="google",
            uid="google-owner",
            extra_data={"picture": "https://example.com/owner-avatar.png"},
        )
        listing = self.create_listing()
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=listing.owner,
            participant=participant,
        )

        payload = serialize_conversation_for_user(conversation, participant)

        self.assertEqual(payload["counterparty_avatar_url"], "https://example.com/owner-avatar.png")

    def test_start_direct_conversation_creates_direct_thread(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        self._complete_roommate_profile(self.user)
        self._complete_roommate_profile(participant)

        conversation, message, created = start_direct_conversation(self.user, participant, "Want to compare options?")

        self.assertTrue(created)
        self.assertTrue(conversation.is_direct)
        self.assertIsNone(conversation.listing)
        self.assertEqual(message.sender, self.user)
        self.assertEqual(message.body, "Want to compare options?")
        self.assertEqual(conversation.last_message_preview, "Want to compare options?")

    def test_start_direct_conversation_reuses_existing_pair(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        self._complete_roommate_profile(self.user)
        self._complete_roommate_profile(participant)
        first_conversation, _, _ = start_direct_conversation(self.user, participant, "First note")

        second_conversation, _, created = start_direct_conversation(participant, self.user, "Replying back")

        self.assertFalse(created)
        self.assertEqual(first_conversation.id, second_conversation.id)
        self.assertEqual(ListingConversation.objects.filter(conversation_type="direct").count(), 1)

    def test_direct_conversation_model_normalizes_participant_order(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )

        conversation = ListingConversation.objects.create(
            conversation_type=ListingConversation.CONVERSATION_TYPE_DIRECT,
            owner=participant,
            participant=self.user,
        )

        self.assertEqual(conversation.owner_id, self.user.id)
        self.assertEqual(conversation.participant_id, participant.id)

    def test_direct_conversation_payload_uses_roommate_context(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
            first_name="Riley",
        )
        self._complete_roommate_profile(self.user)
        self._complete_roommate_profile(participant)
        participant.student_profile.major = "Biology"
        participant.student_profile.save(update_fields=["major"])
        conversation, _, _ = start_direct_conversation(self.user, participant, "Want to compare options?")

        payload = serialize_conversation_for_user(conversation, self.user)

        self.assertEqual(payload["conversation_type"], "direct")
        self.assertEqual(payload["context_title"], "Roommate chat")
        self.assertEqual(payload["context_subtitle"], "Biology")
        self.assertEqual(payload["listing_title"], "")

    def test_start_direct_conversation_requires_completed_roommate_profiles(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        self._complete_roommate_profile(participant)

        with self.assertRaises(ValidationError) as exc:
            start_direct_conversation(self.user, participant, "Want to compare options?")

        self.assertIn("Complete your roommate profile before messaging matches.", exc.exception.message_dict["body"][0])

    def test_start_direct_conversation_allows_completed_profile_without_roommate_post(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        self._complete_roommate_profile(self.user)
        self._complete_roommate_profile(participant)

        conversation, message, created = start_direct_conversation(self.user, participant, "Want to compare options?")

        self.assertTrue(created)
        self.assertTrue(conversation.is_direct)
        self.assertEqual(message.body, "Want to compare options?")

    def test_start_direct_conversation_allows_group_lead_with_active_group_post(self):
        participant = self.user.__class__.objects.create_user(
            username="group-lead-match",
            email="group-lead-match@bc.edu",
            password="test",
        )
        group_member = self.user.__class__.objects.create_user(
            username="group-member-match",
            email="group-member-match@bc.edu",
            password="test",
        )
        self._complete_roommate_profile(self.user)
        self._complete_roommate_profile(participant)
        self._complete_roommate_profile(group_member)
        group = self.create_roommate_group(lead=participant, members=[group_member])
        self.create_group_roommate_post(group=group)

        conversation, _, created = start_direct_conversation(self.user, participant, "Want to compare options?")

        self.assertTrue(created)
        self.assertTrue(conversation.is_direct)

    def test_start_direct_conversation_allows_existing_thread_after_roommate_post_is_paused(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        self._complete_roommate_profile(self.user)
        self._complete_roommate_profile(participant)
        roommate_post = self.create_roommate_post(author=participant)
        conversation, _, _ = start_direct_conversation(self.user, participant, "First note")
        roommate_post.is_active = False
        roommate_post.save(update_fields=["is_active", "updated_at"])

        reused_conversation, _, created = start_direct_conversation(self.user, participant, "Second note")

        self.assertFalse(created)
        self.assertEqual(reused_conversation.id, conversation.id)

    def test_send_conversation_message_rejects_inactive_counterparty(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        conversation = ListingConversation.objects.create(
            conversation_type=ListingConversation.CONVERSATION_TYPE_DIRECT,
            owner=self.user,
            participant=participant,
        )
        participant.is_active = False
        participant.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError) as exc:
            send_conversation_message(conversation, self.user, "Following up.")

        self.assertIn(
            "This conversation is read-only because one participant no longer has an active account.",
            exc.exception.message_dict["body"][0],
        )

    def test_deleting_conversation_hides_it_for_one_user_only(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        listing = self.create_listing()
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=listing.owner,
            participant=participant,
        )

        deleted = delete_conversation_for_user(conversation, participant)
        conversation.refresh_from_db()

        self.assertTrue(deleted)
        self.assertIsNotNone(conversation.participant_deleted_at)
        self.assertFalse(accessible_conversations_for_user(participant).filter(pk=conversation.pk).exists())
        self.assertTrue(accessible_conversations_for_user(listing.owner).filter(pk=conversation.pk).exists())

    def test_new_message_restores_deleted_conversation_visibility(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        listing = self.create_listing()
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=listing.owner,
            participant=participant,
        )
        delete_conversation_for_user(conversation, participant)

        send_listing_message(conversation, listing.owner, "Still available.")
        conversation.refresh_from_db()

        self.assertIsNone(conversation.participant_deleted_at)
        self.assertTrue(accessible_conversations_for_user(participant).filter(pk=conversation.pk).exists())

    def test_conversation_is_removed_when_both_users_delete_it(self):
        participant = self.user.__class__.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        listing = self.create_listing()
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=listing.owner,
            participant=participant,
        )

        delete_conversation_for_user(conversation, participant)
        delete_conversation_for_user(conversation, listing.owner)

        self.assertFalse(ListingConversation.objects.filter(pk=conversation.pk).exists())


class ListingGeocodingTests(ListingTestCase):
    def _image_upload(self, name="photo.png"):
        buffer = BytesIO()
        Image.new("RGB", (8, 8), color=(79, 70, 229)).save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    @override_settings(LISTING_GEOCODING_ENABLED=False)
    @patch("listings.geocoding.requests.get")
    def test_geocode_listing_address_returns_none_without_network_when_disabled(self, requests_get_mock):
        latitude, longitude = geocode_listing_address("140 Commonwealth Ave")

        self.assertIsNone(latitude)
        self.assertIsNone(longitude)
        requests_get_mock.assert_not_called()

    @override_settings(
        LISTING_GEOCODING_ENABLED=True,
        LISTING_GEOCODER_URL="https://photon.example/api/",
        LISTING_GEOCODER_USER_AGENT="PadlyTests/1.0",
        LISTING_GEOCODER_TIMEOUT_SECONDS=7,
    )
    @patch("listings.geocoding.requests.get")
    def test_geocode_listing_address_parses_first_feature_coordinates(self, requests_get_mock):
        response_mock = Mock()
        response_mock.raise_for_status.return_value = None
        response_mock.json.return_value = {
            "features": [
                {"geometry": {"coordinates": [-71.1685, 42.3355]}},
            ]
        }
        requests_get_mock.return_value = response_mock

        latitude, longitude = geocode_listing_address("140 Commonwealth Ave")

        self.assertEqual((latitude, longitude), (42.3355, -71.1685))
        requests_get_mock.assert_called_once_with(
            "https://photon.example/api/",
            params={"q": "140 Commonwealth Ave", "limit": 1, "lat": 42.3355, "lon": -71.1685},
            headers={"User-Agent": "PadlyTests/1.0"},
            timeout=7,
        )

    @override_settings(LISTING_GEOCODING_ENABLED=True)
    @patch("listings.geocoding.requests.get")
    def test_geocode_listing_address_rejects_invalid_coordinate_payload(self, requests_get_mock):
        response_mock = Mock()
        response_mock.raise_for_status.return_value = None
        response_mock.json.return_value = {
            "features": [
                {"geometry": {"coordinates": ["not-a-number", "still-not-a-number"]}},
            ]
        }
        requests_get_mock.return_value = response_mock

        latitude, longitude = geocode_listing_address("140 Commonwealth Ave")

        self.assertIsNone(latitude)
        self.assertIsNone(longitude)

    @override_settings(LISTING_IMAGE_TOTAL_LIMIT=1)
    def test_listing_image_total_limit_applies_to_direct_model_saves(self):
        with TemporaryDirectory() as temp_dir, override_settings(MEDIA_ROOT=temp_dir):
            listing = self.create_listing()
            ListingImage.objects.create(listing=listing, image=self._image_upload("one.png"))

            with self.assertRaises(ValidationError) as exc:
                ListingImage.objects.create(listing=listing, image=self._image_upload("two.png"))

        self.assertIn("Each listing can have up to 1 images total.", exc.exception.message_dict["image"][0])


class ListingAddressPrimitiveTests(ListingTestCase):
    @override_settings(
        LISTING_MAPS_ENABLED=False,
        LISTING_GEOAPIFY_API_KEY="geoapify-test-key",
        LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
    )
    def test_geoapify_config_is_enabled_without_map_browsing_ui(self):
        config = get_geoapify_autocomplete_config()

        self.assertEqual(
            config,
            {
                "enabled": True,
                "url": "https://api.geoapify.com/v1/geocode/autocomplete",
                "api_key": "geoapify-test-key",
            },
        )

    @override_settings(
        LISTING_MAPS_ENABLED=True,
        LISTING_GEOAPIFY_API_KEY="",
        LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
    )
    def test_geoapify_config_fails_closed_without_api_key(self):
        config = get_geoapify_autocomplete_config()

        self.assertEqual(
            config,
            {
                "enabled": False,
                "url": None,
                "api_key": None,
            },
        )

    def test_address_selection_token_round_trip_preserves_normalized_payload(self):
        payload = {
            "provider_id": "geoapify:place:123",
            "label": "140 Commonwealth Ave, Chestnut Hill, MA 02467",
            "address_line_1": "140 Commonwealth Ave",
            "address_line_2": "",
            "city": "Chestnut Hill",
            "state": "MA",
            "postal_code": "02467",
            "country": "US",
            "latitude": 42.3355,
            "longitude": -71.1685,
        }

        token = sign_address_selection(payload)

        self.assertEqual(unsign_address_selection(token, max_age=60), payload)

    def test_address_selection_token_rejects_expired_or_tampered_values(self):
        payload = {
            "provider_id": "geoapify:place:123",
            "label": "140 Commonwealth Ave, Chestnut Hill, MA 02467",
            "address_line_1": "140 Commonwealth Ave",
            "address_line_2": "",
            "city": "Chestnut Hill",
            "state": "MA",
            "postal_code": "02467",
            "country": "US",
            "latitude": 42.3355,
            "longitude": -71.1685,
        }
        token = sign_address_selection(payload)

        with self.assertRaises(SignatureExpired):
            unsign_address_selection(token, max_age=-1)

        with self.assertRaises(BadSignature):
            unsign_address_selection(f"{token}tampered", max_age=60)

    def test_geoapify_normalization_returns_minimal_suggestion_shape(self):
        payload = {
            "results": [
                {
                    "place_id": "abc123",
                    "formatted": "140 Commonwealth Ave, Chestnut Hill, MA 02467, United States of America",
                    "address_line1": "140 Commonwealth Ave",
                    "address_line2": "",
                    "city": "Chestnut Hill",
                    "state_code": "MA",
                    "postcode": "02467",
                    "country_code": "us",
                    "lat": 42.3355,
                    "lon": -71.1685,
                    "timezone": {"name": "America/New_York"},
                    "rank": {"confidence": 0.99},
                }
            ]
        }

        self.assertEqual(
            normalize_geoapify_suggestions(payload),
            [
                {
                    "provider_id": "geoapify:abc123",
                    "label": "140 Commonwealth Ave, Chestnut Hill, MA 02467",
                    "address_line_1": "140 Commonwealth Ave",
                    "address_line_2": "",
                    "city": "Chestnut Hill",
                    "state": "MA",
                    "postal_code": "02467",
                    "country": "US",
                    "primary_label": "140 Commonwealth Ave",
                    "latitude": 42.3355,
                    "longitude": -71.1685,
                }
            ],
        )

    def test_geoapify_normalization_returns_empty_list_for_malformed_payload_items(self):
        payload = {
            "results": [
                "not-a-dict",
                None,
                {"formatted": "missing place id"},
            ]
        }

        self.assertEqual(normalize_geoapify_suggestions(payload), [])

    def test_geoapify_normalization_accepts_fallback_address_fields_without_postcode(self):
        payload = {
            "results": [
                {
                    "place_id": "fallback-1",
                    "formatted": "",
                    "housenumber": "15",
                    "street": "Chiswick Rd",
                    "suburb": "Brighton",
                    "state": "Massachusetts",
                    "state_code": "MA",
                    "country": "United States",
                    "country_code": "us",
                    "lat": 42.3477,
                    "lon": -71.1538,
                }
            ]
        }

        self.assertEqual(
            normalize_geoapify_suggestions(payload),
            [
                {
                    "provider_id": "geoapify:fallback-1",
                    "label": "15 Chiswick Rd, Brighton, MA",
                    "address_line_1": "15 Chiswick Rd",
                    "address_line_2": "",
                    "city": "Brighton",
                    "state": "MA",
                    "postal_code": "",
                    "country": "US",
                    "primary_label": "15 Chiswick Rd",
                    "latitude": 42.3477,
                    "longitude": -71.1538,
                }
            ],
        )

    def test_geoapify_normalization_accepts_geojson_feature_payload_and_dedupes_duplicate_address_matches(self):
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "place_id": "building-1",
                        "formatted": "140 Commonwealth Avenue, Newton, MA 02467, United States of America",
                        "address_line1": "140 Commonwealth Avenue",
                        "housenumber": "140",
                        "street": "Commonwealth Avenue",
                        "city": "Newton",
                        "state_code": "MA",
                        "postcode": "02467",
                        "country_code": "us",
                    },
                    "geometry": {"type": "Point", "coordinates": [-71.168984, 42.33806]},
                },
                {
                    "type": "Feature",
                    "properties": {
                        "place_id": "amenity-1",
                        "formatted": (
                            "Boston College Chestnut Hill Campus, 140 Commonwealth Avenue, Newton, MA 02467, "
                            "United States of America"
                        ),
                        "address_line1": "Boston College Chestnut Hill Campus",
                        "housenumber": "140",
                        "street": "Commonwealth Avenue",
                        "city": "Newton",
                        "state_code": "MA",
                        "postcode": "02467",
                        "country_code": "us",
                    },
                    "geometry": {"type": "Point", "coordinates": [-71.1682664, 42.3354481]},
                },
            ],
        }

        self.assertEqual(
            normalize_geoapify_suggestions(payload),
            [
                {
                    "provider_id": "geoapify:building-1",
                    "label": "140 Commonwealth Avenue, Newton, MA 02467",
                    "address_line_1": "140 Commonwealth Avenue",
                    "address_line_2": "",
                    "city": "Newton",
                    "state": "MA",
                    "postal_code": "02467",
                    "country": "US",
                    "primary_label": "140 Commonwealth Avenue",
                    "latitude": 42.33806,
                    "longitude": -71.168984,
                }
            ],
        )
