from django.conf import settings


def get_geoapify_autocomplete_config():
    api_key = (settings.LISTING_GEOAPIFY_API_KEY or "").strip()
    url = (settings.LISTING_GEOAPIFY_AUTOCOMPLETE_URL or "").strip()
    if not settings.LISTING_MAPS_ENABLED or not api_key or not url:
        return {
            "enabled": False,
            "url": None,
            "api_key": None,
        }

    return {
        "enabled": True,
        "url": url,
        "api_key": api_key,
    }


def normalize_geoapify_suggestions(payload):
    suggestions = []
    for result in payload.get("results") or []:
        normalized = _normalize_geoapify_result(result)
        if normalized is not None:
            suggestions.append(normalized)
    return suggestions


def _normalize_geoapify_result(result):
    place_id = _clean_text(result.get("place_id"))
    label = _clean_text(result.get("formatted"))
    address_line_1 = _clean_text(result.get("address_line1"))
    address_line_2 = _clean_text(result.get("address_line2"))
    city = _clean_text(result.get("city"))
    state = _clean_text(result.get("state_code") or result.get("state"))
    postal_code = _clean_text(result.get("postcode"))
    country = _clean_text(result.get("country_code")).upper()
    latitude = _normalize_coordinate(result.get("lat"), minimum=-90, maximum=90)
    longitude = _normalize_coordinate(result.get("lon"), minimum=-180, maximum=180)

    if not all([place_id, label, address_line_1, city, state, postal_code, country]):
        return None
    if latitude is None or longitude is None:
        return None

    return {
        "provider_id": f"geoapify:{place_id}",
        "label": label,
        "address_line_1": address_line_1,
        "address_line_2": address_line_2,
        "city": city,
        "state": state,
        "postal_code": postal_code,
        "country": country,
        "latitude": latitude,
        "longitude": longitude,
    }


def _clean_text(value):
    return (value or "").strip()


def _normalize_coordinate(value, *, minimum, maximum):
    try:
        coordinate = float(value)
    except (TypeError, ValueError):
        return None

    if not minimum <= coordinate <= maximum:
        return None

    return coordinate
