import io
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import requests
from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from PIL import Image

from communications.models import ListingConversation, ListingMessage
from users.models import FavoriteRoommate, Role

from ..address_signing import sign_address_selection, unsign_address_selection
from ..models import Listing, ListingFavorite, ListingImage, ListingReport, ListingReview, RoommatePost
from .base import ListingTestCase


@override_settings(
    LISTING_GEOAPIFY_API_KEY="geoapify-test-key",
    LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
)
class ListingPageTests(ListingTestCase):
    def make_verified_address_token(
        self,
        *,
        label="140 Commonwealth Ave, Chestnut Hill, MA 02467, US",
        address_line_1="140 Commonwealth Ave",
        city="Chestnut Hill",
        state="MA",
        postal_code="02467",
        country="US",
        latitude=42.3355,
        longitude=-71.1685,
        provider_id="geoapify:place-140-commonwealth",
    ):
        return sign_address_selection(
            {
                "provider_id": provider_id,
                "label": label,
                "address_line_1": address_line_1,
                "address_line_2": "",
                "city": city,
                "state": state,
                "postal_code": postal_code,
                "country": country,
                "latitude": latitude,
                "longitude": longitude,
            }
        )

    def listing_payload(self, **overrides):
        payload = {
            "title": "Quiet dorm near campus",
            "address": "140 Commonwealth Ave, Chestnut Hill, MA 02467, US",
            "verified_address_token": self.make_verified_address_token(),
            "price": "1200.00",
            "lease_type": "FULL",
            "start_date": date(2026, 9, 1),
            "end_date": date(2027, 5, 31),
            "description": "Close to dining hall.",
        }
        payload.update(overrides)
        return payload

    def make_image_upload(self, name="photo.png"):
        buffer = io.BytesIO()
        Image.new("RGB", (4, 4), color="white").save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    @override_settings(
        LISTING_GEOAPIFY_API_KEY="geoapify-test-key",
        LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
    )
    @patch("requests.get")
    def test_address_autocomplete_endpoint_returns_signed_suggestions_for_valid_query(self, requests_get):
        requests_get.return_value.json.return_value = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "place_id": "geoapify-place-1",
                        "formatted": "140 Commonwealth Avenue, Chestnut Hill, MA 02467, United States of America",
                        "address_line1": "140 Commonwealth Avenue",
                        "address_line2": "",
                        "housenumber": "140",
                        "street": "Commonwealth Avenue",
                        "city": "Chestnut Hill",
                        "state_code": "MA",
                        "postcode": "02467",
                        "country_code": "us",
                    },
                    "geometry": {"type": "Point", "coordinates": [-71.1685, 42.3355]},
                }
            ],
        }
        requests_get.return_value.raise_for_status.return_value = None
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:address_suggestions"), {"q": "140 Commonwealth"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["results"]), 1)
        result = payload["results"][0]
        self.assertEqual(result["label"], "140 Commonwealth Avenue, Chestnut Hill, MA 02467")
        self.assertEqual(result["primary_label"], "140 Commonwealth Avenue")
        self.assertEqual(result["context_label"], "Chestnut Hill, MA 02467")
        self.assertEqual(result["address_line_1"], "140 Commonwealth Avenue")
        self.assertEqual(result["latitude"], 42.3355)
        self.assertEqual(result["longitude"], -71.1685)
        self.assertIn("token", result)
        signed_payload = unsign_address_selection(result["token"], max_age=300)
        self.assertEqual(signed_payload["provider_id"], "geoapify:geoapify-place-1")
        self.assertEqual(signed_payload["address_line_1"], "140 Commonwealth Avenue")
        requests_get.assert_called_once()
        self.assertEqual(requests_get.call_args.kwargs["params"]["filter"], "countrycode:us")
        self.assertEqual(
            requests_get.call_args.kwargs["params"]["bias"],
            "proximity:-71.1685,42.3355",
        )

    @override_settings(
        LISTING_GEOAPIFY_API_KEY="geoapify-test-key",
        LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
    )
    @patch("requests.get")
    def test_address_autocomplete_endpoint_returns_json_auth_error_for_unauthenticated_requests(self, requests_get):
        response = self.client.get(
            reverse("listings:address_suggestions"),
            {"q": "140 Commonwealth"},
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 401)
        payload = response.json()
        self.assertEqual(payload["results"], [])
        self.assertEqual(payload["error"]["message"], "Sign in again to verify addresses.")
        self.assertTrue(payload["error"]["requires_login"])
        requests_get.assert_not_called()

    @override_settings(
        LISTING_GEOAPIFY_API_KEY="geoapify-test-key",
        LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
    )
    @patch("requests.get")
    def test_address_autocomplete_endpoint_returns_empty_results_for_blank_or_short_query(self, requests_get):
        self.client.force_login(self.user)

        blank_response = self.client.get(reverse("listings:address_suggestions"), {"q": ""})
        short_response = self.client.get(reverse("listings:address_suggestions"), {"q": "12"})

        self.assertEqual(blank_response.status_code, 200)
        self.assertEqual(blank_response.json(), {"results": []})
        self.assertEqual(short_response.status_code, 200)
        self.assertEqual(short_response.json(), {"results": []})
        requests_get.assert_not_called()

    @override_settings(
        LISTING_GEOAPIFY_API_KEY="geoapify-test-key",
        LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
    )
    @patch("requests.get", side_effect=requests.RequestException("provider unavailable"))
    def test_address_autocomplete_endpoint_returns_retry_friendly_inline_error_contract(self, requests_get):
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:address_suggestions"), {"q": "140 Commonwealth"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "results": [],
                "error": {
                    "message": "Address suggestions are temporarily unavailable. Try again.",
                    "retryable": True,
                },
            },
        )
        requests_get.assert_called_once()

    @override_settings(
        LISTING_GEOAPIFY_API_KEY="geoapify-test-key",
        LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
    )
    @patch("requests.get")
    def test_address_autocomplete_endpoint_handles_malformed_provider_payload(self, requests_get):
        requests_get.return_value.raise_for_status.return_value = None
        requests_get.return_value.json.side_effect = ValueError("malformed payload")
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:address_suggestions"), {"q": "140 Commonwealth"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {
                "results": [],
                "error": {
                    "message": "Address suggestions are temporarily unavailable. Try again.",
                    "retryable": True,
                },
            },
        )
        requests_get.assert_called_once()

    @override_settings(LISTING_ADDRESS_AUTOCOMPLETE_RATE_LIMIT=1, LISTING_ADDRESS_AUTOCOMPLETE_RATE_WINDOW_SECONDS=60)
    @patch("requests.get")
    def test_address_autocomplete_endpoint_throttles_repeat_requests(self, requests_get):
        requests_get.return_value.json.return_value = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "place_id": "geoapify-place-1",
                        "formatted": "140 Commonwealth Avenue, Chestnut Hill, MA 02467, United States of America",
                        "address_line1": "140 Commonwealth Avenue",
                        "address_line2": "",
                        "housenumber": "140",
                        "street": "Commonwealth Avenue",
                        "city": "Chestnut Hill",
                        "state_code": "MA",
                        "postcode": "02467",
                        "country_code": "us",
                    },
                    "geometry": {"type": "Point", "coordinates": [-71.1685, 42.3355]},
                }
            ],
        }
        requests_get.return_value.raise_for_status.return_value = None
        cache.clear()
        self.client.force_login(self.user)

        first_response = self.client.get(reverse("listings:address_suggestions"), {"q": "140 Commonwealth"})
        second_response = self.client.get(reverse("listings:address_suggestions"), {"q": "140 Commonwealth"})

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 429)
        self.assertEqual(
            second_response.json(),
            {
                "results": [],
                "error": {
                    "message": "Too many address lookups. Wait a moment and try again.",
                    "retryable": True,
                },
            },
        )
        requests_get.assert_called_once()

    def test_listing_pages_require_login(self):
        listing = self.create_listing()

        for path in (
            reverse("listings:listing_list"),
            reverse("listings:detail", args=[listing.pk]),
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn("/accounts/login/", response.url)

    def test_listing_pages_render_for_authenticated_user(self):
        listing = self.create_listing()
        self.client.force_login(self.user)

        for path in (
            reverse("listings:listing_list"),
            reverse("listings:detail", args=[listing.pk]),
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)

    def test_listing_list_includes_detail_page_link(self):
        listing = self.create_listing()
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(response, reverse("listings:detail", args=[listing.pk]))

    def test_listing_favorite_toggle_creates_and_removes(self):
        owner = get_user_model().objects.create_user(username="owner2", email="owner2@bc.edu", password="test")
        listing = owner.listings.create(
            title="Saved listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            description="Close to campus.",
            approval_status="approved",
        )
        self.client.force_login(self.user)
        url = reverse("listings:toggle_favorite", args=[listing.pk])

        response = self.client.post(url, {"next": reverse("listings:detail", args=[listing.pk])})
        self.assertRedirects(response, reverse("listings:detail", args=[listing.pk]))
        self.assertTrue(ListingFavorite.objects.filter(user=self.user, listing=listing).exists())

        response = self.client.post(url, {"next": reverse("listings:detail", args=[listing.pk])})
        self.assertRedirects(response, reverse("listings:detail", args=[listing.pk]))
        self.assertFalse(ListingFavorite.objects.filter(user=self.user, listing=listing).exists())

    def test_listing_list_includes_favorite_state(self):
        owner = get_user_model().objects.create_user(username="owner3", email="owner3@bc.edu", password="test")
        listing = owner.listings.create(
            title="Saved listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            description="Close to campus.",
            approval_status="approved",
        )
        ListingFavorite.objects.create(user=self.user, listing=listing)
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        listings_page = response.context["listings"]
        self.assertTrue(listings_page.object_list[0].is_favorited)

    def test_listing_list_saved_filter_limits_results(self):
        owner = get_user_model().objects.create_user(username="owner4", email="owner4@bc.edu", password="test")
        listing = owner.listings.create(
            title="Saved listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            description="Close to campus.",
            approval_status="approved",
        )
        other_listing = self.create_listing(title="Unsaved listing", address="200 Comm Ave")
        ListingFavorite.objects.create(user=self.user, listing=listing)
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"), {"saved": "1"})

        listings_page = response.context["listings"]
        listing_ids = [item.id for item in listings_page.object_list]
        self.assertIn(listing.id, listing_ids)
        self.assertNotIn(other_listing.id, listing_ids)

    def test_listing_page_renders_saved_filter_as_select_control(self):
        self.create_listing(title="Saved filter listing")
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"), {"saved": "1"})

        self.assertContains(response, '<select class="form-select" id="filter-saved" name="saved">', html=False)
        self.assertContains(response, '<option value="">All listings</option>', html=False)
        self.assertContains(response, '<option value="1" selected>Saved only</option>', html=False)

    def test_listing_list_bathrooms_filter_limits_results(self):
        matching_listing = self.create_listing(title="Two bath", bathrooms="2.0")
        other_listing = self.create_listing(title="One bath", address="200 Comm Ave", bathrooms="1.0")
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"), {"min_bathrooms": "2"})

        listings_page = response.context["listings"]
        listing_ids = [item.id for item in listings_page.object_list]
        self.assertIn(matching_listing.id, listing_ids)
        self.assertNotIn(other_listing.id, listing_ids)

    def test_listing_page_renders_map_first_layout_hooks(self):
        self.create_listing(title="Mapped listing", latitude=42.3355, longitude=-71.1685)
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))
        content = response.content.decode()
        browser_index = content.index("data-listings-browser-shell")
        workspace_index = content.index("data-listings-workspace")
        filters_index = content.index("data-listings-filters")
        results_index = content.index("data-listings-results-pane")
        map_index = content.index("data-listings-map-pane")

        self.assertContains(response, "data-listings-page")
        self.assertContains(response, "listing-browser-page")
        self.assertContains(response, "data-listings-workspace")
        self.assertContains(response, "data-listings-filters")
        self.assertContains(response, "data-listings-filter-form")
        self.assertContains(response, "data-listings-filter-menu")
        self.assertContains(response, 'data-filter-name="baths"')
        self.assertContains(response, 'data-filter-name="filters"')
        self.assertContains(response, "data-listings-browser-shell")
        self.assertContains(response, "data-listings-results-pane")
        self.assertContains(response, "data-listings-map-pane")
        self.assertContains(response, "listing-browser-main")
        self.assertContains(response, "data-listings-map-root")
        self.assertContains(response, "data-listings-map")
        self.assertContains(response, "data-listings-results")
        self.assertContains(response, "data-listings-live-error")
        self.assertContains(response, 'class="form-control listing-filter-search-input"')
        self.assertNotContains(response, "Boston College rentals")
        self.assertNotContains(
            response,
            'class="btn btn-brand" href="/listings/create/">Create listing</a>',
            html=False,
        )
        self.assertNotContains(response, ">Reset<", html=False)
        self.assertLess(browser_index, results_index)
        self.assertLess(workspace_index, results_index)
        self.assertLess(results_index, filters_index)
        self.assertLess(filters_index, map_index)
        self.assertLess(results_index, map_index)

    def test_listing_page_embeds_initial_json_payload_hooks_for_live_controller(self):
        listing = self.create_listing(title="Mapped listing", latitude=42.3355, longitude=-71.1685)
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(response, 'id="listing-page-initial-payload"')
        self.assertContains(response, '"total": 1')
        self.assertContains(response, f'"id": {listing.id}')
        self.assertContains(response, '"markers"')
        self.assertContains(response, '"cards"')
        self.assertContains(response, 'id="listing-page-initial-state"')
        self.assertContains(response, '"selected_listing_id": ""')

    def test_listing_page_exposes_search_endpoints_and_initial_state_to_js_controller(self):
        self.create_listing(title="Mapped listing", latitude=42.3355, longitude=-71.1685)
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(response, "data-listings-page")
        self.assertContains(response, f'data-listings-search-url="{reverse("listings:search")}"')
        self.assertContains(response, 'data-listings-map-style-url="https://maps.geoapify.com/v1/styles/osm-liberty/')
        self.assertContains(
            response, 'data-listings-map-default-style-url="https://maps.geoapify.com/v1/styles/osm-liberty/'
        )
        self.assertContains(
            response,
            f'data-listings-map-satellite-style-url="{settings.LISTING_MAP_SATELLITE_STYLE_URL}"',
        )
        self.assertContains(response, "data-listings-map-style-toggle")
        self.assertContains(response, 'data-selected-listing-id=""')

    @override_settings(LISTING_MAP_SATELLITE_STYLE_URL="https://tiles.example.com/satellite/style.json")
    def test_listing_page_exposes_configured_satellite_toggle(self):
        self.create_listing(title="Mapped listing", latitude=42.3355, longitude=-71.1685)
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(
            response, 'data-listings-map-satellite-style-url="https://tiles.example.com/satellite/style.json"'
        )
        self.assertContains(response, "data-listings-map-style-toggle")
        self.assertContains(response, 'data-style-mode="map"')
        self.assertContains(response, 'data-style-mode="satellite"')

    def test_map_marker_buttons_do_not_override_maplibre_positioning_transform(self):
        module_url = (Path(__file__).resolve().parents[2] / "static/js/listings-map-view.js").as_uri()
        script = f"""
import assert from "node:assert/strict";
import {{ createListingsMapView }} from {module_url!r};

class HTMLElement {{
    constructor() {{
        this.dataset = {{}};
        this.style = {{}};
        this.attributes = {{}};
        this.listeners = {{}};
        this.hidden = false;
        this.textContent = "";
        this.innerHTML = "";
        this.children = [];
        this.className = "";
        this.classList = {{
            add: (...tokens) => tokens.forEach((token) => this._toggleClass(token, true)),
            remove: (...tokens) => tokens.forEach((token) => this._toggleClass(token, false)),
            toggle: (token, force) => {{
                const shouldAdd = force ?? !this.className.split(/\\s+/).includes(token);
                this._toggleClass(token, shouldAdd);
            }},
        }};
    }}

    _toggleClass(token, force) {{
        const next = new Set(this.className.split(/\\s+/).filter(Boolean));
        if (force) {{
            next.add(token);
        }} else {{
            next.delete(token);
        }}
        this.className = Array.from(next).join(" ");
    }}

    setAttribute(name, value) {{
        this.attributes[name] = value;
    }}

    addEventListener(type, handler) {{
        this.listeners[type] = handler;
    }}

    append(child) {{
        this.children.push(child);
    }}

    querySelector() {{
        return null;
    }}
}}

class HTMLButtonElement extends HTMLElement {{}}

globalThis.HTMLElement = HTMLElement;
globalThis.document = {{
    createElement(tag) {{
        if (tag === "button") {{
            return new HTMLButtonElement();
        }}
        return new HTMLElement();
    }},
}};

const capturedElements = [];
class MockMap {{
    constructor() {{
        this.handlers = {{}};
        globalThis.__map = this;
    }}

    addControl() {{}}

    on(name, handler) {{
        this.handlers[name] = handler;
    }}

    getBounds() {{
        return {{
            getWest() {{ return -71.3; }},
            getSouth() {{ return 42.2; }},
            getEast() {{ return -71.0; }},
            getNorth() {{ return 42.5; }},
        }};
    }}

    setCenter() {{}}
    setZoom() {{}}
    fitBounds() {{}}
    setStyle(style) {{
        this.style = style;
        this.styleCalls = this.styleCalls || [];
        this.styleCalls.push(style);
    }}
}}

class MockMarker {{
    constructor({{ element }}) {{
        this.element = element;
        capturedElements.push(element);
    }}

    setLngLat() {{
        return this;
    }}

    addTo() {{
        return this;
    }}

    remove() {{}}
}}

globalThis.maplibregl = {{
    Map: MockMap,
    Marker: MockMarker,
    NavigationControl: class {{}},
    LngLatBounds: class {{
        extend() {{}}
    }},
}};

const canvas = new HTMLElement();
const root = new HTMLElement();
root.querySelector = (selector) => (selector === "[data-listings-map-canvas]" ? canvas : null);

const view = createListingsMapView({{
    root,
    defaultStyleUrl: "https://maps.example.com/style.json",
    satelliteStyleUrl: "builtin://satellite",
    defaultLat: 42.3355,
    defaultLng: -71.1685,
    initialMarkers: [{{ id: 1, price: "$1800", title: "Beacon apartment", lat: 42.3355, lng: -71.1685 }}],
}});

globalThis.__map.handlers.load();
view.setSelectedListing(1);
view.setStyleMode("satellite");
globalThis.__map.handlers["style.load"]();

assert.equal(capturedElements.length, 1);
assert.equal(capturedElements[0].className.includes("listing-map-marker"), true);
assert.equal(capturedElements[0].style.transform ?? "", "");
assert.equal(typeof globalThis.__map.styleCalls[0], "object");
assert.equal(globalThis.__map.styleCalls[0].sources.satellite.type, "raster");
assert.equal(globalThis.__map.styleCalls[0].layers[0].id, "satellite");
assert.equal(view.getStyleMode(), "satellite");
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

    def test_listing_page_loads_map_bootstrap_without_popup_link_navigation_contract(self):
        self.create_listing(title="Mapped listing", latitude=42.3355, longitude=-71.1685)
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "maplibre-gl@5.18.0/dist/maplibre-gl.css")
        self.assertContains(response, "maplibre-gl@5.18.0/dist/maplibre-gl.js")
        self.assertContains(response, "js/listings-map.js")
        self.assertNotContains(response, "listing-map-popup-link")
        self.assertNotContains(response, "Open listing")

    def test_listing_page_renders_result_cards_with_selection_and_detail_hooks(self):
        listing = self.create_listing(title="Mapped listing", latitude=42.3355, longitude=-71.1685)
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))
        detail_url = reverse("listings:detail", args=[listing.pk])

        self.assertContains(response, "data-listings-results-list")
        self.assertContains(response, "data-listing-card")
        self.assertContains(response, f'data-listing-id="{listing.id}"')
        self.assertContains(response, f'data-listing-detail-url="{detail_url}"')
        self.assertContains(response, 'data-listing-selected="false"')
        self.assertNotContains(response, "listing-map-popup-link")

    def test_listing_page_exposes_empty_state_container_for_zero_results(self):
        self.create_listing(title="Mapped listing", latitude=42.3355, longitude=-71.1685)
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"), {"q": "nowhere"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-listings-empty-state")

    def test_listing_page_exposes_inline_live_search_error_container(self):
        self.create_listing(title="Mapped listing", latitude=42.3355, longitude=-71.1685)
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-listings-live-error")
        self.assertContains(response, "data-listings-empty-state")
        self.assertContains(response, 'role="alert"')

    def test_listing_list_context_includes_marker_payload_for_geocoded_results(self):
        mapped_listing = self.create_listing(title="Mapped listing", latitude=42.3355, longitude=-71.1685)
        self.create_listing(title="Unmapped listing", address="200 Beacon St")
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(response, "data-listing-map-root")
        markers = response.context["listing_initial_payload"]["markers"]
        self.assertEqual(len(markers), 1)
        self.assertEqual(markers[0]["title"], mapped_listing.title)
        self.assertEqual(markers[0]["url"], reverse("listings:detail", args=[mapped_listing.pk]))
        self.assertAlmostEqual(markers[0]["lat"], 42.3355)
        self.assertAlmostEqual(markers[0]["lng"], -71.1685)

    @override_settings(LISTING_MAPS_ENABLED=False)
    def test_listing_list_hides_map_when_feature_flag_is_disabled(self):
        self.create_listing(title="Mapped listing", latitude=42.3355, longitude=-71.1685)
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertNotContains(response, "data-listing-map-root")
        self.assertNotIn("listing_initial_payload", response.context)

    @override_settings(LISTING_MAPS_ENABLED=False)
    def test_listing_list_suppresses_map_first_contract_when_feature_flag_is_disabled(self):
        self.create_listing(title="Mapped listing", latitude=42.3355, longitude=-71.1685)
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["listing_maps_enabled"])
        self.assertNotIn("listing_search_url", response.context)
        self.assertNotIn("listing_map_default_lat", response.context)
        self.assertNotIn("listing_map_default_lng", response.context)
        self.assertNotContains(response, "data-listings-page")
        self.assertNotContains(response, "data-listings-map-shell")
        self.assertNotContains(response, "data-listings-live-error")
        self.assertNotContains(response, "maplibre-gl@5.18.0/dist/maplibre-gl.js")
        self.assertNotContains(response, "js/listings-map.js")

    @override_settings(LISTING_GEOAPIFY_API_KEY="", LISTING_GEOAPIFY_MAP_STYLE_URL="")
    def test_listing_list_falls_back_when_map_style_configuration_is_missing(self):
        self.create_listing(title="Mapped listing", latitude=42.3355, longitude=-71.1685)
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["listing_maps_enabled"])
        self.assertTrue(response.context["listing_maps_unavailable"])
        self.assertNotContains(response, "data-listings-page")
        self.assertNotContains(response, "maplibre-gl@5.18.0/dist/maplibre-gl.js")
        self.assertNotContains(response, "js/listings-map.js")
        self.assertContains(response, "Map view is unavailable until Geoapify map configuration is set.")

    def test_live_search_filters_results_to_current_bounds(self):
        inside = self.create_listing(title="Inside bounds", latitude=42.3355, longitude=-71.1685)
        self.create_listing(title="Outside bounds", latitude=42.0, longitude=-71.9)
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("listings:search"),
            {
                "west": "-71.3",
                "south": "42.2",
                "east": "-71.0",
                "north": "42.5",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual([item["id"] for item in payload["cards"]], [inside.id])
        self.assertEqual([item["id"] for item in payload["markers"]], [inside.id])

    def test_live_search_returns_no_results_without_complete_valid_bounds(self):
        inside = self.create_listing(title="Inside bounds", latitude=42.3355, longitude=-71.1685)
        self.client.force_login(self.user)

        invalid_responses = [
            self.client.get(reverse("listings:search")),
            self.client.get(reverse("listings:search"), {"west": "-71.3", "south": "42.2", "east": "-71.0"}),
            self.client.get(
                reverse("listings:search"),
                {"west": "-71.3", "south": "42.2", "east": "-71.0", "north": "north"},
            ),
            self.client.get(
                reverse("listings:search"),
                {"west": "-71.0", "south": "42.5", "east": "-71.3", "north": "42.2"},
            ),
        ]

        for response in invalid_responses:
            with self.subTest(query=response.wsgi_request.GET.urlencode()):
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"total": 0, "markers": [], "cards": []})

        self.assertTrue(inside.has_map_coordinates)

    def test_live_search_combines_bounds_with_standard_filters(self):
        matching = self.create_listing(
            title="Beacon sublease",
            address="1731 Beacon St",
            price="950.00",
            lease_type="SUBLEASE",
            start_date=date.today() + timedelta(days=15),
            latitude=42.3355,
            longitude=-71.1685,
        )
        self.create_listing(
            title="Beacon outside bounds",
            address="1740 Beacon St",
            price="950.00",
            lease_type="SUBLEASE",
            start_date=date.today() + timedelta(days=15),
            latitude=42.0,
            longitude=-71.9,
        )
        self.create_listing(
            title="Commonwealth sublease",
            address="140 Commonwealth Ave",
            price="950.00",
            lease_type="SUBLEASE",
            start_date=date.today() + timedelta(days=15),
            latitude=42.3354,
            longitude=-71.1684,
        )
        self.create_listing(
            title="Beacon premium",
            address="1732 Beacon St",
            price="2100.00",
            lease_type="SUBLEASE",
            start_date=date.today() + timedelta(days=15),
            latitude=42.3353,
            longitude=-71.1683,
        )
        self.create_listing(
            title="Beacon full lease",
            address="1733 Beacon St",
            price="950.00",
            lease_type="FULL",
            start_date=date.today() + timedelta(days=15),
            latitude=42.3352,
            longitude=-71.1682,
        )
        self.create_listing(
            title="Beacon later move-in",
            address="1734 Beacon St",
            price="950.00",
            lease_type="SUBLEASE",
            start_date=date.today() + timedelta(days=45),
            latitude=42.3351,
            longitude=-71.1681,
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("listings:search"),
            {
                "q": "Beacon",
                "min_price": "900",
                "max_price": "1000",
                "lease_type": "SUBLEASE",
                "availability_start": str(date.today() + timedelta(days=5)),
                "availability_end": str(date.today() + timedelta(days=30)),
                "west": "-71.3",
                "south": "42.2",
                "east": "-71.0",
                "north": "42.5",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual([item["id"] for item in payload["cards"]], [matching.id])
        self.assertEqual([item["id"] for item in payload["markers"]], [matching.id])

    def test_live_search_respects_current_user_access_rules(self):
        realtor = get_user_model().objects.create_user(
            username="agent",
            email="agent@example.com",
            password="testpass123",
            role=Role.REALTOR,
        )
        self.user.listings.create(
            title="Student listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date=date.today() + timedelta(days=10),
            end_date=date.today() + timedelta(days=200),
            property_type="apartment",
            description="Visible to students.",
            latitude=42.3355,
            longitude=-71.1685,
            approval_status="approved",
        )
        own_listing = realtor.listings.create(
            title="Realtor listing",
            address="150 Commonwealth Ave",
            price="1400.00",
            lease_type="FULL",
            start_date=date.today() + timedelta(days=10),
            end_date=date.today() + timedelta(days=200),
            property_type="apartment",
            description="Owned by realtor.",
            latitude=42.3356,
            longitude=-71.1684,
            approval_status="approved",
        )
        self.client.force_login(realtor)

        response = self.client.get(
            reverse("listings:search"),
            {
                "west": "-71.3",
                "south": "42.2",
                "east": "-71.0",
                "north": "42.5",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual([item["id"] for item in payload["cards"]], [own_listing.id])
        self.assertEqual([item["id"] for item in payload["markers"]], [own_listing.id])

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_live_search_returns_expected_marker_and_card_payloads(self):
        self.user.first_name = "Casey"
        self.user.last_name = "Owner"
        self.user.profile_image_url = "https://example.com/owner-avatar.jpg"
        self.user.save(update_fields=["first_name", "last_name", "profile_image_url"])
        listing = self.create_listing(
            title="Beacon apartment",
            address="1731 Beacon St",
            price="1800.00",
            lease_type="FULL",
            property_type="house",
            rooms=3,
            bathrooms="1.5",
            sq_ft=980,
            description="Sunny apartment with updated kitchen and a short walk to campus.",
            latitude=42.3355,
            longitude=-71.1685,
        )
        ListingImage.objects.create(listing=listing, image=self.make_image_upload())
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("listings:search"),
            {
                "west": "-71.3",
                "south": "42.2",
                "east": "-71.0",
                "north": "42.5",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(
            payload["markers"],
            [
                {
                    "id": listing.id,
                    "price": "$1800",
                    "title": "Beacon apartment",
                    "lat": 42.3355,
                    "lng": -71.1685,
                    "url": reverse("listings:detail", args=[listing.pk]),
                }
            ],
        )
        self.assertEqual(len(payload["cards"]), 1)
        card = payload["cards"][0]
        self.assertEqual(card["id"], listing.id)
        self.assertEqual(card["url"], reverse("listings:detail", args=[listing.pk]))
        self.assertEqual(card["title"], "Beacon apartment")
        self.assertEqual(card["address"], "1731 Beacon St")
        self.assertEqual(card["price"], "$1800/mo")
        self.assertEqual(card["status"], {"value": "AVAILABLE", "label": "Available", "state": "available"})
        self.assertEqual(card["lease_type"], "Full Lease")
        self.assertEqual(card["property_type"], "House")
        self.assertEqual(card["rooms"], 3)
        self.assertEqual(card["bathrooms"], "1.5")
        self.assertEqual(card["sq_ft"], 980)
        self.assertEqual(card["description"], "Sunny apartment with updated kitchen and a short walk to campus.")
        self.assertEqual(card["owner_name"], "Casey Owner")
        self.assertEqual(card["owner_avatar_url"], "https://example.com/owner-avatar.jpg")
        self.assertEqual(card["image_url"], listing.primary_image.versioned_url)

    def test_live_search_does_not_add_per_listing_image_queries_for_imageless_results(self):
        for index in range(3):
            self.create_listing(
                title=f"Imageless listing {index}",
                address=f"{140 + index} Commonwealth Ave",
                latitude=42.3355 + (index * 0.0001),
                longitude=-71.1685 + (index * 0.0001),
            )
        self.client.force_login(self.user)

        with CaptureQueriesContext(connection) as captured_queries:
            response = self.client.get(
                reverse("listings:search"),
                {
                    "west": "-71.3",
                    "south": "42.2",
                    "east": "-71.0",
                    "north": "42.5",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 3)
        listing_image_queries = [query for query in captured_queries if '"listings_listingimage"' in query["sql"]]
        self.assertEqual(len(listing_image_queries), 1)
        self.assertIn(" IN (", listing_image_queries[0]["sql"])

    def test_listing_list_shows_owner_avatar(self):
        self.user.profile_image_url = "https://example.com/owner-avatar.jpg"
        self.user.save(update_fields=["profile_image_url"])
        self.create_listing()
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(response, "https://example.com/owner-avatar.jpg")

    def test_listing_list_omits_hidden_listings(self):
        visible_listing = self.create_listing(
            title="Visible listing",
            description="Visible",
            is_hidden=False,
        )
        self.create_listing(
            title="Hidden listing",
            address="200 Beacon St",
            price="1400.00",
            lease_type="SUBLEASE",
            description="Hidden",
            is_hidden=True,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(response, visible_listing.title)
        self.assertNotContains(response, "Hidden listing")

    def test_listing_list_omits_taken_and_expired_listings(self):
        today = date.today()
        visible_listing = self.create_listing(title="Visible listing")
        self.create_listing(
            title="Taken listing",
            address="200 Beacon St",
            price="1400.00",
            lease_type="SUBLEASE",
            description="Taken",
            status=Listing.STATUS_TAKEN,
        )
        self.create_listing(
            title="Expired listing",
            address="300 Beacon St",
            price="1500.00",
            lease_type="FULL",
            description="Expired",
            start_date=today - timedelta(days=90),
            end_date=today - timedelta(days=30),
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(response, visible_listing.title)
        self.assertNotContains(response, "Taken listing")
        self.assertNotContains(response, "Expired listing")

    def test_listing_list_shows_owner_avatar_when_available(self):
        listing = self.create_listing()
        SocialAccount.objects.create(
            user=self.user,
            provider="google",
            uid="google-owner",
            extra_data={"picture": "https://example.com/listing-owner.png"},
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(response, listing.owner.display_name)
        self.assertContains(response, "https://example.com/listing-owner.png")

    def test_listing_list_filters_by_price_range_and_lease_type(self):
        affordable_listing = self.create_listing(title="Affordable", price="950.00", lease_type="SUBLEASE")
        self.create_listing(title="Too cheap", address="100 Main St", price="700.00", lease_type="SUBLEASE")
        self.create_listing(title="Expensive", price="2200.00", lease_type="FULL")
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("listings:listing_list"),
            {"min_price": "900", "max_price": "1000", "lease_type": "SUBLEASE"},
        )

        self.assertContains(response, affordable_listing.title)
        self.assertNotContains(response, "Expensive")
        self.assertNotContains(response, "Too cheap")

    def test_listing_list_filters_by_search_query(self):
        matching_listing = self.create_listing(title="Beacon apartment", address="1731 Beacon St")
        self.create_listing(title="Comm Ave house", address="140 Commonwealth Ave")
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("listings:listing_list"),
            {"q": "Beacon"},
        )

        self.assertContains(response, matching_listing.title)
        self.assertNotContains(response, "Comm Ave house")

    def test_listing_list_ignores_invalid_price_filters(self):
        listing = self.create_listing(title="Beacon apartment", price="1800.00")
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("listings:listing_list"),
            {"min_price": "invalid", "max_price": "50000"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, listing.title)

    def test_listing_list_filters_by_availability_date_overlap(self):
        matching_listing = self.create_listing(
            title="September opening",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 12, 31),
        )
        self.create_listing(
            title="Ends too early",
            address="200 Main St",
            start_date=date(2026, 6, 1),
            end_date=date(2026, 8, 31),
        )
        self.create_listing(
            title="Starts too late",
            address="300 Main St",
            start_date=date(2027, 1, 1),
            end_date=date(2027, 5, 31),
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("listings:listing_list"),
            {"availability_start": "2026-09-15", "availability_end": "2026-10-15"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, matching_listing.title)
        self.assertNotContains(response, "Ends too early")
        self.assertNotContains(response, "Starts too late")

    def test_listing_list_filters_by_bedrooms_features_and_distance(self):
        matching_listing = self.create_listing(
            title="Match all filters",
            rooms=3,
            has_parking=True,
            is_furnished=True,
            has_yard=True,
            distance_to_campus="1.2",
            pet_policy="Cats allowed",
        )
        self.create_listing(
            title="Too few bedrooms",
            address="200 Main St",
            rooms=2,
            has_parking=True,
            is_furnished=True,
            has_yard=True,
            distance_to_campus="1.0",
            pet_policy="Pets allowed",
        )
        self.create_listing(
            title="No parking",
            address="300 Main St",
            rooms=3,
            has_parking=False,
            is_furnished=True,
            has_yard=True,
            distance_to_campus="1.0",
            pet_policy="Pets allowed",
        )
        self.create_listing(
            title="Not furnished",
            address="400 Main St",
            rooms=3,
            has_parking=True,
            is_furnished=False,
            has_yard=True,
            distance_to_campus="1.0",
            pet_policy="Pets allowed",
        )
        self.create_listing(
            title="No pets",
            address="450 Main St",
            rooms=3,
            has_parking=True,
            is_furnished=True,
            has_yard=True,
            distance_to_campus="1.0",
            pet_policy="",
        )
        self.create_listing(
            title="No yard",
            address="475 Main St",
            rooms=3,
            has_parking=True,
            is_furnished=True,
            has_yard=False,
            distance_to_campus="1.0",
            pet_policy="Pets allowed",
        )
        self.create_listing(
            title="Too far",
            address="500 Main St",
            rooms=3,
            has_parking=True,
            is_furnished=True,
            has_yard=True,
            distance_to_campus="3.8",
            pet_policy="Pets allowed",
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("listings:listing_list"),
            {
                "min_bedrooms": "3",
                "has_parking": "1",
                "is_furnished": "1",
                "allows_pets": "1",
                "has_yard": "1",
                "max_distance": "2.0",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, matching_listing.title)
        self.assertNotContains(response, "Too few bedrooms")
        self.assertNotContains(response, "No parking")
        self.assertNotContains(response, "Not furnished")
        self.assertNotContains(response, "No pets")
        self.assertNotContains(response, "No yard")
        self.assertNotContains(response, "Too far")

    def test_listing_page_renders_price_and_availability_dropdown_inputs(self):
        self.create_listing(title="Filter form listing")
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("listings:listing_list"),
            {
                "min_price": "1000",
                "max_price": "2000",
                "availability_start": "2026-09-01",
                "availability_end": "2026-12-31",
            },
        )

        self.assertContains(response, 'name="min_price"')
        self.assertContains(response, 'name="max_price"')
        self.assertContains(response, ">No min</option>", html=False)
        self.assertContains(response, ">No max</option>", html=False)
        self.assertContains(response, 'name="availability_start"')
        self.assertContains(response, 'value="2026-09-01"')
        self.assertContains(response, 'name="availability_end"')
        self.assertContains(response, 'value="2026-12-31"')

    def test_listing_page_renders_new_feature_filter_inputs(self):
        self.create_listing(title="Feature filter listing")
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("listings:listing_list"),
            {
                "min_bedrooms": "2",
                "min_bathrooms": "1.5",
                "has_parking": "1",
                "is_furnished": "1",
                "allows_pets": "1",
                "has_yard": "1",
                "max_distance": "1.5",
            },
        )

        self.assertContains(response, 'name="min_bedrooms"')
        self.assertContains(response, 'name="min_bathrooms"')
        self.assertContains(response, 'name="has_parking"')
        self.assertContains(response, 'name="is_furnished"')
        self.assertContains(response, 'name="allows_pets"')
        self.assertContains(response, 'name="has_yard"')
        self.assertContains(response, 'name="max_distance"')
        self.assertContains(response, 'value="2"')
        self.assertContains(response, 'value="1.5" selected', html=False)
        self.assertContains(response, 'value="1.5"')
        self.assertContains(response, "Parking")
        self.assertContains(response, "Furnished")
        self.assertContains(response, "Pets")
        self.assertContains(response, "Yard")

    def test_listing_list_is_paginated(self):
        for index in range(13):
            self.create_listing(title=f"Listing {index}")
        self.client.force_login(self.user)

        first_page = self.client.get(reverse("listings:listing_list"))
        second_page = self.client.get(reverse("listings:listing_list"), {"page": 2})

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(second_page.status_code, 200)
        self.assertNotContains(first_page, "Listing 0")
        self.assertContains(second_page, "Listing 0")

    def test_create_listing_requires_login(self):
        response = self.client.get(reverse("listings:create_listing"))

        self.assertEqual(response.status_code, 302)

    def test_create_listing_renders_for_authenticated_user(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:create_listing"))

        self.assertEqual(response.status_code, 200)

    def test_create_listing_uses_guided_wizard_flow(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:create_listing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-listing-form-wizard")
        self.assertContains(response, 'data-step-panel="0"')
        self.assertContains(response, "data-step-next")
        self.assertContains(response, "Publishing flow")

    def test_create_listing_renders_verified_address_picker_contract(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:create_listing"))

        self.assertContains(response, "data-address-picker")
        self.assertContains(response, 'data-address-picker-enabled="true"')
        self.assertContains(response, "data-address-input")
        self.assertContains(response, "data-address-token-input")
        self.assertContains(response, "data-address-suggestions")
        self.assertContains(response, "data-address-status")
        self.assertContains(response, reverse("listings:address_suggestions"))

    @override_settings(
        LISTING_GEOAPIFY_API_KEY="",
        LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
    )
    def test_create_listing_renders_blocking_address_picker_state_when_geoapify_is_unavailable(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:create_listing"))

        self.assertContains(response, 'data-address-picker-enabled="false"')
        self.assertContains(response, 'aria-disabled="true"')
        self.assertContains(
            response,
            (
                "Verified address search is unavailable right now. Listing authoring is blocked until Geoapify "
                "autocomplete is configured."
            ),
        )
        self.assertNotContains(response, reverse("listings:address_suggestions"))

    def test_edit_listing_preserves_verified_address_picker_initial_selection_contract(self):
        listing = self.create_listing(latitude=42.3355, longitude=-71.1685)
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:edit_listing", args=[listing.pk]))

        self.assertContains(response, "data-address-picker")
        self.assertContains(response, 'data-address-picker-enabled="true"')
        self.assertContains(response, f'data-initial-address="{listing.address}"')
        self.assertContains(response, 'data-address-initially-verified="true"')
        self.assertContains(response, f'data-selected-label="{listing.address}"')
        self.assertContains(response, "Keeping the saved verified address.")

    def test_address_picker_keeps_saved_edit_selection_when_address_reverts_to_original_value(self):
        module_url = (Path(__file__).resolve().parents[2] / "static/js/listings-address-picker.js").as_uri()
        script = f"""
import assert from "node:assert/strict";
import {{ createAddressPicker }} from {module_url!r};

class HTMLElement {{
    constructor() {{
        this.dataset = {{}};
        this.listeners = {{}};
        this.hidden = false;
        this.textContent = "";
        this.innerHTML = "";
    }}

    addEventListener(type, handler) {{
        this.listeners[type] = handler;
    }}

    dispatch(type) {{
        this.listeners[type]?.({{ target: this }});
    }}

    append() {{}}
}}

class HTMLInputElement extends HTMLElement {{
    constructor(value = "") {{
        super();
        this.value = value;
        this.validationMessage = "";
    }}

    setCustomValidity(message) {{
        this.validationMessage = message;
    }}

    reportValidity() {{
        return true;
    }}

    focus() {{}}
}}

globalThis.HTMLElement = HTMLElement;
globalThis.HTMLInputElement = HTMLInputElement;
globalThis.window = {{
    clearTimeout() {{}},
    setTimeout() {{
        return 1;
    }},
    location: {{ origin: "https://example.com" }},
}};

const label = "140 Commonwealth Ave, Chestnut Hill, MA 02467, US";
const pickerRoot = new HTMLElement();
pickerRoot.dataset = {{
    addressPickerEnabled: "true",
    addressSuggestionsUrl: "/listings/address-suggestions/",
    initialAddress: label,
    selectedLabel: label,
    addressInitiallyVerified: "true",
}};
const addressInput = new HTMLInputElement(label);
const tokenInput = new HTMLInputElement("");
const suggestionsNode = new HTMLElement();
const statusNode = new HTMLElement();
const formListeners = {{}};
const elements = {{
    "[data-address-picker]": pickerRoot,
    "[data-address-input]": addressInput,
    "[data-address-token-input]": tokenInput,
    "[data-address-suggestions]": suggestionsNode,
    "[data-address-status]": statusNode,
}};
const form = {{
    querySelector(selector) {{
        return elements[selector] ?? null;
    }},
    addEventListener(type, handler) {{
        formListeners[type] = handler;
    }},
}};

const picker = createAddressPicker(form);
assert.equal(picker.isSelectionComplete(), true);

addressInput.value = "15 Chiswick Rd, Brighton, MA 02135, US";
addressInput.dispatch("input");
assert.equal(picker.isSelectionComplete(), false);

addressInput.value = label;
addressInput.dispatch("input");
assert.equal(picker.isSelectionComplete(), true);
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)

    def test_authenticated_user_can_create_listing(self):
        self.client.force_login(self.user)
        payload = self.listing_payload(
            images=[self.make_image_upload()],
            utilities_estimate="90.00",
            security_deposit="1200.00",
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                response = self.client.post(reverse("listings:create_listing"), payload)

        self.assertEqual(response.status_code, 302)
        created_listing = self.user.listings.get()
        self.assertEqual(response["Location"], reverse("listings:detail", args=[created_listing.pk]))
        self.assertEqual(self.user.listings.count(), 1)
        self.assertEqual(created_listing.utilities_estimate, 90)
        self.assertEqual(created_listing.security_deposit, 1200)

    def test_created_listing_starts_pending_review(self):
        self.client.force_login(self.user)
        payload = self.listing_payload(images=[self.make_image_upload()])

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                response = self.client.post(reverse("listings:create_listing"), payload, follow=True)

        created_listing = self.user.listings.get()
        self.assertEqual(created_listing.approval_status, Listing.APPROVAL_PENDING)
        self.assertContains(response, "Listing submitted for review.")
        self.assertContains(response, "data-app-notification-stack")
        self.assertContains(response, "data-app-notification")

    def test_authenticated_user_can_create_listing_and_persist_verified_coordinates(self):
        self.client.force_login(self.user)
        payload = self.listing_payload(images=[self.make_image_upload()])

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                response = self.client.post(reverse("listings:create_listing"), payload)

        self.assertEqual(response.status_code, 302)
        created_listing = self.user.listings.get()
        self.assertAlmostEqual(created_listing.latitude, 42.3355)
        self.assertAlmostEqual(created_listing.longitude, -71.1685)

    def test_unapproved_listing_is_hidden_from_marketplace(self):
        self.client.force_login(self.user)
        approved_listing = self.create_listing(title="Approved listing")
        pending_owner = get_user_model().objects.create_user(
            username="pending-owner",
            email="pending-owner@bc.edu",
            password="test",
        )
        pending_owner.listings.create(
            title="Pending listing",
            address="10 Beacon St",
            price="1400.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            approval_status=Listing.APPROVAL_PENDING,
        )

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(response, approved_listing.title)
        self.assertNotContains(response, "Pending listing")

    def test_admin_marketplace_hides_unapproved_listings(self):
        admin = get_user_model().objects.create_user(
            username="admin-user",
            email="admin-user@bc.edu",
            password="testpass123",
            role=Role.ADMIN,
        )
        approved_listing = self.create_listing(title="Approved listing")
        self.user.listings.create(
            title="Pending listing",
            address="10 Beacon St",
            price="1400.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            approval_status=Listing.APPROVAL_PENDING,
        )
        self.user.listings.create(
            title="Rejected listing",
            address="20 Beacon St",
            price="1500.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            approval_status=Listing.APPROVAL_REJECTED,
        )
        self.client.force_login(admin)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(response, approved_listing.title)
        self.assertNotContains(response, "Pending listing")
        self.assertNotContains(response, "Rejected listing")

    def test_admin_live_search_hides_unapproved_listings_from_map_payload(self):
        admin = get_user_model().objects.create_user(
            username="admin-search",
            email="admin-search@bc.edu",
            password="testpass123",
            role=Role.ADMIN,
        )
        approved_listing = self.create_listing(title="Approved listing", latitude=42.3355, longitude=-71.1685)
        self.user.listings.create(
            title="Pending listing",
            address="10 Beacon St",
            price="1400.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            latitude=42.3356,
            longitude=-71.1684,
            approval_status=Listing.APPROVAL_PENDING,
        )
        self.user.listings.create(
            title="Rejected listing",
            address="20 Beacon St",
            price="1500.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            latitude=42.3354,
            longitude=-71.1683,
            approval_status=Listing.APPROVAL_REJECTED,
        )
        self.client.force_login(admin)

        response = self.client.get(
            reverse("listings:search"),
            {
                "west": "-71.3",
                "south": "42.2",
                "east": "-71.0",
                "north": "42.5",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual([item["id"] for item in payload["cards"]], [approved_listing.id])
        self.assertEqual([item["id"] for item in payload["markers"]], [approved_listing.id])

    def test_admin_can_still_open_pending_listing_detail_for_review(self):
        admin = get_user_model().objects.create_user(
            username="admin-detail",
            email="admin-detail@bc.edu",
            password="testpass123",
            role=Role.ADMIN,
        )
        pending_listing = self.user.listings.create(
            title="Pending listing",
            address="10 Beacon St",
            price="1400.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            approval_status=Listing.APPROVAL_PENDING,
        )
        self.client.force_login(admin)

        response = self.client.get(reverse("listings:detail", args=[pending_listing.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pending_listing.title)
        self.assertContains(response, "Pending review")

    def test_marketplace_user_can_submit_review_for_approved_listing(self):
        owner = get_user_model().objects.create_user(
            username="review-owner",
            email="review-owner@bc.edu",
            password="test",
        )
        listing = owner.listings.create(
            title="Reviewed home",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            approval_status=Listing.APPROVAL_APPROVED,
        )
        ListingConversation.objects.create(listing=listing, owner=owner, participant=self.user)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("listings:submit_review", args=[listing.pk]),
            {"rating": "5", "comment": "Actually lived here and it was great."},
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("#community"))
        review = ListingReview.objects.get(listing=listing, author=self.user)
        self.assertEqual(review.rating, 5)

    def test_invalid_review_submission_redirects_without_creating_review(self):
        owner = get_user_model().objects.create_user(
            username="invalid-review-owner",
            email="invalid-review-owner@bc.edu",
            password="test",
        )
        listing = owner.listings.create(
            title="Invalid review home",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            approval_status=Listing.APPROVAL_APPROVED,
        )
        ListingConversation.objects.create(listing=listing, owner=owner, participant=self.user)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("listings:submit_review", args=[listing.pk]),
            {"comment": "Missing a rating should not raise a server error."},
            follow=True,
        )

        self.assertRedirects(response, f"{reverse('listings:detail', args=[listing.pk])}#community")
        self.assertContains(response, "This field is required.")
        self.assertFalse(ListingReview.objects.filter(listing=listing, author=self.user).exists())

    def test_marketplace_user_needs_prior_contact_before_submitting_review(self):
        owner = get_user_model().objects.create_user(
            username="review-contact-owner",
            email="review-contact-owner@bc.edu",
            password="test",
        )
        listing = owner.listings.create(
            title="Contact gated review",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            approval_status=Listing.APPROVAL_APPROVED,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("listings:submit_review", args=[listing.pk]),
            {"rating": "4", "comment": "Trying to review without contact."},
            follow=False,
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ListingReview.objects.filter(listing=listing, author=self.user).exists())

    def test_marketplace_user_can_report_listing_once_until_resolved(self):
        owner = get_user_model().objects.create_user(
            username="report-owner",
            email="report-owner@bc.edu",
            password="test",
        )
        listing = owner.listings.create(
            title="Flagged home",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            approval_status=Listing.APPROVAL_APPROVED,
        )
        self.client.force_login(self.user)

        first_response = self.client.post(
            reverse("listings:report_listing", args=[listing.pk]),
            {"reason": ListingReport.REASON_INACCURATE, "details": "The posted details do not match the unit."},
            follow=False,
        )
        second_response = self.client.post(
            reverse("listings:report_listing", args=[listing.pk]),
            {"reason": ListingReport.REASON_SPAM, "details": "Trying again."},
            follow=True,
        )

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(ListingReport.objects.filter(listing=listing, reporter=self.user).count(), 1)
        self.assertContains(second_response, "You already have an active report on this listing.")

    def test_invalid_report_submission_redirects_without_creating_report(self):
        owner = get_user_model().objects.create_user(
            username="invalid-report-owner",
            email="invalid-report-owner@bc.edu",
            password="test",
        )
        listing = owner.listings.create(
            title="Invalid report home",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            approval_status=Listing.APPROVAL_APPROVED,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("listings:report_listing", args=[listing.pk]),
            {"reason": ListingReport.REASON_OTHER, "details": ""},
            follow=True,
        )

        self.assertRedirects(response, f"{reverse('listings:detail', args=[listing.pk])}#community")
        self.assertContains(response, "Add context so the admin team can review this report.")
        self.assertFalse(ListingReport.objects.filter(listing=listing, reporter=self.user).exists())

    def test_create_listing_rejects_submission_without_selected_signed_token(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("listings:create_listing"),
            self.listing_payload(verified_address_token=""),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "address", "Select a verified address suggestion.")
        self.assertFalse(self.user.listings.exists())

    def test_create_listing_rejects_end_date_before_start_date(self):
        self.client.force_login(self.user)
        payload = self.listing_payload(
            start_date=date(2027, 5, 31),
            end_date=date(2026, 9, 1),
        )

        response = self.client.post(reverse("listings:create_listing"), payload)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "End date must be on or after the start date.")
        self.assertEqual(self.user.listings.count(), 0)

    def test_create_listing_rejects_invalid_uploaded_image(self):
        self.client.force_login(self.user)
        payload = self.listing_payload()
        invalid_upload = SimpleUploadedFile("bad.txt", b"not an image", content_type="text/plain")

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                response = self.client.post(reverse("listings:create_listing"), {**payload, "images": invalid_upload})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload a JPG, PNG, or WebP image.")
        self.assertFalse(self.user.listings.exists())

    def test_create_listing_can_save_multiple_images(self):
        self.client.force_login(self.user)
        payload = self.listing_payload(images=[self.make_image_upload("one.png"), self.make_image_upload("two.png")])

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                response = self.client.post(reverse("listings:create_listing"), payload)

        self.assertEqual(response.status_code, 302)
        listing = self.user.listings.get()
        self.assertEqual(listing.images.count(), 2)

    def test_listing_owner_can_edit_listing(self):
        listing = self.create_listing(latitude=42.3355, longitude=-71.1685)
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                response = self.client.post(
                    reverse("listings:edit_listing", args=[listing.pk]),
                    {
                        "title": "Updated listing",
                        "address": listing.address,
                        "price": listing.price,
                        "lease_type": listing.lease_type,
                        "start_date": listing.start_date,
                        "end_date": listing.end_date,
                        "property_type": listing.property_type,
                        "description": listing.description,
                        "status": "PENDING",
                        "images": self.make_image_upload(),
                    },
                )

        listing.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("listings:detail", args=[listing.pk]))
        self.assertEqual(listing.title, "Updated listing")
        self.assertEqual(listing.status, "PENDING")

    @override_settings(
        LISTING_GEOAPIFY_API_KEY="",
        LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
    )
    def test_listing_owner_can_edit_listing_with_unchanged_address_without_token_when_lookup_is_unavailable(self):
        listing = self.create_listing(latitude=42.3355, longitude=-71.1685)
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                response = self.client.post(
                    reverse("listings:edit_listing", args=[listing.pk]),
                    {
                        "title": "Updated listing",
                        "address": listing.address,
                        "price": listing.price,
                        "lease_type": listing.lease_type,
                        "start_date": listing.start_date,
                        "end_date": listing.end_date,
                        "property_type": listing.property_type,
                        "description": listing.description,
                        "status": listing.status,
                        "images": self.make_image_upload(),
                    },
                )

        listing.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(listing.title, "Updated listing")
        self.assertEqual(listing.latitude, 42.3355)
        self.assertEqual(listing.longitude, -71.1685)

    @override_settings(
        LISTING_GEOAPIFY_API_KEY="",
        LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
    )
    def test_listing_owner_cannot_bypass_verified_address_on_unchanged_edit_without_coordinates(self):
        listing = self.create_listing(latitude=None, longitude=None)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("listings:edit_listing", args=[listing.pk]),
            {
                "title": "Updated listing",
                "address": listing.address,
                "price": listing.price,
                "lease_type": listing.lease_type,
                "start_date": listing.start_date,
                "end_date": listing.end_date,
                "property_type": listing.property_type,
                "description": listing.description,
                "status": listing.status,
            },
        )

        listing.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "address", "Verified address lookup is unavailable right now. Try again later."
        )
        self.assertEqual(listing.title, "Test listing")
        self.assertIsNone(listing.latitude)
        self.assertIsNone(listing.longitude)

    def test_listing_owner_edit_rejects_changed_freeform_address_without_reselection(self):
        listing = self.create_listing(latitude=42.3355, longitude=-71.1685)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("listings:edit_listing", args=[listing.pk]),
            {
                "title": listing.title,
                "address": "215 Commonwealth Ave",
                "verified_address_token": self.make_verified_address_token(label=listing.address),
                "price": listing.price,
                "lease_type": listing.lease_type,
                "start_date": listing.start_date,
                "end_date": listing.end_date,
                "property_type": listing.property_type,
                "description": listing.description,
                "status": listing.status,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "address",
            "Choose the updated address from the verified suggestions.",
        )

    @override_settings(
        LISTING_GEOAPIFY_API_KEY="",
        LISTING_GEOAPIFY_AUTOCOMPLETE_URL="https://api.geoapify.com/v1/geocode/autocomplete",
    )
    def test_missing_geoapify_config_blocks_authoring_instead_of_silently_falling_back(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("listings:create_listing"), self.listing_payload())

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"], "address", "Verified address lookup is unavailable right now. Try again later."
        )
        self.assertFalse(self.user.listings.exists())

    def test_listing_detail_shows_owner_avatar_when_available(self):
        listing = self.create_listing()
        SocialAccount.objects.create(
            user=self.user,
            provider="google",
            uid="google-owner-detail",
            extra_data={"picture": "https://example.com/listing-owner-detail.png"},
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:detail", args=[listing.pk]))

        self.assertContains(response, listing.owner.display_name)
        self.assertContains(response, "https://example.com/listing-owner-detail.png")

    def test_listing_detail_shows_commute_distance_from_coordinates(self):
        listing = self.create_listing(latitude=42.3477, longitude=-71.1538, distance_to_campus=None)
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:detail", args=[listing.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Commute to Boston College")
        self.assertContains(response, "Distance to campus")
        self.assertContains(response, f"{response.context['commute_distance_miles']} mi")
        self.assertContains(response, "js/listing-commute.js")

    def test_listing_detail_renders_route_map_hooks_for_mapped_listing(self):
        listing = self.create_listing(latitude=42.3477, longitude=-71.1538, distance_to_campus=None)
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:detail", args=[listing.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-listing-commute")
        self.assertContains(response, "data-commute-map")
        self.assertContains(response, "data-commute-map-note")
        self.assertContains(response, 'id="listing-commute-payload"')
        self.assertContains(response, "https://unpkg.com/maplibre-gl@5.18.0/dist/maplibre-gl.js")
        self.assertTrue(response.context["commute_map_enabled"])
        self.assertEqual(
            response.context["commute_payload"]["map"]["routing_url"], "https://api.geoapify.com/v1/routing"
        )

    def test_listing_detail_renders_gallery_hooks_when_multiple_images_exist(self):
        listing = self.create_listing()
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                ListingImage.objects.create(listing=listing, image=self.make_image_upload("detail-one.png"))
                ListingImage.objects.create(listing=listing, image=self.make_image_upload("detail-two.png"))

                response = self.client.get(reverse("listings:detail", args=[listing.pk]))

        self.assertContains(response, "data-listing-gallery")
        self.assertContains(response, "data-listing-gallery-active-image")
        self.assertContains(response, "data-listing-gallery-thumb")
        self.assertContains(response, "listing-detail-gallery-topbar")
        self.assertContains(response, "listing-detail-intro")
        self.assertContains(response, "js/listing-detail-gallery.js")

    def test_edit_listing_rejects_total_image_limit(self):
        listing = self.create_listing()
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir, LISTING_IMAGE_TOTAL_LIMIT=2):
                ListingImage.objects.create(listing=listing, image=self.make_image_upload("one.png"))
                ListingImage.objects.create(listing=listing, image=self.make_image_upload("two.png"))

                response = self.client.post(
                    reverse("listings:edit_listing", args=[listing.pk]),
                    {
                        "title": listing.title,
                        "address": listing.address,
                        "verified_address_token": self.make_verified_address_token(label=listing.address),
                        "price": listing.price,
                        "lease_type": listing.lease_type,
                        "start_date": listing.start_date,
                        "end_date": listing.end_date,
                        "property_type": listing.property_type,
                        "description": listing.description,
                        "images": self.make_image_upload("three.png"),
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Each listing can have up to 2 images total.")
        self.assertEqual(listing.images.count(), 2)

    def test_edit_listing_can_remove_existing_images(self):
        listing = self.create_listing()
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                image_one = ListingImage.objects.create(listing=listing, image=self.make_image_upload("one.png"))
                image_two = ListingImage.objects.create(listing=listing, image=self.make_image_upload("two.png"))

                response = self.client.post(
                    reverse("listings:edit_listing", args=[listing.pk]),
                    {
                        "title": listing.title,
                        "address": listing.address,
                        "verified_address_token": self.make_verified_address_token(label=listing.address),
                        "price": listing.price,
                        "lease_type": listing.lease_type,
                        "start_date": listing.start_date,
                        "end_date": listing.end_date,
                        "property_type": listing.property_type,
                        "description": listing.description,
                        "remove_images": [str(image_one.pk)],
                    },
                )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(listing.images.count(), 1)
        self.assertFalse(listing.images.filter(pk=image_one.pk).exists())
        self.assertTrue(listing.images.filter(pk=image_two.pk).exists())

    def test_listing_owner_can_delete_listing(self):
        listing = self.create_listing()
        self.client.force_login(self.user)

        response = self.client.post(reverse("listings:delete_listing", args=[listing.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("users:posts"))
        self.assertFalse(self.user.listings.filter(pk=listing.pk).exists())

    def test_delete_listing_cleans_up_image_files(self):
        listing = self.create_listing()
        self.client.force_login(self.user)

        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                listing_image = ListingImage.objects.create(
                    listing=listing, image=self.make_image_upload("cleanup.png")
                )
                stored_name = listing_image.image.name

                self.assertTrue(listing.images.exists())
                self.assertTrue(listing_image.image.storage.exists(stored_name))

                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.post(reverse("listings:delete_listing", args=[listing.pk]))

                self.assertEqual(response.status_code, 302)
                self.assertFalse(listing_image.image.storage.exists(stored_name))

    def test_realtor_listing_list_shows_only_owned_listings(self):
        realtor = get_user_model().objects.create_user(username="agent", email="agent@gmail.com", password="test")
        owned_listing = realtor.listings.create(
            title="Owned listing",
            address="10 Main St",
            price="2100.00",
            lease_type="FULL",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 5, 31),
            approval_status="approved",
        )
        self.create_listing(title="Student listing", address="20 Main St")
        self.client.force_login(realtor)

        response = self.client.get(reverse("listings:listing_list"))

        self.assertContains(response, "This account can manage its own listings only.")
        self.assertContains(response, owned_listing.title)
        self.assertNotContains(response, "Student listing")

    def test_realtor_cannot_view_other_listing_detail(self):
        realtor = get_user_model().objects.create_user(username="agent", email="agent@gmail.com", password="test")
        listing = self.create_listing()
        self.client.force_login(realtor)

        response = self.client.get(reverse("listings:detail", args=[listing.pk]))

        self.assertEqual(response.status_code, 404)

    def test_listing_owner_can_view_own_taken_listing_detail(self):
        listing = self.create_listing(status=Listing.STATUS_TAKEN)
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:detail", args=[listing.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, listing.title)

    def test_student_can_start_listing_conversation(self):
        student = get_user_model().objects.create_user(username="student", email="student@bc.edu", password="test")
        listing = self.create_listing()
        self.client.force_login(student)

        response = self.client.post(
            reverse("listings:message_listing", args=[listing.pk]),
            {"body": "Interested for fall."},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ListingConversation.objects.count(), 1)
        self.assertEqual(ListingMessage.objects.count(), 1)
        conversation = ListingConversation.objects.get()
        self.assertEqual(conversation.participant, student)
        self.assertEqual(conversation.owner, listing.owner)
        self.assertEqual(conversation.listing, listing)
        self.assertEqual(conversation.last_message_preview, "Interested for fall.")
        self.assertTrue(conversation.owner_has_unread_messages)
        self.assertFalse(conversation.participant_has_unread_messages)
        message = ListingMessage.objects.get()
        self.assertEqual(message.sender, student)
        self.assertEqual(message.body, "Interested for fall.")

    def test_student_reuses_existing_listing_conversation(self):
        student = get_user_model().objects.create_user(username="student", email="student@bc.edu", password="test")
        listing = self.create_listing()
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=listing.owner,
            participant=student,
        )
        conversation.add_message(sender=student, body="First note.")
        self.client.force_login(student)

        response = self.client.post(
            reverse("listings:message_listing", args=[listing.pk]),
            {"body": "Following up on availability."},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ListingConversation.objects.count(), 1)
        self.assertEqual(ListingMessage.objects.count(), 2)
        conversation.refresh_from_db()
        self.assertEqual(conversation.last_message_preview, "Following up on availability.")

    @override_settings(MESSAGE_SEND_RATE_LIMIT=1, MESSAGE_SEND_RATE_WINDOW_SECONDS=60)
    def test_student_message_rate_limit_blocks_follow_up_post(self):
        student = get_user_model().objects.create_user(username="student", email="student@bc.edu", password="test")
        listing = self.create_listing()
        self.client.force_login(student)
        cache.clear()

        first_response = self.client.post(
            reverse("listings:message_listing", args=[listing.pk]),
            {"body": "Interested for fall."},
            follow=False,
        )
        second_response = self.client.post(
            reverse("listings:message_listing", args=[listing.pk]),
            {"body": "Following up."},
            follow=True,
        )

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 200)
        self.assertContains(second_response, "Too many messages sent too quickly. Wait a minute and try again.")
        self.assertEqual(ListingMessage.objects.count(), 1)

    def test_realtor_cannot_start_listing_conversation(self):
        realtor = get_user_model().objects.create_user(username="agent", email="agent@gmail.com", password="test")
        listing = self.create_listing()
        self.client.force_login(realtor)

        response = self.client.post(reverse("listings:message_listing", args=[listing.pk]), {"body": "Interested."})

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ListingConversation.objects.exists())

    def test_blank_message_does_not_create_conversation(self):
        student = get_user_model().objects.create_user(username="student", email="student@bc.edu", password="test")
        listing = self.create_listing()
        self.client.force_login(student)

        response = self.client.post(reverse("listings:message_listing", args=[listing.pk]), {"body": "   "})

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ListingConversation.objects.exists())

    def test_message_endpoint_requires_post(self):
        listing = self.create_listing()
        student = get_user_model().objects.create_user(username="student", email="student@bc.edu", password="test")
        self.client.force_login(student)

        response = self.client.get(reverse("listings:message_listing", args=[listing.pk]))

        self.assertEqual(response.status_code, 405)
        self.assertFalse(ListingConversation.objects.exists())

    def test_delete_listing_endpoint_requires_post(self):
        listing = self.create_listing()
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:delete_listing", args=[listing.pk]))

        self.assertEqual(response.status_code, 405)
        self.assertTrue(self.user.listings.filter(pk=listing.pk).exists())

    def test_student_cannot_message_taken_listing(self):
        student = get_user_model().objects.create_user(username="student", email="student@bc.edu", password="test")
        listing = self.create_listing(status=Listing.STATUS_TAKEN)
        self.client.force_login(student)

        response = self.client.post(reverse("listings:message_listing", args=[listing.pk]), {"body": "Interested."})

        self.assertEqual(response.status_code, 404)
        self.assertFalse(ListingConversation.objects.exists())

    def test_admin_can_start_listing_conversation_for_public_listing(self):
        admin = get_user_model().objects.create_user(
            username="admin",
            email="admin@bc.edu",
            password="test",
            role=Role.ADMIN,
        )
        listing = self.create_listing()
        self.client.force_login(admin)

        response = self.client.post(
            reverse("listings:message_listing", args=[listing.pk]),
            {"body": "I need to follow up on this listing."},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(ListingConversation.objects.count(), 1)
        conversation = ListingConversation.objects.get()
        self.assertEqual(conversation.participant, admin)
        self.assertEqual(conversation.listing, listing)

    def test_admin_non_public_listing_post_redirects_with_error_instead_of_404(self):
        admin = get_user_model().objects.create_user(
            username="admin",
            email="admin@bc.edu",
            password="test",
            role=Role.ADMIN,
        )
        listing = self.create_listing(status=Listing.STATUS_TAKEN)
        self.client.force_login(admin)

        response = self.client.post(
            reverse("listings:message_listing", args=[listing.pk]),
            {"body": "Still available?"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This listing is no longer accepting new messages.")
        self.assertContains(response, "New conversations are closed.")
        self.assertFalse(ListingConversation.objects.exists())

    def test_listing_owner_sees_conversations_on_detail_page(self):
        listing = self.create_listing()
        student = get_user_model().objects.create_user(username="student", email="student@bc.edu", password="test")
        conversation = ListingConversation.objects.create(
            listing=listing,
            owner=listing.owner,
            participant=student,
        )
        conversation.add_message(sender=student, body="Can I tour this week?")
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:detail", args=[listing.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inquiries")
        self.assertContains(response, "Can I tour this week?")

    def test_listing_detail_shows_owner_avatar(self):
        self.user.profile_image_url = "https://example.com/owner-avatar.jpg"
        self.user.save(update_fields=["profile_image_url"])
        listing = self.create_listing()
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:detail", args=[listing.pk]))

        self.assertContains(response, "https://example.com/owner-avatar.jpg")


class GroupMatchPageTests(ListingTestCase):
    def test_group_match_requires_marketplace_access(self):
        realtor = get_user_model().objects.create_user(username="agent", email="agent@gmail.com", password="test")
        self.client.force_login(realtor)

        response = self.client.get(reverse("listings:group_match"))

        self.assertEqual(response.status_code, 403)

    def test_group_match_requires_student_access(self):
        admin = get_user_model().objects.create_user(username="admin-user", email="admin@bc.edu", password="test")
        admin.set_admin_access(True)
        admin.save()
        self.client.force_login(admin)

        response = self.client.get(reverse("listings:group_match"))

        self.assertEqual(response.status_code, 403)

    def test_group_match_page_shows_active_roommate_posts_with_score_and_message_entry(self):
        self.complete_roommate_profile(self.user)
        roommate = get_user_model().objects.create_user(
            username="match",
            email="match@bc.edu",
            password="testpass123",
            first_name="Riley",
        )
        self.complete_roommate_profile(
            roommate,
            major="Biology",
            bio="Prefers quieter nights and shared routines.",
        )
        self.create_roommate_post(author=roommate, title="Two students looking for one more in Brighton")
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:group_match"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Active posts")
        self.assertContains(response, roommate.display_name)
        self.assertContains(response, "100% match")
        self.assertContains(response, reverse("users:public_profile", args=[roommate.pk]))
        self.assertContains(response, "Message lead")

    def test_group_match_page_shows_group_owned_post_details(self):
        self.complete_roommate_profile(self.user)
        group_lead = get_user_model().objects.create_user(
            username="group-lead-board",
            email="group-lead-board@bc.edu",
            password="testpass123",
            first_name="Jordan",
        )
        group_member = get_user_model().objects.create_user(
            username="group-member-board",
            email="group-member-board@bc.edu",
            password="testpass123",
            first_name="Taylor",
        )
        self.complete_roommate_profile(group_lead, major="Economics")
        self.complete_roommate_profile(group_member, major="Finance")
        group = self.create_roommate_group(lead=group_lead, members=[group_member], name="Cleveland Circle Crew")
        self.create_group_roommate_post(group=group, title="Cleveland Circle group needs one more roommate")
        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:group_match"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cleveland Circle Crew")
        self.assertContains(response, "Led by Jordan")
        self.assertContains(response, "Taylor")
        self.assertContains(response, "View lead")

    def test_group_match_page_shows_listing_matches_for_selected_post(self):
        self.complete_roommate_profile(self.user)
        self.client.force_login(self.user)
        author = get_user_model().objects.create_user(
            username="listing-group",
            email="listing-group@bc.edu",
            password="testpass123",
        )
        self.complete_roommate_profile(author)
        post = self.create_roommate_post(
            author=author,
            current_group_size=2,
            open_spots=1,
            move_in_date=date.today() + timedelta(days=45),
        )
        matching_listing = self.create_listing(title="Matching listing", rooms=3)
        self.create_listing(title="Too small listing", rooms=1)

        response = self.client.get(reverse("listings:group_match"), {"group": post.id})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Listing matches")
        self.assertContains(response, matching_listing.title)
        self.assertNotContains(response, "Too small listing")

    def test_group_match_page_filters_posts(self):
        self.complete_roommate_profile(self.user)
        self.client.force_login(self.user)
        matching_author = get_user_model().objects.create_user(
            username="matching-group",
            email="matching-group@bc.edu",
            password="testpass123",
        )
        self.complete_roommate_profile(matching_author)
        matching_post = self.create_roommate_post(
            author=matching_author,
            title="Brighton three-person group",
            neighborhoods="Brighton, Cleveland Circle",
            budget_min="1200",
            budget_max="1600",
            open_spots=2,
            housing_status=RoommatePost.HOUSING_NEED_HOME,
            move_in_date=date.today() + timedelta(days=40),
        )
        other_author = get_user_model().objects.create_user(
            username="other-group",
            email="other-group@bc.edu",
            password="testpass123",
        )
        self.complete_roommate_profile(other_author)
        other_post = self.create_roommate_post(
            author=other_author,
            title="Already have a place in Newton",
            housing_status=RoommatePost.HOUSING_HAVE_HOME,
            neighborhoods="Newton",
            budget_min="1700",
            budget_max="2200",
            open_spots=1,
            move_in_date=date.today() + timedelta(days=90),
        )

        response = self.client.get(
            reverse("listings:group_match"),
            {
                "q": "Brighton",
                "housing_status": RoommatePost.HOUSING_HAVE_HOME,
                "max_budget": 1300,
                "open_spots_min": 2,
                "people_in_group": 2,
                "move_in_by": (date.today() + timedelta(days=60)).isoformat(),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, matching_post.title)
        self.assertNotContains(response, other_post.title)

    def test_roommates_hub_people_tab_shows_save_button_state(self):
        self.complete_roommate_profile(self.user)
        candidate = get_user_model().objects.create_user(
            username="save-candidate",
            email="save-candidate@bc.edu",
            password="testpass123",
            first_name="Casey",
        )
        self.complete_roommate_profile(candidate)
        self.client.force_login(self.user)

        initial_response = self.client.get(reverse("listings:roommates_hub"), {"tab": "people", "q": "Casey"})
        FavoriteRoommate.objects.create(user=self.user, favorite_user=candidate)
        saved_response = self.client.get(reverse("listings:roommates_hub"), {"tab": "people", "q": "Casey"})

        self.assertEqual(initial_response.status_code, 200)
        self.assertContains(initial_response, f'action="/users/favorite/{candidate.id}/"', html=False)
        self.assertFalse(initial_response.context["people_results"].object_list[0]["is_favorited"])
        self.assertEqual(saved_response.status_code, 200)
        self.assertTrue(saved_response.context["people_results"].object_list[0]["is_favorited"])

    def test_roommates_hub_people_tab_results_are_paginated(self):
        self.complete_roommate_profile(self.user)
        for index in range(13):
            candidate = get_user_model().objects.create_user(
                username=f"people-candidate-{index}",
                email=f"people-candidate-{index}@bc.edu",
                password="testpass123",
                first_name=f"Candidate{index:02d}",
            )
            self.complete_roommate_profile(candidate)

        self.client.force_login(self.user)

        response = self.client.get(reverse("listings:roommates_hub"), {"tab": "people", "page": "2"})

        self.assertEqual(response.status_code, 200)
        people_page = response.context["people_results"]
        self.assertEqual(people_page.paginator.count, 13)
        self.assertEqual(people_page.number, 2)
        self.assertEqual(len(people_page.object_list), 1)

    def test_student_can_publish_roommate_post(self):
        self.complete_roommate_profile(self.user)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("listings:save_roommate_post"),
            {
                "title": "Three students looking for one more roommate",
                "housing_status": RoommatePost.HOUSING_NEED_HOME,
                "current_group_size": 3,
                "open_spots": 1,
                "budget_min": 1100,
                "budget_max": 1500,
                "move_in_date": (date.today() + timedelta(days=50)).isoformat(),
                "neighborhoods": "Allston, Brighton",
                "description": "We want one more roommate for an August lease and a calm weeknight apartment.",
            },
        )

        self.assertRedirects(response, reverse("listings:roommates_hub") + "?tab=mypost")
        roommate_post = RoommatePost.objects.get(author=self.user)
        self.assertEqual(roommate_post.current_group_size, 3)
        self.assertTrue(roommate_post.is_active)

    def test_student_can_save_roommate_group_and_publish_group_post(self):
        group_member = get_user_model().objects.create_user(
            username="group-member-form",
            email="group-member-form@bc.edu",
            password="testpass123",
        )
        self.complete_roommate_profile(self.user)
        self.complete_roommate_profile(group_member)
        self.client.force_login(self.user)

        group_response = self.client.post(
            reverse("listings:save_roommate_group"),
            {
                "name": "South Street Search",
                "member_emails": group_member.email,
                "description": "Two students trying to lock in a quiet fall apartment.",
            },
        )

        self.assertRedirects(group_response, reverse("listings:roommates_hub") + "?tab=mypost")

        post_response = self.client.post(
            reverse("listings:save_group_roommate_post"),
            {
                "title": "South Street group looking for one more roommate",
                "housing_status": RoommatePost.HOUSING_NEED_HOME,
                "current_group_size": 99,
                "open_spots": 1,
                "budget_min": 1100,
                "budget_max": 1500,
                "move_in_date": (date.today() + timedelta(days=50)).isoformat(),
                "neighborhoods": "Allston, Brighton",
                "description": "We already have two committed roommates and want one more for a late summer lease.",
            },
        )

        self.assertRedirects(post_response, reverse("listings:roommates_hub") + "?tab=mypost")
        group_post = RoommatePost.objects.get(group__lead=self.user)
        self.assertEqual(group_post.current_group_size, 1)  # members now join via invite flow, not member_emails
        self.assertTrue(group_post.is_active)

    def test_student_can_publish_roommate_post_without_open_spots_when_still_need_home(self):
        self.complete_roommate_profile(self.user)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("listings:save_roommate_post"),
            {
                "title": "Looking for a group to join",
                "housing_status": RoommatePost.HOUSING_NEED_HOME,
                "current_group_size": 1,
                "budget_min": 1100,
                "budget_max": 1500,
                "move_in_date": (date.today() + timedelta(days=50)).isoformat(),
                "neighborhoods": "Allston, Brighton",
                "description": "I still need a place and want to find a compatible group.",
            },
        )

        self.assertRedirects(response, reverse("listings:roommates_hub") + "?tab=mypost")
        roommate_post = RoommatePost.objects.get(author=self.user)
        self.assertIsNone(roommate_post.open_spots)

    def test_roommate_post_publish_requires_open_spots_when_have_home(self):
        self.complete_roommate_profile(self.user)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("listings:save_roommate_post"),
            {
                "title": "We already have a place",
                "housing_status": RoommatePost.HOUSING_HAVE_HOME,
                "current_group_size": 2,
                "budget_min": 1100,
                "budget_max": 1500,
                "move_in_date": (date.today() + timedelta(days=50)).isoformat(),
                "neighborhoods": "Allston",
                "description": "We have housing and want to add roommates.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(RoommatePost.objects.count(), 0)
        self.assertContains(response, "Add how many open roommate spots you have.")

    def test_roommate_post_publish_requires_completed_profile(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("listings:save_roommate_post"),
            {
                "title": "Two students looking for one more roommate",
                "housing_status": RoommatePost.HOUSING_NEED_HOME,
                "current_group_size": 2,
                "open_spots": 1,
                "budget_min": 1100,
                "budget_max": 1500,
                "move_in_date": (date.today() + timedelta(days=50)).isoformat(),
                "neighborhoods": "Allston",
                "description": "We want one more roommate for a fall lease.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(RoommatePost.objects.count(), 0)
        self.assertContains(response, "Complete your roommate profile before posting for roommates.")

    def test_roommate_post_publish_rejects_past_move_in_date(self):
        self.complete_roommate_profile(self.user)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("listings:save_roommate_post"),
            {
                "title": "Two students looking for one more roommate",
                "housing_status": RoommatePost.HOUSING_NEED_HOME,
                "current_group_size": 2,
                "open_spots": 1,
                "budget_min": 1100,
                "budget_max": 1500,
                "move_in_date": (date.today() - timedelta(days=1)).isoformat(),
                "neighborhoods": "Allston",
                "description": "We want one more roommate for a fall lease.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(RoommatePost.objects.count(), 0)
        self.assertContains(response, "Move-in date must be today or later.")
        self.assertContains(response, "Fix these fields to publish your post.")

    def test_listing_owner_cannot_favorite_their_own_listing(self):
        listing = self.create_listing()
        self.client.force_login(self.user)

        response = self.client.post(reverse("listings:toggle_favorite", args=[listing.pk]))

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ListingFavorite.objects.filter(user=self.user, listing=listing).exists())
