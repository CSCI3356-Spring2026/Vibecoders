from django.urls import reverse

from communications.selectors import direct_conversations_by_counterparty
from users.compatibility import compatibility_highlights, compute_compatibility


def _score_variant(score):
    if score is None:
        return "neutral"
    if score >= 75:
        return "primary"
    if score >= 50:
        return "secondary"
    return "neutral"


def decorate_roommate_posts_for_user(user, roommate_posts):
    posts = list(roommate_posts)
    counterparties = [post.author for post in posts]
    conversation_map = direct_conversations_by_counterparty(user, counterparties) if counterparties else {}
    my_profile = getattr(user, "student_profile", None) if getattr(user, "can_use_roommate_matching", False) else None

    for post in posts:
        their_profile = getattr(post.author, "student_profile", None)
        score = compute_compatibility(my_profile, their_profile) if my_profile and their_profile else None
        conversation = conversation_map.get(post.author_id)
        post.ui_score = score
        post.ui_score_variant = _score_variant(score)
        post.ui_highlights = compatibility_highlights(my_profile, their_profile)
        post.ui_profile_url = reverse("users:public_profile", args=[post.author_id])
        post.ui_can_message = getattr(user, "can_use_roommate_matching", False) and user.id != post.author_id
        post.ui_message_url = (
            reverse("communications:detail", args=[conversation.id])
            if conversation is not None
            else f"{post.ui_profile_url}#message-user"
        )
        post.ui_message_label = "Open chat" if conversation is not None else "Message lead"
        post.ui_has_existing_conversation = conversation is not None
        post.ui_author_major = getattr(their_profile, "major", "")

    posts.sort(
        key=lambda post: (
            post.ui_score is not None,
            post.ui_score or -1,
            post.updated_at,
        ),
        reverse=True,
    )
    return posts
