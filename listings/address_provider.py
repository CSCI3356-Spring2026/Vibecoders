from django.conf import settings


def get_geoapify_autocomplete_config():
    api_key = (settings.LISTING_GEOAPIFY_API_KEY or "").strip()
    url = (settings.LISTING_GEOAPIFY_AUTOCOMPLETE_URL or "").strip()
    if not api_key or not url:
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
    if not isinstance(payload, dict):
        return []

    suggestions = []
    seen_labels = set()
    for result in _geoapify_payload_results(payload):
        normalized = _normalize_geoapify_result(result)
        if normalized is not None:
            dedupe_key = normalized["label"].casefold()
            if dedupe_key in seen_labels:
                continue
            seen_labels.add(dedupe_key)
            suggestions.append(normalized)
    return suggestions


def _normalize_geoapify_result(result):
    if not isinstance(result, dict):
        return None

    place_id = _clean_text(result.get("place_id"))
    address_line_1 = _normalize_address_line_1(result)
    address_line_2 = _clean_text(result.get("address_line2"))
    city = _clean_text(
        result.get("city")
        or result.get("town")
        or result.get("suburb")
        or result.get("village")
        or result.get("hamlet")
        or result.get("county")
    )
    state = _clean_text(result.get("state_code") or result.get("state"))
    postal_code = _clean_text(result.get("postcode"))
    country_name = _clean_text(result.get("country"))
    country = _clean_text(result.get("country_code") or country_name).upper()
    label = (
        _build_address_label(
            address_line_1=address_line_1,
            city=city,
            state=state,
            postal_code=postal_code,
            country=country,
        )
        or _clean_text(result.get("formatted"))
        or _build_fallback_label(
            address_line_1=address_line_1,
            city=city,
            state=state,
            postal_code=postal_code,
            country_name=country_name or country,
        )
    )
    latitude = _normalize_coordinate(result.get("lat"), minimum=-90, maximum=90)
    longitude = _normalize_coordinate(result.get("lon"), minimum=-180, maximum=180)

    if not all([place_id, label, address_line_1, state, country]):
        return None
    if not city and not postal_code:
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
        "primary_label": address_line_1,
        "latitude": latitude,
        "longitude": longitude,
    }


def _geoapify_payload_results(payload):
    raw_results = payload.get("results")
    if isinstance(raw_results, list):
        for result in raw_results:
            yield result

    raw_features = payload.get("features")
    if not isinstance(raw_features, list):
        return

    for feature in raw_features:
        flattened = _flatten_geoapify_feature(feature)
        if flattened is not None:
            yield flattened


def _flatten_geoapify_feature(feature):
    if not isinstance(feature, dict):
        return None

    properties = feature.get("properties")
    if not isinstance(properties, dict):
        return None

    flattened = dict(properties)
    geometry = feature.get("geometry")
    coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2:
        flattened.setdefault("lon", coordinates[0])
        flattened.setdefault("lat", coordinates[1])
    return flattened


def _clean_text(value):
    return (value or "").strip()


def _normalize_address_line_1(result):
    house_number = _clean_text(result.get("housenumber"))
    street = _clean_text(result.get("street"))
    if house_number and street:
        return f"{house_number} {street}"

    address_line_1 = _clean_text(result.get("address_line1"))
    if address_line_1:
        return address_line_1
    if street:
        return street

    return _clean_text(result.get("name"))


def _build_address_label(*, address_line_1, city, state, postal_code, country):
    locality = ""
    if city and state:
        locality = f"{city}, {state}"
    else:
        locality = city or state

    if postal_code:
        locality = f"{locality} {postal_code}".strip()

    parts = [address_line_1]
    if locality:
        parts.append(locality)
    if country and country != "US":
        parts.append(country)
    return ", ".join(part for part in parts if part)


def _build_fallback_label(*, address_line_1, city, state, postal_code, country_name):
    locality = ", ".join(part for part in [city, state] if part)
    if postal_code:
        locality = f"{locality} {postal_code}".strip()

    return ", ".join(part for part in [address_line_1, locality, country_name] if part)


def _normalize_coordinate(value, *, minimum, maximum):
    try:
        coordinate = float(value)
    except (TypeError, ValueError):
        return None

    if not minimum <= coordinate <= maximum:
        return None

    return coordinate
