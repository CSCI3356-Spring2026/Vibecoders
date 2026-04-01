from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.utils.dateparse import parse_date

PRICE_FILTER_MIN = Decimal("0")
PRICE_FILTER_MAX = Decimal("25000")
BEDROOMS_FILTER_MIN = 1
BATHROOMS_FILTER_MIN = Decimal("0.5")
BATHROOMS_FILTER_MAX = Decimal("10")
DISTANCE_FILTER_MIN = Decimal("0")


def parse_viewport_bounds(params):
    raw_bounds = {
        "west": (params.get("west") or "").strip(),
        "south": (params.get("south") or "").strip(),
        "east": (params.get("east") or "").strip(),
        "north": (params.get("north") or "").strip(),
    }
    if not any(raw_bounds.values()):
        return None
    if not all(raw_bounds.values()):
        return None

    try:
        bounds = {key: Decimal(value) for key, value in raw_bounds.items()}
    except InvalidOperation:
        return None

    if bounds["west"] > bounds["east"] or bounds["south"] > bounds["north"]:
        return None
    return bounds


def parse_price_filter(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return None, ""

    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None, ""

    if parsed < PRICE_FILTER_MIN or parsed > PRICE_FILTER_MAX:
        return None, ""
    return parsed, value


def parse_decimal_filter(raw_value, *, minimum=None, maximum=None):
    value = (raw_value or "").strip()
    if not value:
        return None, ""

    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None, ""

    if minimum is not None and parsed < minimum:
        return None, ""
    if maximum is not None and parsed > maximum:
        return None, ""
    return parsed, value


def parse_date_filter(raw_value):
    value = (raw_value or "").strip()
    if not value:
        return None, ""

    parsed = parse_date(value)
    if parsed is None:
        return None, ""
    return parsed, value


def parse_integer_filter(raw_value, *, minimum=None):
    value = (raw_value or "").strip()
    if not value:
        return None, ""

    if not value.isdigit():
        return None, ""

    parsed = int(value)
    if minimum is not None and parsed < minimum:
        return None, ""
    return parsed, value


def apply_listing_filters(queryset, params, *, viewport_required=False):
    query = params.get("q", "").strip()
    if query:
        queryset = queryset.filter(
            Q(title__icontains=query) | Q(address__icontains=query) | Q(description__icontains=query)
        )

    min_price_value, min_price = parse_price_filter(params.get("min_price", ""))
    if min_price_value is not None:
        queryset = queryset.filter(price__gte=min_price_value)

    max_price_value, max_price = parse_price_filter(params.get("max_price", ""))
    if max_price_value is not None:
        queryset = queryset.filter(price__lte=max_price_value)

    min_bedrooms_value, min_bedrooms = parse_integer_filter(params.get("min_bedrooms", ""), minimum=BEDROOMS_FILTER_MIN)
    if min_bedrooms_value is not None:
        queryset = queryset.filter(rooms__gte=min_bedrooms_value)

    min_bathrooms_value, min_bathrooms = parse_decimal_filter(
        params.get("min_bathrooms", ""),
        minimum=BATHROOMS_FILTER_MIN,
        maximum=BATHROOMS_FILTER_MAX,
    )
    if min_bathrooms_value is not None:
        queryset = queryset.filter(bathrooms__gte=min_bathrooms_value)

    lease_type = params.get("lease_type", "").strip()
    if lease_type:
        queryset = queryset.filter(lease_type=lease_type)

    max_distance_value, max_distance = parse_price_filter(params.get("max_distance", ""))
    if max_distance_value is not None and max_distance_value >= DISTANCE_FILTER_MIN:
        queryset = queryset.filter(distance_to_campus__isnull=False, distance_to_campus__lte=max_distance_value)

    availability_start_value, availability_start = parse_date_filter(params.get("availability_start", ""))
    availability_end_value, availability_end = parse_date_filter(params.get("availability_end", ""))
    if availability_start_value is not None:
        queryset = queryset.filter(end_date__gte=availability_start_value)
    if availability_end_value is not None:
        queryset = queryset.filter(start_date__lte=availability_end_value)

    has_parking = params.get("has_parking", "").strip().lower()
    has_parking_enabled = has_parking in {"1", "true", "yes", "on"}
    if has_parking_enabled:
        queryset = queryset.filter(has_parking=True)

    is_furnished = params.get("is_furnished", "").strip().lower()
    is_furnished_enabled = is_furnished in {"1", "true", "yes", "on"}
    if is_furnished_enabled:
        queryset = queryset.filter(is_furnished=True)

    allows_pets = params.get("allows_pets", "").strip().lower()
    allows_pets_enabled = allows_pets in {"1", "true", "yes", "on"}
    if allows_pets_enabled:
        queryset = queryset.exclude(pet_policy__exact="")

    has_yard = params.get("has_yard", "").strip().lower()
    has_yard_enabled = has_yard in {"1", "true", "yes", "on"}
    if has_yard_enabled:
        queryset = queryset.filter(has_yard=True)

    saved = params.get("saved", "").strip().lower()
    saved_enabled = saved in {"1", "true", "yes", "on"}
    if saved_enabled:
        queryset = queryset.filter(is_favorited=True)

    bounds = parse_viewport_bounds(params)
    if viewport_required and bounds is None:
        queryset = queryset.none()
    elif bounds is not None:
        queryset = queryset.filter(
            longitude__gte=bounds["west"],
            longitude__lte=bounds["east"],
            latitude__gte=bounds["south"],
            latitude__lte=bounds["north"],
        )

    return queryset, {
        "q": query,
        "min_price": min_price,
        "max_price": max_price,
        "min_bedrooms": min_bedrooms,
        "min_bathrooms": min_bathrooms,
        "lease_type": lease_type,
        "max_distance": max_distance,
        "availability_start": availability_start,
        "availability_end": availability_end,
        "has_parking": "1" if has_parking_enabled else "",
        "is_furnished": "1" if is_furnished_enabled else "",
        "allows_pets": "1" if allows_pets_enabled else "",
        "has_yard": "1" if has_yard_enabled else "",
        "saved": "1" if saved_enabled else "",
    }
