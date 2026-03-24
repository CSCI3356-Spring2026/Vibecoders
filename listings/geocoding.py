import logging

import requests
from django.conf import settings

BOSTON_COLLEGE_LATITUDE = 42.3355
BOSTON_COLLEGE_LONGITUDE = -71.1685
logger = logging.getLogger(__name__)


def geocode_listing_address(address):
    normalized_address = (address or "").strip()
    if not normalized_address or not settings.LISTING_GEOCODING_ENABLED:
        return None, None

    try:
        response = requests.get(
            settings.LISTING_GEOCODER_URL,
            params={
                "q": normalized_address,
                "limit": 1,
                "lat": BOSTON_COLLEGE_LATITUDE,
                "lon": BOSTON_COLLEGE_LONGITUDE,
            },
            headers={"User-Agent": settings.LISTING_GEOCODER_USER_AGENT},
            timeout=settings.LISTING_GEOCODER_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Listing geocoding request failed.", exc_info=exc)
        return None, None

    features = payload.get("features") or []
    if not features:
        return None, None

    coordinates = (features[0].get("geometry") or {}).get("coordinates") or []
    if len(coordinates) != 2:
        return None, None

    longitude, latitude = coordinates
    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError):
        return None, None

    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return None, None

    return latitude, longitude
