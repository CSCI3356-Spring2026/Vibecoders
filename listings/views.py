import logging
import re
from decimal import Decimal
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import DecimalField, ExpressionWrapper, F, Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from communications.forms import ConversationMessageForm
from communications.models import ListingConversation
from communications.selectors import direct_conversations_by_counterparty
from communications.services import (
    MESSAGE_SEND_RATE_LIMIT_ERROR,
    consume_message_send_rate_limit,
    start_listing_conversation,
)
from core.rate_limits import consume_rate_limit, request_rate_limit_identifier
from core.utils import get_page, preserved_query_suffix, safe_next_url
from users.selectors import compatible_students_for_user

from .address_provider import get_geoapify_autocomplete_config, normalize_geoapify_suggestions
from .address_signing import sign_address_selection
from .filtering import BEDROOMS_FILTER_MIN, PRICE_FILTER_MAX, PRICE_FILTER_MIN, apply_listing_filters
from .form_services import handle_listing_form_submission, validation_message
from .forms import GroupMatchPreferencesForm, ListingForm, ListingReportForm, ListingReviewForm
from .geocoding import BOSTON_COLLEGE_LATITUDE, BOSTON_COLLEGE_LONGITUDE
from .group_matching import (
    BudgetRange,
    Preferences,
    build_group_options,
)
from .models import Listing, ListingFavorite, ListingReport, ListingReview
from .search_payloads import listing_card_payload, listing_marker_payload
from .selectors import (
    accessible_listing_detail_queryset,
    listing_reviews_queryset,
    marketplace_listings_for_user,
    messageable_listings_for_user,
    searchable_marketplace_listings_for_user,
    with_favorite_state,
)

logger = logging.getLogger(__name__)

LISTINGS_PER_PAGE = 12
ADDRESS_AUTOCOMPLETE_MIN_QUERY_LENGTH = 3
ADDRESS_AUTOCOMPLETE_MAX_RESULTS = 5
ADDRESS_AUTOCOMPLETE_ERROR = {
    "message": "Address suggestions are temporarily unavailable. Try again.",
    "retryable": True,
}
ADDRESS_AUTOCOMPLETE_AUTH_ERROR = {
    "message": "Sign in again to verify addresses.",
    "retryable": False,
    "requires_login": True,
}
ADDRESS_AUTOCOMPLETE_RATE_LIMIT_ERROR = {
    "message": "Too many address lookups. Wait a moment and try again.",
    "retryable": True,
}
ADDRESS_PICKER_DEFAULT_STATUS = "Search and choose a verified address suggestion before publishing."
ADDRESS_PICKER_SAVED_STATUS = "Keeping the saved verified address."
ADDRESS_PICKER_BLOCKED_STATUS = (
    "Verified address search is unavailable right now. Listing authoring is blocked until Geoapify "
    "autocomplete is configured."
)
LISTING_REPORT_RATE_LIMIT_ERROR = "Too many listing reports were sent in a short time. Wait a bit and try again."

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


def _workspace_destination(user):
    if user.has_listing_only_access:
        return "users:posts", "My Listings"
    return "listings:listing_list", "Listings"


def _selected_remove_image_ids(form):
    if not form.is_bound:
        return set()
    return set(form.data.getlist(form.add_prefix("remove_images")))


def _listing_form_context(form, *, is_edit, back_url_name, back_label, listing=None):
    address_config = get_geoapify_autocomplete_config()
    has_saved_verified_address = bool(listing and listing.has_map_coordinates and listing.address)
    initial_address = (listing.address or "") if listing is not None else ""
    address_picker_status_message = ADDRESS_PICKER_DEFAULT_STATUS
    if not address_config["enabled"]:
        address_picker_status_message = ADDRESS_PICKER_BLOCKED_STATUS
    elif has_saved_verified_address:
        address_picker_status_message = ADDRESS_PICKER_SAVED_STATUS

    context = {
        "form": form,
        "form_summary": form.build_summary(),
        "selected_remove_image_ids": _selected_remove_image_ids(form),
        "is_edit": is_edit,
        "back_url_name": back_url_name,
        "back_label": back_label,
        "address_picker_enabled": address_config["enabled"],
        "address_picker_suggestions_url": reverse("listings:address_suggestions") if address_config["enabled"] else "",
        "address_picker_initial_address": initial_address,
        "address_picker_selected_label": initial_address if has_saved_verified_address else "",
        "address_picker_initially_verified": has_saved_verified_address,
        "address_picker_status_message": address_picker_status_message,
    }
    if listing is not None:
        context["listing"] = listing
    return context


def _listing_initial_payload(listings, *, total):
    cards = [listing_card_payload(listing) for listing in listings]
    markers = [listing_marker_payload(listing) for listing in listings if listing.has_map_coordinates]
    return {
        "total": total,
        "markers": markers,
        "cards": cards,
    }


def _listing_map_style_url():
    configured_url = getattr(settings, "LISTING_GEOAPIFY_MAP_STYLE_URL", "").strip()
    if configured_url:
        return configured_url

    api_key = getattr(settings, "LISTING_GEOAPIFY_API_KEY", "").strip()
    if not api_key:
        return ""

    return f"https://maps.geoapify.com/v1/styles/osm-liberty/style.json?apiKey={api_key}"


def _listing_satellite_map_style_url():
    return getattr(settings, "LISTING_MAP_SATELLITE_STYLE_URL", "").strip()


def _autocomplete_results_response(results, *, status=200):
    return JsonResponse({"results": results}, status=status)


def _autocomplete_error_response():
    return JsonResponse({"results": [], "error": ADDRESS_AUTOCOMPLETE_ERROR}, status=503)


def _autocomplete_auth_required_response():
    return JsonResponse({"results": [], "error": ADDRESS_AUTOCOMPLETE_AUTH_ERROR}, status=401)


def _autocomplete_rate_limit_response():
    return JsonResponse({"results": [], "error": ADDRESS_AUTOCOMPLETE_RATE_LIMIT_ERROR}, status=429)


def _consume_address_autocomplete_rate_limit(request):
    return consume_rate_limit(
        scope="listing-address-autocomplete",
        identifier=request_rate_limit_identifier(request),
        limit=getattr(settings, "LISTING_ADDRESS_AUTOCOMPLETE_RATE_LIMIT", 30),
        window_seconds=getattr(settings, "LISTING_ADDRESS_AUTOCOMPLETE_RATE_WINDOW_SECONDS", 60),
    )


def _suggestion_context_label(suggestion):
    locality = ""
    if suggestion["city"] and suggestion["state"]:
        locality = f"{suggestion['city']}, {suggestion['state']}"
    else:
        locality = suggestion["city"] or suggestion["state"]

    if suggestion["postal_code"]:
        locality = f"{locality} {suggestion['postal_code']}".strip()

    if suggestion["country"] and suggestion["country"] != "US":
        if locality:
            return f"{locality}, {suggestion['country']}"
        return suggestion["country"]
    return locality


@require_GET
def address_suggestions(request):
    if not request.user.is_authenticated:
        return _autocomplete_auth_required_response()

    query = (request.GET.get("q") or "").strip()
    if len(query) < ADDRESS_AUTOCOMPLETE_MIN_QUERY_LENGTH:
        return _autocomplete_results_response([])
    if not _consume_address_autocomplete_rate_limit(request):
        return _autocomplete_rate_limit_response()

    config = get_geoapify_autocomplete_config()
    if not config["enabled"]:
        return _autocomplete_error_response()

    try:
        response = requests.get(
            config["url"],
            params={
                "text": query,
                "limit": ADDRESS_AUTOCOMPLETE_MAX_RESULTS,
                "apiKey": config["api_key"],
                "filter": "countrycode:us",
                "bias": f"proximity:{BOSTON_COLLEGE_LONGITUDE},{BOSTON_COLLEGE_LATITUDE}",
            },
            timeout=settings.LISTING_GEOCODER_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        suggestions = normalize_geoapify_suggestions(response.json())
    except (requests.RequestException, TypeError, ValueError) as exc:
        logger.warning("Address autocomplete lookup failed (%s).", type(exc).__name__)
        return _autocomplete_error_response()

    results = []
    for suggestion in suggestions:
        results.append(
            {
                **suggestion,
                "context_label": _suggestion_context_label(suggestion),
                "token": sign_address_selection(suggestion),
            }
        )

    return _autocomplete_results_response(results)


@login_required
def listing_list(request):
    base_queryset = with_favorite_state(marketplace_listings_for_user(request.user), request.user)
    listings, active_filters = apply_listing_filters(base_queryset, request.GET)
    listings_page = get_page(listings, request.GET.get("page"), LISTINGS_PER_PAGE)
    map_requested = settings.LISTING_MAPS_ENABLED
    listing_map_style_url = _listing_map_style_url() if map_requested else ""
    listing_map_satellite_style_url = _listing_satellite_map_style_url() if map_requested else ""
    map_enabled = map_requested and bool(listing_map_style_url)
    satellite_map_enabled = bool(
        map_enabled and listing_map_satellite_style_url and listing_map_satellite_style_url != listing_map_style_url
    )
    listings_page_items = _apply_listing_ui_flags(list(listings_page.object_list), request.user)
    listings_page.object_list = listings_page_items

    context = {
        "listings": listings_page,
        "listings_total": listings_page.paginator.count,
        "pagination_query": preserved_query_suffix(request.GET, "page"),
        "active_filters": active_filters,
        "bedrooms_filter_min": BEDROOMS_FILTER_MIN,
        "price_filter_min": PRICE_FILTER_MIN,
        "price_filter_max": PRICE_FILTER_MAX,
        "lease_type_filters": Listing.LEASE_TYPES,
        "has_listing_only_access": request.user.has_listing_only_access,
        "listing_maps_enabled": map_enabled,
        "listing_maps_unavailable": map_requested and not map_enabled,
    }
    if map_enabled:
        context["listing_initial_payload"] = _listing_initial_payload(
            listings_page_items,
            total=listings_page.paginator.count,
        )
        context["listing_page_initial_state"] = {
            "selected_listing_id": "",
            "query": active_filters["q"],
        }
        context["listing_search_url"] = reverse("listings:search")
        context["listing_map_style_url"] = listing_map_style_url
        context["listing_map_satellite_style_url"] = listing_map_satellite_style_url if satellite_map_enabled else ""
        context["listing_map_satellite_enabled"] = satellite_map_enabled
        context["listing_map_default_lat"] = BOSTON_COLLEGE_LATITUDE
        context["listing_map_default_lng"] = BOSTON_COLLEGE_LONGITUDE
    return render(request, "listings/listing_list.html", context)


def _parse_location_keywords(raw_keywords: str) -> tuple[str, ...]:
    if not raw_keywords:
        return ()
    parts = [keyword.strip() for keyword in raw_keywords.split(",")]
    return tuple(keyword for keyword in parts if keyword)


def _can_favorite_listing(user, listing):
    return (
        getattr(user, "is_authenticated", False)
        and getattr(user, "can_browse_marketplace", False)
        and listing.owner_id != getattr(user, "id", None)
    )


def _can_leave_listing_feedback(user):
    return (
        getattr(user, "is_authenticated", False)
        and getattr(user, "is_student", False)
        and getattr(user, "can_browse_marketplace", False)
    )


def _can_review_listing(user, listing):
    return (
        _can_leave_listing_feedback(user)
        and listing.owner_id != getattr(user, "id", None)
        and listing.is_approved
        and listing.conversations.filter(participant_id=getattr(user, "id", None)).exists()
    )


def _can_report_listing(user, listing):
    return _can_leave_listing_feedback(user) and listing.owner_id != getattr(user, "id", None) and listing.is_approved


def _consume_listing_report_rate_limit(user):
    user_id = getattr(user, "id", None)
    if not user_id:
        return False

    return consume_rate_limit(
        scope="listing-report",
        identifier=str(user_id),
        limit=getattr(settings, "LISTING_REPORT_RATE_LIMIT", 10),
        window_seconds=getattr(settings, "LISTING_REPORT_RATE_WINDOW_SECONDS", 3600),
    )


def _first_form_error(form, *, fallback):
    for errors in form.errors.values():
        if errors:
            return errors[0]
    return fallback


def _apply_listing_ui_flags(listings, user):
    for listing in listings:
        listing.can_favorite = _can_favorite_listing(user, listing)
    return listings


def _split_listing_detail_items(raw_value):
    if not raw_value:
        return []

    parts = []
    for item in re.split(r"[\n,;]+", raw_value):
        cleaned = item.strip()
        if cleaned and cleaned not in parts:
            parts.append(cleaned)
    return parts


def _listing_highlight_items(listing):
    items = [listing.get_lease_type_display(), listing.get_property_type_display()]
    if listing.has_yard:
        items.append("Yard")
    if listing.has_parking:
        items.append("Parking")
    if listing.is_furnished:
        items.append("Furnished")
    if listing.distance_to_campus:
        items.append(f"{listing.distance_to_campus} mi to campus")
    return items


def _clamp(value, minimum, maximum):
    return max(minimum, min(value, maximum))


def _group_match_sleep_schedule_from_bedtime(bedtime):
    if bedtime is None:
        return GROUP_MATCH_DEFAULTS["sleep_schedule"]
    if bedtime >= 23 or bedtime <= 2:
        return "late"
    if 20 <= bedtime <= 22:
        return "early"
    return "balanced"


def _group_match_social_from_profile(profile):
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


def _group_match_size_defaults(social_preference):
    if social_preference >= 4:
        return 4, 6
    if social_preference <= 2:
        return 2, 4
    return 3, 5


def _group_match_initial_data(user):
    defaults = GROUP_MATCH_DEFAULTS.copy()
    profile = getattr(user, "student_profile", None)
    if profile is None:
        return defaults

    if profile.messy_level is not None:
        defaults["cleanliness"] = profile.messy_level
    defaults["social"] = _group_match_social_from_profile(profile)
    defaults["sleep_schedule"] = _group_match_sleep_schedule_from_bedtime(profile.bedtime)
    defaults["desired_group_min"], defaults["desired_group_max"] = _group_match_size_defaults(defaults["social"])
    return defaults


def _group_match_preferences(raw_data):
    location_keywords = _parse_location_keywords(raw_data.get("location_keywords", ""))
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


def _group_match_option_url(*, effective_data, option_id):
    params = {
        field_name: str(effective_data[field_name])
        for field_name in GROUP_MATCH_QUERY_FIELDS
        if field_name in effective_data and effective_data[field_name] not in ("", None)
    }
    params["group"] = option_id
    return f"{reverse('listings:group_match')}?{urlencode(params)}"


def _group_match_roommate_limit(additional_roommates_needed):
    return min(max(additional_roommates_needed, 3), 6)


def _group_match_roommate_matches(user):
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
                "profile_url": f"{reverse('users:public_profile', args=[match['user'].id])}",
                "message_url": reverse("communications:detail", args=[conversation.id])
                if conversation is not None
                else f"{reverse('users:public_profile', args=[match['user'].id])}#message-user",
                "message_label": "Open chat" if conversation is not None else "Message",
            }
        )

    return decorated_matches


def _group_match_listings_by_size(user, *, unit_size, preferences):
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


@login_required
@require_GET
def group_match(request):
    if not request.user.can_browse_marketplace:
        return HttpResponseForbidden("Verified student access is required to use group matching.")

    initial_data = _group_match_initial_data(request.user)
    form = GroupMatchPreferencesForm(request.GET or None, initial=initial_data)
    group_options = []
    selected_group_id = ""
    selected_group_option = None
    location_keywords = ()
    effective_data = initial_data
    form_is_valid = not bool(request.GET)
    if request.GET:
        form_is_valid = form.is_valid()
        if form_is_valid:
            effective_data = form.cleaned_data

    if form_is_valid:
        preferences, location_keywords = _group_match_preferences(effective_data)
        listings_by_size = _group_match_listings_by_size(
            request.user,
            unit_size=int(effective_data["unit_size"]),
            preferences=preferences,
        )
        group_options = build_group_options(
            base_unit_size=int(effective_data["unit_size"]),
            preferences=preferences,
            listings_by_size=listings_by_size,
            max_options=6,
        )

    roommate_matches = _group_match_roommate_matches(request.user)

    listing_limit = 6
    for option in group_options:
        option.listings = _apply_listing_ui_flags(list(option.listings[:listing_limit]), request.user)
        option.roommate_matches = roommate_matches[: _group_match_roommate_limit(option.additional_roommates_needed)]
        option.select_url = _group_match_option_url(effective_data=effective_data, option_id=option.option_id)

    selected_group_id = request.GET.get("group") or (group_options[0].option_id if group_options else "")
    if selected_group_id and not any(option.option_id == selected_group_id for option in group_options):
        selected_group_id = group_options[0].option_id if group_options else ""
    selected_group_option = next((option for option in group_options if option.option_id == selected_group_id), None)

    context = {
        "form": form,
        "group_options": group_options,
        "selected_group_id": selected_group_id,
        "selected_group_option": selected_group_option,
        "location_keywords": location_keywords,
        "group_match_uses_profile_defaults": not bool(request.GET) and bool(request.user.profile_completed_at),
        "group_match_has_profile": bool(request.user.profile_completed_at),
        "group_match_current_group_size": int(effective_data["unit_size"]),
        "group_match_roommate_matches_total": len(roommate_matches),
        "group_match_roommate_matches": roommate_matches[:6],
        "group_match_total_matches": sum(option.listings_count for option in group_options),
        "group_match_sizes_with_inventory": sum(1 for option in group_options if option.listings_count),
    }
    return render(request, "listings/group_match.html", context)


@login_required
@require_GET
def listing_search(request):
    base_queryset = with_favorite_state(searchable_marketplace_listings_for_user(request.user), request.user)
    listings, _ = apply_listing_filters(base_queryset, request.GET, viewport_required=True)
    listings = _apply_listing_ui_flags(list(listings), request.user)
    return JsonResponse(
        {
            "total": len(listings),
            "markers": [listing_marker_payload(listing) for listing in listings],
            "cards": [listing_card_payload(listing) for listing in listings],
        }
    )


@login_required
def listing_detail(request, pk):
    listing_queryset = with_favorite_state(accessible_listing_detail_queryset(request.user), request.user)
    listing = get_object_or_404(listing_queryset, pk=pk)
    listing.can_favorite = _can_favorite_listing(request.user, listing)
    listing_images = list(listing.images.all())
    message_form = None
    existing_conversation = None
    owner_conversations = None
    back_url_name, back_label = _workspace_destination(request.user)
    show_owner_conversations = listing.owner_id == request.user.id
    can_review_listing = _can_review_listing(request.user, listing)
    can_report_listing = _can_report_listing(request.user, listing)
    can_message_listing = (
        request.user.can_start_listing_conversations
        and listing.owner_id != request.user.id
        and listing.is_publicly_active
    )
    review_requires_contact = (
        _can_leave_listing_feedback(request.user)
        and listing.owner_id != request.user.id
        and listing.is_approved
        and not can_review_listing
    )
    listing_reviews = list(listing_reviews_queryset(listing))
    existing_review = next((review for review in listing_reviews if review.author_id == request.user.id), None)
    review_form = ListingReviewForm(instance=existing_review) if can_review_listing else None
    active_listing_report = None
    report_form = None

    if can_report_listing:
        active_listing_report = (
            ListingReport.objects.filter(
                listing=listing,
                reporter=request.user,
                status__in=[ListingReport.STATUS_OPEN, ListingReport.STATUS_IN_REVIEW],
            )
            .order_by("-created_at")
            .first()
        )
        if active_listing_report is None:
            report_form = ListingReportForm()

    if request.user.can_start_listing_conversations and listing.owner_id != request.user.id:
        existing_conversation = (
            ListingConversation.objects.visible_to(request.user).with_related().filter(listing=listing).first()
        )
        if existing_conversation:
            existing_conversation.ui_has_unread = existing_conversation.has_unread_for(request.user)
        if can_message_listing:
            message_form = ConversationMessageForm()

    if show_owner_conversations:
        owner_conversations = list(
            ListingConversation.objects.visible_to(request.user)
            .with_related()
            .filter(listing=listing)
            .order_by("-last_message_at", "-created_at")[:8]
        )
        for conversation in owner_conversations:
            conversation.ui_counterparty_name = conversation.participant.display_name
            conversation.ui_has_unread = conversation.has_unread_for(request.user)

    context = {
        "listing": listing,
        "listing_images": listing_images,
        "is_favorited": bool(getattr(listing, "is_favorited", False)),
        "average_rating": getattr(listing, "average_rating", None),
        "review_count": int(getattr(listing, "review_count", 0) or 0),
        "listing_reviews": listing_reviews,
        "existing_review": existing_review,
        "review_form": review_form,
        "report_form": report_form,
        "active_listing_report": active_listing_report,
        "message_form": message_form,
        "existing_conversation": existing_conversation,
        "can_message_listing": can_message_listing,
        "owner_conversations": owner_conversations,
        "show_owner_conversations": show_owner_conversations,
        "back_url_name": back_url_name,
        "back_label": back_label,
        "can_favorite_listing": listing.can_favorite,
        "can_review_listing": can_review_listing,
        "can_report_listing": can_report_listing,
        "review_requires_contact": review_requires_contact,
        "listing_highlight_items": _listing_highlight_items(listing),
        "amenity_items": _split_listing_detail_items(listing.amenities),
        "utility_items": _split_listing_detail_items(listing.utilities_included),
        "security_feature_items": _split_listing_detail_items(listing.security_features),
    }
    return render(request, "listings/listing_detail.html", context)


@login_required
@require_POST
def submit_listing_review(request, pk):
    listing = get_object_or_404(accessible_listing_detail_queryset(request.user), pk=pk)
    if not _can_review_listing(request.user, listing):
        return HttpResponseForbidden("Only student users with prior listing contact can review approved listings.")

    review = ListingReview.objects.filter(listing=listing, author=request.user).first()
    form = ListingReviewForm(request.POST, instance=review)
    if form.is_valid():
        review = form.save(commit=False)
        review.listing = listing
        review.author = request.user
        review.save()
        messages.success(request, "Your rating has been saved.")
    else:
        messages.error(request, _first_form_error(form, fallback="Add a rating before saving your review."))

    return redirect(f"{reverse('listings:detail', args=[listing.pk])}#community")


@login_required
@require_POST
def report_listing(request, pk):
    listing = get_object_or_404(accessible_listing_detail_queryset(request.user), pk=pk)
    if not _can_report_listing(request.user, listing):
        return HttpResponseForbidden("Only student users can report approved listings they do not own.")
    if not _consume_listing_report_rate_limit(request.user):
        messages.error(request, LISTING_REPORT_RATE_LIMIT_ERROR)
        return redirect(f"{reverse('listings:detail', args=[listing.pk])}#community")

    existing_report = ListingReport.objects.filter(
        listing=listing,
        reporter=request.user,
        status__in=[ListingReport.STATUS_OPEN, ListingReport.STATUS_IN_REVIEW],
    ).first()
    if existing_report is not None:
        messages.info(request, "You already have an active report on this listing.")
        return redirect(f"{reverse('listings:detail', args=[listing.pk])}#community")

    form = ListingReportForm(request.POST)
    if form.is_valid():
        report = form.save(commit=False)
        report.listing = listing
        report.reporter = request.user
        report.save()
        messages.success(request, "The listing has been reported for admin review.")
    else:
        messages.error(
            request, _first_form_error(form, fallback="Add enough detail for the admin team to review this report.")
        )

    return redirect(f"{reverse('listings:detail', args=[listing.pk])}#community")


@login_required
@require_POST
def toggle_favorite(request, pk):
    listing = get_object_or_404(accessible_listing_detail_queryset(request.user), pk=pk)
    if not _can_favorite_listing(request.user, listing):
        return HttpResponseForbidden("You can only save listings posted by other marketplace users.")
    favorite, created = ListingFavorite.objects.get_or_create(user=request.user, listing=listing)
    if not created:
        favorite.delete()

    next_url = safe_next_url(request, request.POST.get("next"), reverse("listings:detail", args=[listing.pk]))
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"is_favorited": created})
    return redirect(next_url)


@login_required
@require_POST
def message_listing(request, pk):
    if not request.user.can_start_listing_conversations:
        return HttpResponseForbidden("Verified student access is required to message about listings.")

    listing = get_object_or_404(messageable_listings_for_user(request.user), pk=pk)
    if listing.owner_id == request.user.id:
        messages.error(request, "You cannot message yourself about your own listing.")
        return redirect("listings:detail", pk=listing.pk)
    if not consume_message_send_rate_limit(request.user):
        messages.error(request, MESSAGE_SEND_RATE_LIMIT_ERROR)
        return redirect("listings:detail", pk=listing.pk)

    form = ConversationMessageForm(request.POST)
    if form.is_valid():
        try:
            conversation, _, created = start_listing_conversation(listing, request.user, form.cleaned_data["body"])
        except ValidationError as exc:
            messages.error(request, validation_message(exc, "Enter a message before sending."))
        else:
            messages.success(request, "Conversation started." if created else "Message sent.")
            return redirect("communications:detail", conversation_id=conversation.pk)
    else:
        messages.error(request, "Enter a message before sending.")

    return redirect("listings:detail", pk=listing.pk)


@login_required
def create_listing(request):
    if request.method == "POST":
        form = ListingForm(request.POST, request.FILES)
        listing = handle_listing_form_submission(form=form, owner=request.user)
        if listing is not None:
            messages.success(request, "Listing submitted for review.")
            return redirect("listings:detail", pk=listing.pk)
    else:
        form = ListingForm()

    back_url_name, back_label = _workspace_destination(request.user)
    return render(
        request,
        "listings/listing_form.html",
        _listing_form_context(form, is_edit=False, back_url_name=back_url_name, back_label=back_label),
    )


@login_required
def edit_listing(request, pk):
    listing = get_object_or_404(Listing, pk=pk, owner=request.user)
    if request.method == "POST":
        form = ListingForm(request.POST, request.FILES, instance=listing)
        listing = handle_listing_form_submission(form=form, owner=request.user)
        if listing is not None:
            messages.success(request, "Listing updated and re-submitted for review.")
            return redirect("listings:detail", pk=listing.pk)
    else:
        form = ListingForm(instance=listing)
    return render(
        request,
        "listings/listing_form.html",
        _listing_form_context(
            form,
            is_edit=True,
            listing=listing,
            back_url_name="users:posts",
            back_label="My Listings",
        ),
    )


@login_required
@require_POST
def delete_listing(request, pk):
    listing = get_object_or_404(Listing, pk=pk, owner=request.user)
    listing.delete()
    return redirect("users:posts")
