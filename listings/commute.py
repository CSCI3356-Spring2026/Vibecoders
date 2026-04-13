from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from math import asin, cos, radians, sin, sqrt

from .geocoding import BOSTON_COLLEGE_LATITUDE, BOSTON_COLLEGE_LONGITUDE

COMMUTE_MODE_WALKING = "walking"
COMMUTE_MODE_TRANSIT = "transit"
COMMUTE_MODE_DRIVING = "driving"
COMMUTE_DEFAULT_MODE = COMMUTE_MODE_WALKING
COMMUTE_MODE_CHOICES = (
    (COMMUTE_MODE_WALKING, "Walking"),
    (COMMUTE_MODE_TRANSIT, "Train / transit"),
    (COMMUTE_MODE_DRIVING, "Driving"),
)

EARTH_RADIUS_MILES = 3958.8
MODE_FACTORS = {
    COMMUTE_MODE_WALKING: {"route_multiplier": 1.18, "speed_mph": 3.1, "fixed_minutes": 0},
    COMMUTE_MODE_TRANSIT: {"route_multiplier": 1.32, "speed_mph": 15.5, "fixed_minutes": 8},
    COMMUTE_MODE_DRIVING: {"route_multiplier": 1.28, "speed_mph": 17.5, "fixed_minutes": 4},
}


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


def estimate_commute_minutes(distance_miles, mode):
    base_distance = _coerce_decimal(distance_miles)
    config = MODE_FACTORS.get(mode)
    if base_distance is None or base_distance < 0 or config is None:
        return None

    route_distance = base_distance * Decimal(str(config["route_multiplier"]))
    moving_minutes = (route_distance / Decimal(str(config["speed_mph"]))) * Decimal("60")
    total_minutes = moving_minutes + Decimal(str(config["fixed_minutes"]))
    rounded_up = total_minutes.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return max(1, int(rounded_up))


def commute_payload_for_listing(listing):
    distance_miles = listing_distance_to_bc_miles(listing)
    if distance_miles is None:
        return None

    normalized_distance = _rounded_decimal(distance_miles)
    modes = []
    for value, label in COMMUTE_MODE_CHOICES:
        minutes = estimate_commute_minutes(normalized_distance, value)
        modes.append(
            {
                "value": value,
                "label": label,
                "minutes": minutes,
                "display": f"{minutes} min" if minutes is not None else "Unavailable",
            }
        )

    payload = {
        "destination_label": "Boston College",
        "distance_miles": f"{normalized_distance}",
        "default_mode": COMMUTE_DEFAULT_MODE,
        "modes": modes,
    }
    if getattr(listing, "has_map_coordinates", False):
        payload["origin"] = {
            "lat": float(listing.latitude),
            "lng": float(listing.longitude),
        }
        payload["destination"] = {
            "lat": BOSTON_COLLEGE_LATITUDE,
            "lng": BOSTON_COLLEGE_LONGITUDE,
        }
    return payload
