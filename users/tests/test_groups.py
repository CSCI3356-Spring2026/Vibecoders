from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from communications.models import ListingConversation
from listings.models import RoommateGroup, RoommateGroupMembership, RoommatePost
from users.models import RoommateGroupInvite


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
        self.assertTrue(RoommateGroupMembership.objects.filter(group=invite.group, user=invitee).exists())

    def test_group_invite_requires_member_approval(self):
        member = self.User.objects.create_user(username="member", email="member@bc.edu", password="test")
        invitee = self.User.objects.create_user(username="new", email="new@bc.edu", password="test")
        self._complete_profile(member)
        self._complete_profile(invitee)

        group = RoommateGroup.objects.create(lead=self.user, name="Test Group")
        RoommateGroupMembership.objects.create(group=group, user=self.user)
        RoommateGroupMembership.objects.create(group=group, user=member)

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

    def test_cannot_invite_student_who_is_already_in_another_group(self):
        invitee = self.User.objects.create_user(username="invitee", email="invitee@bc.edu", password="test")
        other_lead = self.User.objects.create_user(username="other", email="other@bc.edu", password="test")
        self._complete_profile(invitee)
        self._complete_profile(other_lead)

        other_group = RoommateGroup.objects.create(lead=other_lead, name="Elsewhere")
        RoommateGroupMembership.objects.create(group=other_group, user=other_lead)
        RoommateGroupMembership.objects.create(group=other_group, user=invitee)

        self.client.force_login(self.user)
        response = self.client.post(reverse("users:send_group_invite", args=[invitee.id]), follow=True)

        self.assertContains(response, "already in a roommate group")
        self.assertFalse(RoommateGroupInvite.objects.filter(invitee=invitee, inviter=self.user).exists())

    def test_accepting_group_invite_updates_group_post_size(self):
        invitee = self.User.objects.create_user(username="invitee", email="invitee@bc.edu", password="test")
        self._complete_profile(invitee)

        group = RoommateGroup.objects.create(lead=self.user, name="Test Group")
        RoommateGroupMembership.objects.create(group=group, user=self.user)
        group_post = RoommatePost.objects.create(
            group=group,
            title="Need one more",
            description="Looking for one more roommate for our apartment search.",
            housing_status=RoommatePost.HOUSING_NEED_HOME,
            current_group_size=1,
            open_spots=1,
            budget_min=1000,
            budget_max=1400,
            move_in_date=timezone.localdate() + timedelta(days=30),
            neighborhoods="Allston",
        )

        self.client.force_login(self.user)
        self.client.post(reverse("users:send_group_invite", args=[invitee.id]))
        invite = RoommateGroupInvite.objects.get(invitee=invitee)

        self.client.force_login(invitee)
        self.client.post(reverse("users:accept_group_invite", args=[invite.id]))

        group_post.refresh_from_db()
        self.assertEqual(group_post.current_group_size, 2)

    def test_removing_group_member_updates_group_post_size(self):
        member = self.User.objects.create_user(username="member", email="member@bc.edu", password="test")
        self._complete_profile(member)

        group = RoommateGroup.objects.create(lead=self.user, name="Test Group")
        RoommateGroupMembership.objects.create(group=group, user=self.user)
        membership = RoommateGroupMembership.objects.create(group=group, user=member)
        group_post = RoommatePost.objects.create(
            group=group,
            title="Quiet two-person search",
            description="We want a calm apartment and are narrowing down our shortlist.",
            housing_status=RoommatePost.HOUSING_NEED_HOME,
            current_group_size=2,
            open_spots=1,
            budget_min=1000,
            budget_max=1400,
            move_in_date=timezone.localdate() + timedelta(days=30),
            neighborhoods="Brighton",
        )

        self.client.force_login(self.user)
        response = self.client.post(reverse("listings:remove_group_member", args=[membership.id]))

        self.assertEqual(response.status_code, 302)
        group_post.refresh_from_db()
        self.assertEqual(group_post.current_group_size, 1)

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

        group = RoommateGroup.objects.create(lead=self.user, name="Test Group")
        RoommateGroupMembership.objects.create(group=group, user=self.user)
        RoommateGroupMembership.objects.create(group=group, user=buddy)

        self.client.force_login(self.user)
        response = self.client.get(reverse("users:browse_roommates"), {"q": "Casey"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "52% match")
