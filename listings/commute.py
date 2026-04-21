from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from math import asin, cos, radians, sin, sqrt

import requests
from django.conf import settings
from django.core.cache import cache

from core.campus import PRIMARY_CAMPUS_LATITUDE, PRIMARY_CAMPUS_LONGITUDE, PRIMARY_CAMPUS_NAME

BOSTON_COLLEGE_LATITUDE = PRIMARY_CAMPUS_LATITUDE
BOSTON_COLLEGE_LONGITUDE = PRIMARY_CAMPUS_LONGITUDE

COMMUTE_MODE_WALKING = "walking"
COMMUTE_MODE_TRANSIT = "transit"
COMMUTE_MODE_DRIVING = "driving"
COMMUTE_DEFAULT_MODE = COMMUTE_MODE_WALKING
COMMUTE_MODE_CHOICES = (
    (COMMUTE_MODE_WALKING, "Walking"),
    (COMMUTE_MODE_TRANSIT, "Train / transit"),
    (COMMUTE_MODE_DRIVING, "Driving"),
)
COMMUTE_ROUTE_MODES = {
    COMMUTE_MODE_WALKING: "walk",
    COMMUTE_MODE_TRANSIT: "transit",
    COMMUTE_MODE_DRIVING: "drive",
}

EARTH_RADIUS_MILES = 3958.8


def _rounded_decimal(value):
    return Decimal(str(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _coerce_decimal(value):
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _coerce_float(value):
    if value in (None, ""):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value


def straight_line_distance_miles(*, origin_latitude, origin_longitude, destination_latitude, destination_longitude):
    lat1 = _coerce_float(origin_latitude)
    lng1 = _coerce_float(origin_longitude)
    lat2 = _coerce_float(destination_latitude)
    lng2 = _coerce_float(destination_longitude)
    if None in {lat1, lng1, lat2, lng2}:
        return None

    lat1_rad, lng1_rad, lat2_rad, lng2_rad = map(radians, (lat1, lng1, lat2, lng2))
    delta_lat = lat2_rad - lat1_rad
    delta_lng = lng2_rad - lng1_rad
    haversine_value = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lng / 2) ** 2
    arc = 2 * asin(min(1, sqrt(haversine_value)))
    return Decimal(str(EARTH_RADIUS_MILES * arc))


def listing_distance_to_bc_miles(listing):
    if getattr(listing, "has_map_coordinates", False):
        distance = straight_line_distance_miles(
            origin_latitude=listing.latitude,
            origin_longitude=listing.longitude,
            destination_latitude=BOSTON_COLLEGE_LATITUDE,
            destination_longitude=BOSTON_COLLEGE_LONGITUDE,
        )
        if distance is not None:
            return distance
    return _coerce_decimal(getattr(listing, "distance_to_campus", None))


def routed_commute_enabled():
    return bool(getattr(settings, "LISTING_GEOAPIFY_API_KEY", "").strip())


def commute_available_for_listing(listing):
    return routed_commute_enabled() and getattr(listing, "has_map_coordinates", False)


def _geoapify_routing_url():
    return getattr(settings, "LISTING_GEOAPIFY_ROUTING_URL", "https://api.geoapify.com/v1/routing").strip()


def _commute_cache_key(listing_id, mode):
    return f"listing-commute:{listing_id}:{mode}"


def _seconds_to_display(seconds):
    total_minutes = max(1, round(float(seconds or 0) / 60))
    if total_minutes < 60:
        return f"{total_minutes} min"

    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours} hr {minutes} min" if minutes else f"{hours} hr"


def _meters_to_miles(value):
    if value in (None, ""):
        return None
    try:
        meters = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return (meters * Decimal("0.000621371")).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def _fetch_route_for_mode(listing, mode):
    route_mode = COMMUTE_ROUTE_MODES.get(mode)
    if route_mode is None:
        return None

    cache_key = _commute_cache_key(listing.pk, mode)
    cached_payload = cache.get(cache_key)
    if cached_payload is not None:
        return cached_payload

    response = requests.get(
        _geoapify_routing_url(),
        params={
            "waypoints": f"{listing.latitude},{listing.longitude}|{BOSTON_COLLEGE_LATITUDE},{BOSTON_COLLEGE_LONGITUDE}",
            "mode": route_mode,
            "format": "geojson",
            "apiKey": settings.LISTING_GEOAPIFY_API_KEY,
        },
        timeout=getattr(settings, "LISTING_GEOAPIFY_ROUTING_TIMEOUT_SECONDS", 6),
    )
    response.raise_for_status()
    route_payload = response.json()
    feature = route_payload.get("features", [{}])[0]
    properties = feature.get("properties") or {}
    geometry = feature.get("geometry")
    time_seconds = properties.get("time")
    if geometry is None or time_seconds in (None, ""):
        raise ValueError("Routing payload missing geometry or travel time.")

    payload = {
        "mode": mode,
        "label": dict(COMMUTE_MODE_CHOICES)[mode],
        "time_seconds": int(time_seconds),
        "display": _seconds_to_display(time_seconds),
        "distance_miles": str(_meters_to_miles(properties.get("distance")) or ""),
        "geometry": geometry,
    }
    cache.set(cache_key, payload, timeout=getattr(settings, "LISTING_COMMUTE_CACHE_TTL_SECONDS", 900))
    return payload


def commute_payload_for_listing(listing):
    if not commute_available_for_listing(listing):
        return None

    distance_miles = listing_distance_to_bc_miles(listing)
    if distance_miles is None:
        return None
    normalized_distance = _rounded_decimal(distance_miles)
    routes = {}
    for value, _label in COMMUTE_MODE_CHOICES:
        routes[value] = _fetch_route_for_mode(listing, value)

    return {
        "available": True,
        "destination_label": PRIMARY_CAMPUS_NAME,
        "distance_miles": f"{normalized_distance}",
        "default_mode": COMMUTE_DEFAULT_MODE,
        "modes": [
            {
                "value": mode,
                "label": route["label"],
                "display": route["display"],
                "distance_miles": route["distance_miles"],
            }
            for mode, route in routes.items()
        ],
        "routes": routes,
        "origin": {
            "lat": float(listing.latitude),
            "lng": float(listing.longitude),
        },
        "destination": {
            "lat": BOSTON_COLLEGE_LATITUDE,
            "lng": BOSTON_COLLEGE_LONGITUDE,
        },
    }
