import logging
import re

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404, HttpResponseForbidden, JsonResponse
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
from users.compatibility import (
    compatibility_highlights,
    compute_compatibility,
    compute_group_compatibility,
    group_compatibility_highlights,
)
from users.models import Role, RoommateGroupInvite
from users.selectors import active_roommate_group_for_user, roommate_group_memberships, roommate_group_profiles_for_user

from .address_provider import get_geoapify_autocomplete_config, normalize_geoapify_suggestions
from .address_signing import sign_address_selection
from .commute import commute_payload_for_listing, listing_distance_to_bc_miles
from .filtering import BEDROOMS_FILTER_MIN, PRICE_FILTER_MAX, PRICE_FILTER_MIN, apply_listing_filters
from .form_services import handle_listing_form_submission, validation_message
from .forms import (
    ListingForm,
    ListingReportForm,
    ListingReviewForm,
    RoommateGroupForm,
    RoommatePostFilterForm,
    RoommatePostForm,
)
from .geocoding import BOSTON_COLLEGE_LATITUDE, BOSTON_COLLEGE_LONGITUDE
from .models import (
    Listing,
    ListingFavorite,
    ListingReport,
    ListingReview,
    RoommateGroupMembership,
    RoommatePost,
)
from .roommate_post_service import decorate_roommate_posts_for_user
from .search_payloads import listing_card_payload, listing_marker_payload
from .selectors import (
    accessible_listing_detail_queryset,
    filtered_roommate_posts_queryset,
    listing_reviews_queryset,
    marketplace_listings_for_user,
    messageable_listings_for_user,
    open_listings_matching_roommate_post,
    roommate_group_for_user,
    roommate_group_post_for_user,
    roommate_post_for_user,
    searchable_marketplace_listings_for_user,
    with_favorite_state,
)

logger = logging.getLogger(__name__)

LISTINGS_PER_PAGE = 12
ROOMMATE_POSTS_PER_PAGE = 12
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


def _listing_commute_map_payload():
    if not settings.LISTING_MAPS_ENABLED:
        return None

    api_key = getattr(settings, "LISTING_GEOAPIFY_API_KEY", "").strip()
    style_url = _listing_map_style_url()
    if not api_key or not style_url:
        return None

    return {
        "api_key": api_key,
        "routing_url": "https://api.geoapify.com/v1/routing",
        "style_url": style_url,
    }


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
    distance_to_campus = listing_distance_to_bc_miles(listing)
    if distance_to_campus is not None:
        items.append(f"{distance_to_campus:.1f} mi to campus")
    return items


def _first_form_error(form, default_message):
    if form.non_field_errors():
        return form.non_field_errors()[0]
    for field_errors in form.errors.values():
        if field_errors:
            return field_errors[0]
    return default_message


def _roommate_post_board_context(request, *, filter_form=None, post_form=None):
    current_post = roommate_post_for_user(request.user)
    current_group = roommate_group_for_user(request.user)
    current_group_post = roommate_group_post_for_user(request.user)
    group_profiles = roommate_group_profiles_for_user(request.user)

    if filter_form is None:
        filter_form = RoommatePostFilterForm(request.GET or None)

    filter_data = {}
    if not filter_form.is_bound:
        filter_data = {}
    else:
        filter_form.is_valid()
        filter_data = filter_form.cleaned_data

    roommate_posts = filtered_roommate_posts_queryset(
        request.user,
        query=filter_data.get("q", ""),
        housing_status=filter_data.get("housing_status", ""),
        max_budget=filter_data.get("max_budget"),
        move_in_by=filter_data.get("move_in_by"),
        open_spots_min=filter_data.get("open_spots_min"),
        people_in_group=filter_data.get("people_in_group"),
    )
    roommate_posts = decorate_roommate_posts_for_user(request.user, roommate_posts, group_profiles=group_profiles)
    selected_post = None
    matched_listings = []
    matched_listings_total = 0
    selected_post_id = (request.GET.get("group") or "").strip()
    if selected_post_id.isdigit():
        selected_post = RoommatePost.objects.active().with_related().filter(pk=int(selected_post_id)).first()
        if selected_post is not None:
            matched_queryset = open_listings_matching_roommate_post(request.user, selected_post)
            matched_listings_total = matched_queryset.count()
            matched_listings = list(matched_queryset[:6])
            _apply_listing_ui_flags(matched_listings, request.user)

    group_query_suffix = preserved_query_suffix(request.GET, "page", "group")
    for post in roommate_posts:
        post.ui_listing_match_count = open_listings_matching_roommate_post(request.user, post).count()
        post.ui_match_url = f"{reverse('listings:group_match')}?group={post.id}{group_query_suffix}"
        post.ui_is_selected = selected_post is not None and post.id == selected_post.id
    roommate_posts_page = get_page(roommate_posts, request.GET.get("page"), ROOMMATE_POSTS_PER_PAGE)

    if post_form is None:
        post_form = RoommatePostForm(instance=current_post, user=request.user)
    group_form = RoommateGroupForm(instance=current_group, user=request.user)
    group_post_form = RoommatePostForm(instance=current_group_post, user=request.user, group=current_group)

    return {
        "roommate_group_form": group_form,
        "roommate_post_form": post_form,
        "roommate_group_post_form": group_post_form,
        "roommate_post_filter_form": filter_form,
        "current_roommate_post": current_post,
        "current_roommate_group": current_group,
        "current_group_roommate_post": current_group_post,
        "group_member_count": len(group_profiles),
        "selected_roommate_post": selected_post,
        "selected_roommate_post_listings": matched_listings,
        "selected_roommate_post_listings_total": matched_listings_total,
        "roommate_posts": roommate_posts_page,
        "roommate_posts_total": len(roommate_posts),
        "pagination_query": preserved_query_suffix(request.GET, "page"),
        "can_manage_roommate_post": request.user.is_student,
        "can_message_roommate_posts": request.user.can_use_roommate_matching,
        "roommate_filters_active": any(filter_data.get(field_name) for field_name in filter_data),
    }


def _posts_tab_context(request):
    filter_form = RoommatePostFilterForm(request.GET or None)
    filter_data = {}
    if filter_form.is_bound:
        filter_form.is_valid()
        filter_data = filter_form.cleaned_data

    group_profiles = roommate_group_profiles_for_user(request.user)
    roommate_posts = filtered_roommate_posts_queryset(
        request.user,
        query=filter_data.get("q", ""),
        housing_status=filter_data.get("housing_status", ""),
        max_budget=filter_data.get("max_budget"),
        move_in_by=filter_data.get("move_in_by"),
        open_spots_min=filter_data.get("open_spots_min"),
        people_in_group=filter_data.get("people_in_group"),
    )
    roommate_posts = decorate_roommate_posts_for_user(request.user, roommate_posts, group_profiles=group_profiles)
    roommate_posts_page = get_page(roommate_posts, request.GET.get("page"), ROOMMATE_POSTS_PER_PAGE)
    return {
        "roommate_post_filter_form": filter_form,
        "roommate_posts": roommate_posts_page,
        "roommate_posts_total": len(roommate_posts),
        "pagination_query": preserved_query_suffix(request.GET, "page"),
        "can_message_roommate_posts": request.user.can_use_roommate_matching,
        "roommate_filters_active": any(filter_data.get(f) for f in filter_data),
    }


def _people_tab_context(request):
    User = get_user_model()
    query = request.GET.get("q", "").strip()
    gender_filter = request.GET.get("gender", "").strip()
    smoke_filter = request.GET.get("smoke", "").strip()
    pets_filter = request.GET.get("pets", "").strip()
    min_score_raw = request.GET.get("min_score", "").strip()
    min_score = int(min_score_raw) if min_score_raw.isdigit() else None

    my_profile = getattr(request.user, "student_profile", None)
    group_profiles = roommate_group_profiles_for_user(request.user)

    students_qs = (
        User.objects.filter(role=Role.STUDENT, is_active=True, profile_completed_at__isnull=False)
        .exclude(id=request.user.id)
        .select_related("student_profile")
    )
    if query:
        students_qs = students_qs.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(student_profile__preferred_name__icontains=query)
        )
    if gender_filter:
        students_qs = students_qs.filter(student_profile__gender=gender_filter)
    if smoke_filter == "yes":
        students_qs = students_qs.filter(student_profile__smoke=True)
    elif smoke_filter == "no":
        students_qs = students_qs.filter(student_profile__smoke=False)
    if pets_filter == "yes":
        students_qs = students_qs.filter(student_profile__pets=True)
    elif pets_filter == "no":
        students_qs = students_qs.filter(student_profile__pets=False)

    results = []
    for student in students_qs[:80]:
        their_profile = getattr(student, "student_profile", None)
        if group_profiles:
            score = compute_group_compatibility(group_profiles, their_profile) if their_profile else None
            highlights = group_compatibility_highlights(group_profiles, their_profile) if their_profile else []
        else:
            score = compute_compatibility(my_profile, their_profile) if my_profile and their_profile else None
            highlights = compatibility_highlights(my_profile, their_profile)
        if min_score is not None and (score is None or score < min_score):
            continue
        results.append({"user": student, "profile": their_profile, "score": score, "highlights": highlights})
    results.sort(key=lambda r: r["score"] if r["score"] is not None else -1, reverse=True)

    if request.user.can_use_roommate_matching and results:
        existing_convos = direct_conversations_by_counterparty(request.user, [r["user"] for r in results])
    else:
        existing_convos = {}
    existing_invites = RoommateGroupInvite.objects.filter(
        inviter=request.user,
        invitee__in=[r["user"] for r in results],
        status__in=[RoommateGroupInvite.STATUS_PENDING_APPROVAL, RoommateGroupInvite.STATUS_PENDING_INVITEE],
    ).values_list("invitee_id", "status")
    invite_status_map = {invitee_id: status for invitee_id, status in existing_invites}

    # Determine if viewer is a group lead and get existing member IDs
    led_group = roommate_group_for_user(request.user)
    is_group_lead = led_group is not None
    existing_member_ids = (
        set(RoommateGroupMembership.objects.filter(group=led_group).values_list("user_id", flat=True))
        if led_group
        else set()
    )

    for result in results:
        result["existing_convo"] = existing_convos.get(result["user"].id)
        result["invite_status"] = invite_status_map.get(result["user"].id)
        result["already_in_group"] = result["user"].id in existing_member_ids

    return {
        "people_results": results,
        "has_my_profile": my_profile is not None,
        "can_message": request.user.can_use_roommate_matching,
        "is_group_lead": is_group_lead,
        "people_gender_filter": gender_filter,
        "people_smoke_filter": smoke_filter,
        "people_pets_filter": pets_filter,
        "people_min_score": min_score_raw,
        "people_filters_active": any([query, gender_filter, smoke_filter, pets_filter, min_score is not None]),
    }


def _mypost_tab_context(
    request, *, create_form=None, edit_forms_by_pk=None, edit_error_pk=None, show_create_modal=False
):
    personal_post = roommate_post_for_user(request.user)
    led_group = roommate_group_for_user(request.user)
    group_post = roommate_group_post_for_user(request.user)
    # Get any group the user belongs to (lead or member)
    any_group = led_group or active_roommate_group_for_user(request.user)
    all_posts = [p for p in [personal_post, group_post] if p is not None]
    my_posts_with_forms = []
    for post in all_posts:
        if edit_forms_by_pk and post.pk in edit_forms_by_pk:
            form = edit_forms_by_pk[post.pk]
        else:
            grp = led_group if post.group_id else None
            form = RoommatePostForm(instance=post, user=request.user, group=grp)
        my_posts_with_forms.append((post, form))
    if create_form is None:
        create_form = RoommatePostForm(user=request.user)
    group_members = list(roommate_group_memberships(any_group)) if any_group else []
    return {
        "my_posts_with_forms": my_posts_with_forms,
        "roommate_post_create_form": create_form,
        "show_create_modal": show_create_modal,
        "edit_error_pk": edit_error_pk,
        "display_group": any_group,
        "group_members": group_members,
        "is_group_lead": any_group is not None and any_group.lead_id == request.user.id,
    }


@login_required
@require_GET
def roommates_hub(request):
    if not request.user.is_student:
        raise Http404

    tab = request.GET.get("tab", "posts")
    if tab not in ("posts", "people", "mypost"):
        tab = "posts"

    personal_post = roommate_post_for_user(request.user)
    has_any_post = personal_post is not None or roommate_group_post_for_user(request.user) is not None
    context = {
        "tab": tab,
        "can_manage_roommate_post": True,
        "current_roommate_post": personal_post,
        "has_any_roommate_post": has_any_post,
        # Always include the create form — the create dialog is outside the tab blocks
        "roommate_post_create_form": RoommatePostForm(user=request.user),
        "show_create_modal": False,
        "edit_error_pk": None,
        "my_posts_with_forms": [],
    }
    if tab == "posts":
        context.update(_posts_tab_context(request))
    elif tab == "people":
        context.update(_people_tab_context(request))
    else:
        context.update(_mypost_tab_context(request))
    return render(request, "listings/roommates_hub.html", context)


@login_required
@require_GET
def group_match(request):
    if not request.user.is_student:
        return HttpResponseForbidden("Student access is required to use roommate posts.")

    return render(request, "listings/group_match.html", _roommate_post_board_context(request))


@login_required
@require_POST
def save_roommate_post(request):
    if not request.user.is_student:
        return HttpResponseForbidden("Student access is required to use roommate posts.")

    current_post = roommate_post_for_user(request.user)
    was_active = bool(current_post and current_post.is_active)
    form = RoommatePostForm(request.POST, instance=current_post, user=request.user)
    if form.is_valid():
        form.save()
        if current_post is None:
            messages.success(request, "Roommate post published.")
        elif was_active:
            messages.success(request, "Roommate post updated.")
        else:
            messages.success(request, "Roommate post reactivated.")
        return redirect(reverse("listings:roommates_hub") + "?tab=mypost")

    messages.error(request, _first_form_error(form, "Review the highlighted roommate post fields and try again."))
    context = {
        "tab": "mypost",
        "can_manage_roommate_post": True,
        "current_roommate_post": current_post,
    }
    context.update(_mypost_tab_context(request, create_form=form, show_create_modal=True))
    return render(request, "listings/roommates_hub.html", context)


@login_required
@require_POST
def save_roommate_group(request):
    if not request.user.is_student:
        return HttpResponseForbidden("Student access is required to use roommate posts.")

    current_group = roommate_group_for_user(request.user)
    form = RoommateGroupForm(request.POST, instance=current_group, user=request.user)
    if form.is_valid():
        group = form.save()
        group_post = roommate_group_post_for_user(request.user)
        if group_post is not None:
            group_post.current_group_size = group.member_count
            group_post.save(update_fields=["current_group_size", "updated_at"])
        messages.success(request, "Roommate group saved.")
        return redirect(reverse("listings:roommates_hub") + "?tab=mypost")

    messages.error(request, _first_form_error(form, "Review the highlighted roommate group fields and try again."))
    return redirect(reverse("listings:roommates_hub") + "?tab=mypost")


@login_required
@require_POST
def save_group_roommate_post(request):
    if not request.user.is_student:
        return HttpResponseForbidden("Student access is required to use roommate posts.")

    current_group = roommate_group_for_user(request.user)
    if current_group is None:
        messages.error(request, "Create your roommate group before publishing a group post.")
        return redirect(reverse("listings:roommates_hub") + "?tab=mypost")

    current_post = roommate_group_post_for_user(request.user)
    was_active = bool(current_post and current_post.is_active)
    form = RoommatePostForm(request.POST, instance=current_post, user=request.user, group=current_group)
    if form.is_valid():
        form.save()
        if current_post is None:
            messages.success(request, "Group roommate post published.")
        elif was_active:
            messages.success(request, "Group roommate post updated.")
        else:
            messages.success(request, "Group roommate post reactivated.")
        return redirect(reverse("listings:roommates_hub") + "?tab=mypost")

    messages.error(request, _first_form_error(form, "Review the highlighted group post fields and try again."))
    return redirect(reverse("listings:roommates_hub") + "?tab=mypost")


@login_required
@require_POST
def deactivate_roommate_post(request):
    if not request.user.is_student:
        return HttpResponseForbidden("Student access is required to use roommate posts.")

    roommate_post = roommate_post_for_user(request.user)
    if roommate_post is not None and roommate_post.is_active:
        roommate_post.is_active = False
        roommate_post.save(update_fields=["is_active", "updated_at"])
        messages.success(request, "Roommate post paused.")
    return redirect(reverse("listings:roommates_hub") + "?tab=mypost")


@login_required
@require_POST
def deactivate_group_roommate_post(request):
    if not request.user.is_student:
        return HttpResponseForbidden("Student access is required to use roommate posts.")

    roommate_post = roommate_group_post_for_user(request.user)
    if roommate_post is not None and roommate_post.is_active:
        roommate_post.is_active = False
        roommate_post.save(update_fields=["is_active", "updated_at"])
        messages.success(request, "Group roommate post paused.")
    return redirect(reverse("listings:roommates_hub") + "?tab=mypost")


@login_required
@require_POST
def edit_roommate_post(request, pk):
    if not request.user.is_student:
        return HttpResponseForbidden("Student access is required.")

    post = get_object_or_404(RoommatePost, pk=pk)
    current_group = roommate_group_for_user(request.user)
    if post.author_id != request.user.id and (current_group is None or post.group_id != current_group.pk):
        return HttpResponseForbidden("You cannot edit this post.")

    grp = current_group if post.group_id else None
    form = RoommatePostForm(request.POST, instance=post, user=request.user, group=grp)
    if form.is_valid():
        form.save()
        messages.success(request, "Post updated.")
        return redirect(reverse("listings:roommates_hub") + "?tab=mypost")

    messages.error(request, _first_form_error(form, "Review the highlighted fields and try again."))
    context = {
        "tab": "mypost",
        "can_manage_roommate_post": True,
        "current_roommate_post": roommate_post_for_user(request.user),
    }
    context.update(_mypost_tab_context(request, edit_forms_by_pk={post.pk: form}, edit_error_pk=post.pk))
    return render(request, "listings/roommates_hub.html", context)


@login_required
@require_POST
def delete_roommate_post(request, pk):
    if not request.user.is_student:
        return HttpResponseForbidden("Student access is required.")

    post = get_object_or_404(RoommatePost, pk=pk)
    current_group = roommate_group_for_user(request.user)
    if post.author_id != request.user.id and (current_group is None or post.group_id != current_group.pk):
        return HttpResponseForbidden("You cannot delete this post.")

    post.delete()
    messages.success(request, "Post deleted.")
    return redirect(reverse("listings:roommates_hub") + "?tab=mypost")


@login_required
@require_POST
def remove_group_member(request, member_pk):
    if not request.user.is_student:
        raise Http404
    membership = get_object_or_404(RoommateGroupMembership, pk=member_pk)
    group = membership.group
    if group.lead_id != request.user.id:
        return HttpResponseForbidden("Only the group leader can remove members.")
    if membership.user_id == request.user.id:
        messages.error(request, "You can't remove yourself from the group.")
        return redirect(reverse("listings:roommates_hub") + "?tab=mypost")
    removed_name = membership.user.display_name
    membership.delete()
    messages.success(request, f"Removed {removed_name} from the group.")
    return redirect(reverse("listings:roommates_hub") + "?tab=mypost")


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
    commute_payload = commute_payload_for_listing(listing)
    commute_distance_miles = commute_payload["distance_miles"] if commute_payload else None
    commute_map_payload = _listing_commute_map_payload()
    commute_map_enabled = bool(
        commute_payload and commute_map_payload and commute_payload.get("origin") and commute_payload.get("destination")
    )
    if commute_map_enabled:
        commute_payload["map"] = commute_map_payload
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
        "commute_payload": commute_payload,
        "commute_distance_miles": commute_distance_miles,
        "commute_map_enabled": commute_map_enabled,
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
