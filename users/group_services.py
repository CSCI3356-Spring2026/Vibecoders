from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from communications.services import get_or_create_direct_conversation, send_conversation_message
from listings.models import RoommateGroup as ListingsRoommateGroup
from listings.models import RoommateGroupMembership

from .models import (
    RoommateGroupInvite,
    RoommateGroupInviteApproval,
)
from .selectors import active_roommate_group_for_user, roommate_group_memberships


def _ensure_student_with_profile(user):
    if not getattr(user, "is_student", False):
        raise ValidationError("Student access is required.")
    if not getattr(user, "can_use_roommate_matching", False):
        raise ValidationError("Complete your roommate profile first.")


def _create_group_for_inviter(inviter):
    group = ListingsRoommateGroup.objects.create(
        lead=inviter,
        name=f"{inviter.display_name[:110]}'s Group",
    )
    _add_group_membership(group, inviter)
    return group


def _sync_group_post_size(group):
    try:
        roommate_post = group.roommate_post
    except ListingsRoommateGroup.roommate_post.RelatedObjectDoesNotExist:
        return
    current_size = group.member_count
    if roommate_post.current_group_size == current_size:
        return
    roommate_post.current_group_size = current_size
    roommate_post.save(update_fields=["current_group_size", "updated_at"])


def _add_group_membership(group, user):
    membership, created = RoommateGroupMembership.objects.get_or_create(group=group, user=user)
    _sync_group_post_size(group)
    return membership, created


def save_roommate_group_details(*, lead, group=None, name, description):
    _ensure_student_with_profile(lead)

    with transaction.atomic():
        if group is None:
            group = ListingsRoommateGroup(lead=lead)
        elif group.lead_id != lead.id:
            raise ValidationError("Only the group lead can update this roommate group.")

        group.name = name
        group.description = description
        group.save()
        _add_group_membership(group, lead)
        return group


def remove_group_member(*, acting_user, membership):
    _ensure_student_with_profile(acting_user)

    with transaction.atomic():
        membership = RoommateGroupMembership.objects.select_related("group", "user").get(pk=membership.pk)
        group = membership.group
        if group.lead_id != acting_user.id:
            raise ValidationError("Only the group leader can remove members.")
        if membership.user_id == acting_user.id:
            raise ValidationError("You can't remove yourself from the group.")

        membership.delete()
        _sync_group_post_size(group)
        return group


def _create_invite_approvals(invite, inviter):
    approvals = []
    memberships = list(roommate_group_memberships(invite.group))
    now = timezone.now()
    for membership in memberships:
        approved = True if membership.user_id == inviter.id else None
        responded_at = now if approved else None
        approvals.append(
            RoommateGroupInviteApproval(
                invite=invite,
                member=membership.user,
                approved=approved,
                responded_at=responded_at,
            )
        )
    RoommateGroupInviteApproval.objects.bulk_create(approvals)


def _all_group_members_approved(invite):
    approvals = invite.approvals.all()
    return approvals and all(approval.approved for approval in approvals)


def _send_invite_to_invitee(invite):
    inviter = invite.inviter
    invitee = invite.invitee
    conversation, created = get_or_create_direct_conversation(inviter, invitee)
    invite.conversation = conversation
    invite.status = RoommateGroupInvite.STATUS_PENDING_INVITEE
    invite.save(update_fields=["status", "conversation", "updated_at"])
    send_conversation_message(
        conversation,
        inviter,
        "Group invite sent. Accept or decline to join their roommate group.",
        conversation_created=created,
    )


def create_group_invite(inviter, invitee):
    _ensure_student_with_profile(inviter)
    _ensure_student_with_profile(invitee)
    if inviter.id == invitee.id:
        raise ValidationError("You cannot invite yourself.")

    with transaction.atomic():
        group = active_roommate_group_for_user(inviter)
        if group is None:
            group = _create_group_for_inviter(inviter)

        invitee_group = active_roommate_group_for_user(invitee)
        if invitee_group is not None:
            if invitee_group.pk == group.pk:
                raise ValidationError("This student is already in your group.")
            raise ValidationError("This student is already in a roommate group.")
        if RoommateGroupMembership.objects.filter(group=group, user=invitee).exists():
            raise ValidationError("This student is already in your group.")
        if RoommateGroupInvite.objects.filter(
            group=group,
            invitee=invitee,
            status__in=[
                RoommateGroupInvite.STATUS_PENDING_APPROVAL,
                RoommateGroupInvite.STATUS_PENDING_INVITEE,
            ],
        ).exists():
            raise ValidationError("An invite is already pending for this student.")

        invite = RoommateGroupInvite.objects.create(
            group=group,
            inviter=inviter,
            invitee=invitee,
            status=RoommateGroupInvite.STATUS_PENDING_APPROVAL,
        )
        _create_invite_approvals(invite, inviter)

        if _all_group_members_approved(invite):
            _send_invite_to_invitee(invite)

    return invite


def respond_to_invite_approval(invite, member, *, approve):
    with transaction.atomic():
        invite = RoommateGroupInvite.objects.select_for_update().get(pk=invite.pk)
        if invite.status != RoommateGroupInvite.STATUS_PENDING_APPROVAL:
            raise ValidationError("This invite is no longer awaiting approvals.")

        approval = RoommateGroupInviteApproval.objects.select_for_update().filter(invite=invite, member=member).first()
        if approval is None:
            raise ValidationError("You are not eligible to approve this invite.")
        if approval.responded_at is not None:
            raise ValidationError("You already responded to this invite.")

        approval.approved = bool(approve)
        approval.responded_at = timezone.now()
        approval.save(update_fields=["approved", "responded_at"])

        if not approval.approved:
            invite.status = RoommateGroupInvite.STATUS_CANCELLED
            invite.responded_at = timezone.now()
            invite.save(update_fields=["status", "responded_at", "updated_at"])
            return invite

        if _all_group_members_approved(invite):
            _send_invite_to_invitee(invite)

    return invite


def respond_to_group_invite(invite, invitee, *, accept):
    with transaction.atomic():
        invite = RoommateGroupInvite.objects.select_for_update().get(pk=invite.pk)
        if invite.invitee_id != invitee.id:
            raise ValidationError("You cannot respond to this invite.")
        if invite.status != RoommateGroupInvite.STATUS_PENDING_INVITEE:
            raise ValidationError("This invite is no longer active.")

        invite.responded_at = timezone.now()
        if accept:
            existing_group = active_roommate_group_for_user(invitee)
            if existing_group is not None and existing_group.pk != invite.group_id:
                raise ValidationError("You are already in a roommate group.")
            _add_group_membership(invite.group, invitee)
            invite.status = RoommateGroupInvite.STATUS_ACCEPTED
        else:
            invite.status = RoommateGroupInvite.STATUS_REJECTED
        invite.save(update_fields=["status", "responded_at", "updated_at"])

        if invite.conversation_id:
            message = "accepted" if accept else "declined"
            send_conversation_message(
                invite.conversation,
                invitee,
                f"Group invite {message}.",
            )

    return invite
