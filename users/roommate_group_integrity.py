from django.db import transaction
from django.utils import timezone

from listings.models import RoommateGroup, RoommateGroupMembership

from .models import RoommateGroupInvite

ACTIVE_INVITE_STATUSES = [
    RoommateGroupInvite.STATUS_PENDING_APPROVAL,
    RoommateGroupInvite.STATUS_PENDING_INVITEE,
]


def repair_roommate_group_integrity(*, apply=False):
    summary = {
        "groups_missing_lead_membership": 0,
        "lead_membership_conflicts": 0,
        "lead_memberships_created": 0,
        "group_posts_out_of_sync": 0,
        "group_posts_resynced": 0,
        "invalid_active_invites": 0,
        "invalid_active_invites_cancelled": 0,
    }

    for group in RoommateGroup.objects.select_related("lead"):
        has_lead_membership = RoommateGroupMembership.objects.filter(group=group, user=group.lead).exists()
        if not has_lead_membership:
            summary["groups_missing_lead_membership"] += 1
            lead_has_other_group = RoommateGroupMembership.objects.filter(user=group.lead).exclude(group=group).exists()
            if lead_has_other_group:
                summary["lead_membership_conflicts"] += 1
            elif apply:
                RoommateGroupMembership.objects.create(group=group, user=group.lead)
                summary["lead_memberships_created"] += 1

        try:
            group_post = group.roommate_post
        except RoommateGroup.roommate_post.RelatedObjectDoesNotExist:
            group_post = None

        if group_post is None:
            continue

        member_count = RoommateGroupMembership.objects.filter(group=group).count()
        if group_post.current_group_size != member_count:
            summary["group_posts_out_of_sync"] += 1
            if apply:
                group_post.current_group_size = member_count
                group_post.save(update_fields=["current_group_size", "updated_at"])
                summary["group_posts_resynced"] += 1

    active_invites = RoommateGroupInvite.objects.filter(status__in=ACTIVE_INVITE_STATUSES).select_related(
        "group",
        "invitee",
    )
    for invite in active_invites:
        invitee_membership = RoommateGroupMembership.objects.filter(user=invite.invitee).first()
        should_cancel = False
        if invitee_membership is not None:
            should_cancel = True
        elif invite.status == RoommateGroupInvite.STATUS_PENDING_APPROVAL:
            current_member_ids = set(
                RoommateGroupMembership.objects.filter(group=invite.group).values_list("user_id", flat=True)
            )
            approval_member_ids = set(invite.approvals.values_list("member_id", flat=True))
            if current_member_ids != approval_member_ids:
                should_cancel = True

        if not should_cancel:
            continue

        summary["invalid_active_invites"] += 1
        if apply:
            with transaction.atomic():
                invite = RoommateGroupInvite.objects.select_for_update().get(pk=invite.pk)
                if invite.status in ACTIVE_INVITE_STATUSES:
                    invite.status = RoommateGroupInvite.STATUS_CANCELLED
                    invite.responded_at = timezone.now()
                    invite.save(update_fields=["status", "responded_at", "updated_at"])
                    summary["invalid_active_invites_cancelled"] += 1

    return summary
