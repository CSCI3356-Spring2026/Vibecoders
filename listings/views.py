from decimal import Decimal

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
from communications.services import (
    MESSAGE_SEND_RATE_LIMIT_ERROR,
    consume_message_send_rate_limit,
    start_listing_conversation,
)
from core.rate_limits import consume_rate_limit, request_rate_limit_identifier
from core.utils import get_page, preserved_query_suffix, safe_next_url

from .address_provider import get_geoapify_autocomplete_config, normalize_geoapify_suggestions
from .address_signing import sign_address_selection
from .filtering import MAX_PRICE_FILTERS, MOVE_IN_FILTERS, apply_listing_filters
from .form_services import handle_listing_form_submission, validation_message
from .forms import GroupMatchPreferencesForm, ListingForm
from .geocoding import BOSTON_COLLEGE_LATITUDE, BOSTON_COLLEGE_LONGITUDE
from .group_matching import (
    BudgetRange,
    Preferences,
    Unit,
    build_group_options,
    default_base_members,
    sample_candidate_units,
)
from .models import Listing, ListingFavorite
from .search_payloads import listing_card_payload, listing_marker_payload
from .selectors import (
    accessible_listing_detail_queryset,
    marketplace_listings_for_user,
    messageable_listings_for_user,
    searchable_marketplace_listings_for_user,
    with_favorite_state,
)

LISTINGS_PER_PAGE = 12
ADDRESS_AUTOCOMPLETE_MIN_QUERY_LENGTH = 3
ADDRESS_AUTOCOMPLETE_MAX_RESULTS = 5
ADDRESS_AUTOCOMPLETE_ERROR = {
    "message": "Address suggestions are temporarily unavailable. Try again.",
    "retryable": True,
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

GROUP_MATCH_DEFAULTS = {
    "unit_size": 2,
    "budget_min": 1000,
    "budget_max": 1600,
    "cleanliness": 4,
    "social": 3,
    "sleep_schedule": "balanced",
    "desired_group_min": 4,
    "desired_group_max": 6,
    "location_keywords": "Allston, Brighton",
}


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


def _autocomplete_results_response(results, *, status=200):
    return JsonResponse({"results": results}, status=status)


def _autocomplete_error_response():
    return JsonResponse({"results": [], "error": ADDRESS_AUTOCOMPLETE_ERROR}, status=503)


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


@login_required
@require_GET
def address_suggestions(request):
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
    except Exception:
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
    map_enabled = map_requested and bool(listing_map_style_url)
    listings_page_items = list(listings_page.object_list)

    context = {
        "listings": listings_page,
        "listings_total": listings_page.paginator.count,
        "pagination_query": preserved_query_suffix(request.GET, "page"),
        "active_filters": active_filters,
        "max_price_filters": MAX_PRICE_FILTERS,
        "lease_type_filters": Listing.LEASE_TYPES,
        "move_in_filters": MOVE_IN_FILTERS,
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
        context["listing_map_default_lat"] = BOSTON_COLLEGE_LATITUDE
        context["listing_map_default_lng"] = BOSTON_COLLEGE_LONGITUDE
    return render(request, "listings/listing_list.html", context)


def _parse_location_keywords(raw_keywords: str) -> tuple[str, ...]:
    if not raw_keywords:
        return ()
    parts = [keyword.strip() for keyword in raw_keywords.split(",")]
    return tuple(keyword for keyword in parts if keyword)


def _compatible_listings_for_group(user, *, group_size, budget_range, location_keywords):
    queryset = with_favorite_state(marketplace_listings_for_user(user), user).filter(rooms=group_size)
    price_per_person = ExpressionWrapper(
        F("price") / F("rooms"),
        output_field=DecimalField(max_digits=10, decimal_places=2),
    )
    queryset = queryset.annotate(price_per_person=price_per_person)
    if not budget_range.is_valid:
        return queryset.none()
    queryset = queryset.filter(
        price_per_person__gte=budget_range.minimum,
        price_per_person__lte=budget_range.maximum,
    )
    if location_keywords:
        location_query = Q()
        for keyword in location_keywords:
            location_query |= Q(address__icontains=keyword) | Q(title__icontains=keyword)
        queryset = queryset.filter(location_query)
    return queryset


@login_required
@require_GET
def group_match(request):
    show_form = not bool(request.GET) or request.GET.get("edit") == "1"
    form = GroupMatchPreferencesForm(request.GET or None, initial=GROUP_MATCH_DEFAULTS)
    if show_form:
        data = GROUP_MATCH_DEFAULTS
    elif form.is_valid():
        data = form.cleaned_data
    else:
        data = GROUP_MATCH_DEFAULTS

    location_keywords = _parse_location_keywords(data.get("location_keywords", ""))
    base_preferences = Preferences(
        budget=BudgetRange(Decimal(str(data["budget_min"])), Decimal(str(data["budget_max"]))),
        cleanliness=int(data["cleanliness"]),
        social=int(data["social"]),
        sleep_schedule=data["sleep_schedule"],
        desired_group_min=int(data["desired_group_min"]),
        desired_group_max=int(data["desired_group_max"]),
        location_keywords=location_keywords,
    )
    base_unit = Unit(
        unit_id="you",
        label="You",
        size=int(data["unit_size"]),
        members=default_base_members(int(data["unit_size"])),
        preferences=base_preferences,
    )

    candidate_units = sample_candidate_units()
    group_options = build_group_options(base_unit, candidate_units, max_options=6)

    selected_group_id = request.GET.get("group") or (group_options[0].option_id if group_options else "")
    if selected_group_id and not any(option.option_id == selected_group_id for option in group_options):
        selected_group_id = group_options[0].option_id if group_options else ""
    listing_limit = 6
    for option in group_options:
        if location_keywords:
            option_keywords = location_keywords
        else:
            option_keywords = tuple(
                sorted({keyword for unit in option.units for keyword in unit.preferences.location_keywords})
            )
        listings_queryset = _compatible_listings_for_group(
            request.user,
            group_size=option.group_size,
            budget_range=option.budget_range,
            location_keywords=option_keywords,
        )
        option.listings_count = listings_queryset.count()
        option.listings = list(listings_queryset[:listing_limit])

    context = {
        "form": form,
        "group_options": group_options,
        "selected_group_id": selected_group_id,
        "location_keywords": location_keywords,
        "show_form": show_form,
    }
    return render(request, "listings/group_match.html", context)


@login_required
@require_GET
def listing_search(request):
    base_queryset = with_favorite_state(searchable_marketplace_listings_for_user(request.user), request.user)
    listings, _ = apply_listing_filters(base_queryset, request.GET, viewport_required=True)
    listings = list(listings)
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
    listing_images = list(listing.images.all())
    message_form = None
    existing_conversation = None
    owner_conversations = None
    back_url_name, back_label = _workspace_destination(request.user)
    show_owner_conversations = listing.owner_id == request.user.id
    can_message_listing = (
        request.user.can_start_listing_conversations
        and listing.owner_id != request.user.id
        and listing.is_publicly_active
    )

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
        "message_form": message_form,
        "existing_conversation": existing_conversation,
        "can_message_listing": can_message_listing,
        "owner_conversations": owner_conversations,
        "show_owner_conversations": show_owner_conversations,
        "back_url_name": back_url_name,
        "back_label": back_label,
    }
    return render(request, "listings/listing_detail.html", context)


@login_required
@require_POST
def toggle_favorite(request, pk):
    listing = get_object_or_404(accessible_listing_detail_queryset(request.user), pk=pk)
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
            messages.success(request, "Listing created.")
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
            messages.success(request, "Listing updated.")
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
