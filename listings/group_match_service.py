from decimal import Decimal
from urllib.parse import urlencode

from django.db.models import DecimalField, ExpressionWrapper, F, Q
from django.urls import reverse

from communications.selectors import direct_conversations_by_counterparty
from users.selectors import compatible_students_for_user

from .group_matching import BudgetRange, Preferences
from .selectors import marketplace_listings_for_user, with_favorite_state

GROUP_MATCH_DEFAULTS = {
    "unit_size": 1,
    "budget_min": 1000,
    "budget_max": 1600,
    "cleanliness": 4,
    "social": 3,
    "sleep_schedule": "balanced",
    "desired_group_min": 3,
    "desired_group_max": 5,
    "location_keywords": "",
}
GROUP_MATCH_QUERY_FIELDS = (
    "unit_size",
    "budget_min",
    "budget_max",
    "cleanliness",
    "social",
    "sleep_schedule",
    "desired_group_min",
    "desired_group_max",
    "location_keywords",
)


def parse_location_keywords(raw_keywords: str) -> tuple[str, ...]:
    if not raw_keywords:
        return ()
    parts = [keyword.strip() for keyword in raw_keywords.split(",")]
    return tuple(keyword for keyword in parts if keyword)


def _clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def group_match_sleep_schedule_from_bedtime(bedtime):
    if bedtime is None:
        return GROUP_MATCH_DEFAULTS["sleep_schedule"]
    if bedtime >= 23 or bedtime <= 2:
        return "late"
    if 20 <= bedtime <= 22:
        return "early"
    return "balanced"


def group_match_social_from_profile(profile):
    values = [
        value
        for value in (
            profile.guest_level,
            profile.drink,
            profile.party,
            profile.noise_level,
        )
        if value is not None
    ]
    if not values:
        return GROUP_MATCH_DEFAULTS["social"]
    return _clamp(round(sum(values) / len(values)), 1, 5)


def group_match_size_defaults(social_preference):
    if social_preference >= 4:
        return 4, 6
    if social_preference <= 2:
        return 2, 4
    return 3, 5


def group_match_initial_data(user):
    defaults = GROUP_MATCH_DEFAULTS.copy()
    profile = getattr(user, "student_profile", None)
    if profile is None:
        return defaults

    if profile.messy_level is not None:
        defaults["cleanliness"] = profile.messy_level
    defaults["social"] = group_match_social_from_profile(profile)
    defaults["sleep_schedule"] = group_match_sleep_schedule_from_bedtime(profile.bedtime)
    defaults["desired_group_min"], defaults["desired_group_max"] = group_match_size_defaults(defaults["social"])
    return defaults


def group_match_preferences(raw_data):
    location_keywords = parse_location_keywords(raw_data.get("location_keywords", ""))
    preferences = Preferences(
        budget=BudgetRange(Decimal(str(raw_data["budget_min"])), Decimal(str(raw_data["budget_max"]))),
        cleanliness=int(raw_data["cleanliness"]),
        social=int(raw_data["social"]),
        sleep_schedule=raw_data["sleep_schedule"],
        desired_group_min=int(raw_data["desired_group_min"]),
        desired_group_max=int(raw_data["desired_group_max"]),
        location_keywords=location_keywords,
    )
    return preferences, location_keywords


def group_match_option_url(*, effective_data, option_id):
    params = {
        field_name: str(effective_data[field_name])
        for field_name in GROUP_MATCH_QUERY_FIELDS
        if field_name in effective_data and effective_data[field_name] not in ("", None)
    }
    params["group"] = option_id
    return f"{reverse('listings:group_match')}?{urlencode(params)}"


def group_match_roommate_limit(additional_roommates_needed):
    return min(max(additional_roommates_needed, 3), 6)


def group_match_roommate_matches(user):
    base_matches = compatible_students_for_user(user, limit=18)
    conversation_map = direct_conversations_by_counterparty(user, [match["user"] for match in base_matches])
    decorated_matches = []
    for match in base_matches:
        score = match["score"]
        conversation = conversation_map.get(match["user"].id)
        if score is None:
            score_variant = "neutral"
        elif score >= 75:
            score_variant = "primary"
        elif score >= 50:
            score_variant = "secondary"
        else:
            score_variant = "neutral"

        decorated_matches.append(
            {
                **match,
                "score_variant": score_variant,
                "profile_url": reverse("users:public_profile", args=[match["user"].id]),
                "message_url": reverse("communications:detail", args=[conversation.id])
                if conversation is not None
                else f"{reverse('users:public_profile', args=[match['user'].id])}#message-user",
                "message_label": "Open chat" if conversation is not None else "Message",
            }
        )

    return decorated_matches


def group_match_listings_by_size(user, *, unit_size, preferences):
    minimum_group_size = max(unit_size, preferences.desired_group_min)
    maximum_group_size = max(minimum_group_size, preferences.desired_group_max)
    target_sizes = tuple(range(minimum_group_size, maximum_group_size + 1))

    price_per_person = ExpressionWrapper(
        F("price") / F("rooms"),
        output_field=DecimalField(max_digits=10, decimal_places=2),
    )
    queryset = with_favorite_state(marketplace_listings_for_user(user), user).filter(rooms__in=target_sizes)
    queryset = queryset.annotate(price_per_person=price_per_person).filter(
        price_per_person__gte=preferences.budget.minimum,
        price_per_person__lte=preferences.budget.maximum,
    )

    if preferences.location_keywords:
        location_query = Q()
        for keyword in preferences.location_keywords:
            location_query |= Q(address__icontains=keyword) | Q(title__icontains=keyword)
        queryset = queryset.filter(location_query)

    listings_by_size = {group_size: [] for group_size in target_sizes}
    for listing in queryset:
        listings_by_size.setdefault(listing.rooms, []).append(listing)
    return listings_by_size
