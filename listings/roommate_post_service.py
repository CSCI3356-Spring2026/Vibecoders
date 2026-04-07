from django.urls import reverse

from communications.selectors import direct_conversations_by_counterparty
from users.compatibility import (
    compatibility_highlights,
    compute_compatibility,
    compute_group_compatibility,
    group_compatibility_highlights,
)


def _score_variant(score):
    if score is None:
        return "neutral"
    if score >= 75:
        return "primary"
    if score >= 50:
        return "secondary"
    return "neutral"


def _group_compatibility(my_profile, members):
    if my_profile is None:
        return None, []
    scores = []
    highlights = []
    for member in members:
        member_profile = getattr(member, "student_profile", None)
        if member_profile is None:
            continue
        score = compute_compatibility(my_profile, member_profile)
        if score is not None:
            scores.append(score)
        highlights.extend(compatibility_highlights(my_profile, member_profile, limit=2))
    if not scores:
        return None, []
    deduped_highlights = []
    for highlight in highlights:
        if highlight not in deduped_highlights:
            deduped_highlights.append(highlight)
    return round(sum(scores) / len(scores)), deduped_highlights[:3]


def decorate_roommate_posts_for_user(user, roommate_posts, *, group_profiles=None):
    posts = list(roommate_posts)
    counterparties = [post.lead_user for post in posts if post.lead_user is not None]
    conversation_map = direct_conversations_by_counterparty(user, counterparties) if counterparties else {}
    my_profile = getattr(user, "student_profile", None) if getattr(user, "can_use_roommate_matching", False) else None
    use_group_profiles = group_profiles or []

    for post in posts:
        their_profile = getattr(post.author, "student_profile", None)
        if post.group_id:
            score, highlights = _group_compatibility(my_profile, post.member_users)
        elif use_group_profiles:
            score = (
                compute_group_compatibility(use_group_profiles, their_profile)
                if use_group_profiles and their_profile
                else None
            )
            highlights = (
                group_compatibility_highlights(use_group_profiles, their_profile)
                if use_group_profiles and their_profile
                else []
            )
        else:
            score = compute_compatibility(my_profile, their_profile) if my_profile and their_profile else None
            highlights = compatibility_highlights(my_profile, their_profile)
        conversation = conversation_map.get(post.author_id)
        post.ui_score = score
        post.ui_score_variant = _score_variant(score)
        post.ui_highlights = highlights
        post.ui_profile_url = reverse("users:public_profile", args=[post.author_id])
        post.ui_can_message = getattr(user, "can_use_roommate_matching", False) and user.id != post.author_id
        post.ui_message_url = (
            reverse("communications:detail", args=[conversation.id])
            if conversation is not None
            else f"{post.ui_profile_url}#message-user"
        )
        post.ui_message_label = "Open chat" if conversation is not None else "Message lead"
        post.ui_has_existing_conversation = conversation is not None
        post.ui_author_major = getattr(getattr(post.author, "student_profile", None), "major", "")
        post.ui_owner_label = post.group.name if post.group_id else post.author.display_name
        post.ui_owner_meta = (
            f"Led by {post.author.display_name}" if post.group_id else f"Posted by {post.author.display_name}"
        )
        post.ui_member_count = len(post.member_users)
        post.ui_member_names = [member.display_name for member in post.member_users[:4]]

    posts.sort(
        key=lambda post: (
            post.ui_score is not None,
            post.ui_score or -1,
            post.updated_at,
        ),
        reverse=True,
    )
    return posts