from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from communications.models import ListingConversation
from users.models import RoommateGroup, RoommateGroupInvite, RoommateGroupMember


class RoommateGroupTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.user = self.User.objects.create_user(username="leader", email="leader@bc.edu", password="test")
        self._complete_profile(self.user)

    def _complete_profile(self, user, **overrides):
        profile = user.student_profile
        defaults = {
            "preferred_name": user.first_name or user.username,
            "major": "Computer Science",
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

    def test_user_can_send_group_invite_and_accept(self):
        invitee = self.User.objects.create_user(username="invitee", email="invitee@bc.edu", password="test")
        self._complete_profile(invitee)
        self.client.force_login(self.user)

        response = self.client.post(reverse("users:send_group_invite", args=[invitee.id]))

        self.assertEqual(response.status_code, 302)
        invite = RoommateGroupInvite.objects.get(invitee=invitee)
        self.assertEqual(invite.status, RoommateGroupInvite.STATUS_PENDING_INVITEE)
        self.assertIsNotNone(invite.conversation_id)

        self.client.force_login(invitee)
        response = self.client.post(reverse("users:accept_group_invite", args=[invite.id]))

        self.assertEqual(response.status_code, 302)
        invite.refresh_from_db()
        self.assertEqual(invite.status, RoommateGroupInvite.STATUS_ACCEPTED)
        self.assertTrue(RoommateGroupMember.objects.filter(group=invite.group, user=invitee).exists())

    def test_group_invite_requires_member_approval(self):
        member = self.User.objects.create_user(username="member", email="member@bc.edu", password="test")
        invitee = self.User.objects.create_user(username="new", email="new@bc.edu", password="test")
        self._complete_profile(member)
        self._complete_profile(invitee)

        group = RoommateGroup.objects.create(created_by=self.user)
        RoommateGroupMember.objects.create(group=group, user=self.user)
        RoommateGroupMember.objects.create(group=group, user=member)

        self.client.force_login(self.user)
        response = self.client.post(reverse("users:send_group_invite", args=[invitee.id]))
        self.assertEqual(response.status_code, 302)
        invite = RoommateGroupInvite.objects.get(invitee=invitee)
        self.assertEqual(invite.status, RoommateGroupInvite.STATUS_PENDING_APPROVAL)
        self.assertIsNone(invite.conversation_id)

        self.client.force_login(member)
        response = self.client.post(reverse("users:approve_group_invite", args=[invite.id]))
        self.assertEqual(response.status_code, 302)
        invite.refresh_from_db()
        self.assertEqual(invite.status, RoommateGroupInvite.STATUS_PENDING_INVITEE)
        self.assertIsNotNone(invite.conversation_id)
        self.assertTrue(
            ListingConversation.objects.filter(pk=invite.conversation_id, conversation_type="direct").exists()
        )

    def test_browse_roommates_uses_group_compatibility(self):
        buddy = self.User.objects.create_user(username="buddy", email="buddy@bc.edu", password="test")
        candidate = self.User.objects.create_user(
            username="candidate",
            email="candidate@bc.edu",
            password="test",
            first_name="Casey",
        )
        self._complete_profile(
            buddy,
            messy_level=1,
            guest_level=1,
            bedtime=0,
            noise_level=1,
            smoke=False,
            drink=1,
            party=1,
            pets=False,
        )
        self._complete_profile(candidate)

        group = RoommateGroup.objects.create(created_by=self.user)
        RoommateGroupMember.objects.create(group=group, user=self.user)
        RoommateGroupMember.objects.create(group=group, user=buddy)

        self.client.force_login(self.user)
        response = self.client.get(reverse("users:browse_roommates"), {"q": "Casey"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "52% match")
