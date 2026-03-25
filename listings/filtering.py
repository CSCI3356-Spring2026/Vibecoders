from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.utils import timezone

MAX_PRICE_FILTERS = [
    ("", "Any budget"),
    ("1000", "$500 - $1,000"),
    ("1500", "$1,000 - $1,500"),
    ("2000", "$1,500 - $2,000"),
    ("2500", "$2,000 - $2,500"),
]

MOVE_IN_FILTERS = [
    ("", "Anytime"),
    ("30", "Next 30 days"),
    ("60", "Next 60 days"),
    ("120", "Next 120 days"),
]


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


def apply_listing_filters(queryset, params, *, viewport_required=False):
    query = params.get("q", "").strip()
    if query:
        queryset = queryset.filter(
            Q(title__icontains=query) | Q(address__icontains=query) | Q(description__icontains=query)
        )

    max_price = params.get("max_price", "").strip()
    if max_price:
        try:
            max_price_value = Decimal(max_price)
        except InvalidOperation:
            max_price = ""
        else:
            if max_price_value > 0:
                queryset = queryset.filter(price__lte=max_price_value)
            else:
                max_price = ""

    lease_type = params.get("lease_type", "").strip()
    if lease_type:
        queryset = queryset.filter(lease_type=lease_type)

    available_by = params.get("available_by", "").strip()
    if available_by.isdigit():
        move_in_deadline = timezone.localdate() + timedelta(days=int(available_by))
        queryset = queryset.filter(start_date__lte=move_in_deadline)

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
        "max_price": max_price,
        "lease_type": lease_type,
        "available_by": available_by,
    }
