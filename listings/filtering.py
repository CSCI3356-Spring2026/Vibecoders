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


def apply_listing_filters(queryset, params):
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

    return queryset, {
        "q": query,
        "max_price": max_price,
        "lease_type": lease_type,
        "available_by": available_by,
    }
