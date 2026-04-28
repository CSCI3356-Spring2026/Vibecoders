from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from listings.models import RoommateGroup, RoommateGroupMembership, RoommatePost

from ..models import Role, RoommateGroupInvite
from .helpers import User


class SetUserRoleCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="eagle", email="eagle@bc.edu", password="test")
        self.external_user = User.objects.create_user(username="agent", email="agent@gmail.com", password="test")

    def test_promote_to_admin(self):
        call_command("set_user_role", "eagle@bc.edu", "admin", stdout=StringIO())
        self.user.refresh_from_db()

        self.assertEqual(self.user.role, Role.ADMIN)

    def test_restore_bc_user_to_student(self):
        self.user.role = Role.ADMIN
        self.user.save()
        call_command("set_user_role", "eagle@bc.edu", "student", stdout=StringIO())
        self.user.refresh_from_db()

        self.assertEqual(self.user.role, Role.STUDENT)

    def test_restore_external_user_to_realtor(self):
        self.external_user.role = Role.ADMIN
        self.external_user.save()
        call_command("set_user_role", "agent@gmail.com", "realtor", stdout=StringIO())
        self.external_user.refresh_from_db()

        self.assertEqual(self.external_user.role, Role.REALTOR)

    def test_invalid_student_assignment_for_external_email_raises(self):
        self.external_user.role = Role.ADMIN
        self.external_user.save()

        with self.assertRaises(CommandError):
            call_command("set_user_role", "agent@gmail.com", "student", stderr=StringIO())

    def test_nonexistent_user_raises(self):
        with self.assertRaises(CommandError):
            call_command("set_user_role", "nobody@bc.edu", "admin", stderr=StringIO())


class RepairProfileCompletionIntegrityCommandTests(TestCase):
    def _complete_student_profile(self, user, **overrides):
        profile = user.student_profile
        defaults = {
            "preferred_name": user.first_name or user.username,
            "age": 20,
            "gender": "male",
            "institution_status": "undergraduate",
            "major": "Computer Science",
            "bio": "Easygoing roommate.",
            "messy_level": 3,
            "guest_level": 3,
            "bedtime": 22,
            "noise_level": 3,
            "drink": 2,
            "party": 2,
        }
        defaults.update(overrides)
        for field_name, value in defaults.items():
            setattr(profile, field_name, value)
        profile.save()

    def _complete_admin_profile(self, user, **overrides):
        profile = user.admin_profile
        defaults = {
            "preferred_name": user.first_name or user.username,
            "bio": "Manages listings near campus.",
        }
        defaults.update(overrides)
        for field_name, value in defaults.items():
            setattr(profile, field_name, value)
        profile.save()

    def test_repair_command_clears_false_positive_completion_and_preserves_valid_completion(self):
        incomplete_admin = User.objects.create_user(
            username="incomplete-admin",
            email="incomplete-admin@bc.edu",
            password="test",
            role=Role.ADMIN,
        )
        incomplete_admin.profile_completed_at = timezone.now()
        incomplete_admin.save(update_fields=["profile_completed_at"])

        complete_student = User.objects.create_user(
            username="complete-student",
            email="complete-student@bc.edu",
            password="test",
        )
        self._complete_student_profile(complete_student)
        valid_timestamp = timezone.now()
        complete_student.profile_completed_at = valid_timestamp
        complete_student.save(update_fields=["profile_completed_at"])

        output = StringIO()

        call_command("repair_profile_completion_integrity", stdout=output)

        incomplete_admin.refresh_from_db()
        complete_student.refresh_from_db()
        self.assertIsNone(incomplete_admin.profile_completed_at)
        self.assertEqual(complete_student.profile_completed_at, valid_timestamp)
        self.assertIn("Profile completions cleared: 1", output.getvalue())
        self.assertIn("Profile completions set: 0", output.getvalue())

    def test_repair_command_sets_completion_when_current_profile_is_complete(self):
        student = User.objects.create_user(username="set-student", email="set-student@bc.edu", password="test")
        self._complete_student_profile(student)

        output = StringIO()

        call_command("repair_profile_completion_integrity", stdout=output)

        student.refresh_from_db()
        self.assertIsNotNone(student.profile_completed_at)
        self.assertIn("Profile completions set: 1", output.getvalue())


class RepairRoommateGroupIntegrityCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="leader", email="leader@bc.edu", password="test")

    def _complete_profile(self, user, **overrides):
        profile = user.student_profile
        defaults = {
            "preferred_name": user.first_name or user.username,
            "major": "Computer Science",
            "institution_status": "undergraduate",
            "bio": "Easygoing roommate.",
            "messy_level": 5,
            "guest_level": 3,
            "bedtime": 23,
            "noise_level": 5,
            "smoke": True,
            "drink": 5,
            "party": 5,
            "pets": True,
        }
        defaults.update(overrides)
        for field_name, value in defaults.items():
            setattr(profile, field_name, value)
        profile.save()
        user.profile_completed_at = timezone.now()
        user.save(update_fields=["profile_completed_at"])

    def test_audit_mode_reports_but_does_not_repair(self):
        self._complete_profile(self.user)
        group = RoommateGroup.objects.create(lead=self.user, name="Audit Group")
        output = StringIO()

        call_command("repair_roommate_group_integrity", stdout=output)

        self.assertIn("Groups missing lead membership: 1", output.getvalue())
        self.assertFalse(RoommateGroupMembership.objects.filter(group=group, user=self.user).exists())

    def test_apply_mode_creates_missing_lead_membership_and_resyncs_group_post(self):
        self._complete_profile(self.user)
        group = RoommateGroup.objects.create(lead=self.user, name="Repair Group")
        lead_membership = RoommateGroupMembership.objects.create(group=group, user=self.user)
        roommate_post = RoommatePost.objects.create(
            group=group,
            title="Need one more",
            description="Looking for one more roommate for a late-summer apartment search.",
            housing_status=RoommatePost.HOUSING_NEED_HOME,
            current_group_size=1,
            open_spots=1,
            budget_min=1000,
            budget_max=1400,
            move_in_date=timezone.localdate() + timedelta(days=30),
            neighborhoods="Allston",
        )
        RoommatePost.objects.filter(pk=roommate_post.pk).update(current_group_size=99)
        lead_membership.delete()
        output = StringIO()

        call_command("repair_roommate_group_integrity", "--apply", stdout=output)

        self.assertTrue(RoommateGroupMembership.objects.filter(group=group, user=self.user).exists())
        roommate_post.refresh_from_db()
        self.assertEqual(roommate_post.current_group_size, 1)
        self.assertIn("Lead memberships created: 1", output.getvalue())
        self.assertIn("Group posts resynced: 1", output.getvalue())

    def test_apply_mode_cancels_active_invite_for_user_already_in_group(self):
        invitee = User.objects.create_user(username="invitee", email="invitee@bc.edu", password="test")
        other_lead = User.objects.create_user(username="other", email="other@bc.edu", password="test")
        self._complete_profile(self.user)
        self._complete_profile(invitee)
        self._complete_profile(other_lead)

        inviting_group = RoommateGroup.objects.create(lead=self.user, name="Inviting Group")
        RoommateGroupMembership.objects.create(group=inviting_group, user=self.user)
        other_group = RoommateGroup.objects.create(lead=other_lead, name="Other Group")
        RoommateGroupMembership.objects.create(group=other_group, user=other_lead)
        RoommateGroupMembership.objects.create(group=other_group, user=invitee)

        invite = RoommateGroupInvite.objects.create(
            group=inviting_group,
            inviter=self.user,
            invitee=invitee,
            status=RoommateGroupInvite.STATUS_PENDING_INVITEE,
        )
        output = StringIO()

        call_command("repair_roommate_group_integrity", "--apply", stdout=output)

        invite.refresh_from_db()
        self.assertEqual(invite.status, RoommateGroupInvite.STATUS_CANCELLED)
        self.assertIsNotNone(invite.responded_at)
        self.assertIn("Invalid active invites cancelled: 1", output.getvalue())
