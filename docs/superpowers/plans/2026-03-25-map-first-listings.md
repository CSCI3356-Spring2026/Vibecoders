# Map-First Listings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Zillow/Redfin-style map-first listings experience with live viewport filtering and verified-address listing authoring backed by Geoapify.

**Architecture:** Keep Django responsible for access control, initial rendering, and persistence while adding two focused JSON contracts: one for verified address suggestions and one for live map search results. Replace the current basic map enhancement with a map-first frontend built from small ES modules, and replace best-effort listing geocoding with a signed, provider-verified address selection flow.

**Tech Stack:** Django 5.2, Django signing utilities, Geoapify autocomplete/geocoding + vector map style, MapLibre GL JS, vanilla ES modules, Bootstrap 5, project CSS token layer, Django test runner, Ruff

---

## File Structure

**Create**

- `listings/address_provider.py`
  Geoapify HTTP client and response normalization for address suggestions.
- `listings/address_signing.py`
  Django signing helpers for trusted address-selection tokens.
- `listings/search_payloads.py`
  JSON payload builders for live map markers and results cards.
- `templates/listings/includes/listing_result_card.html`
  Shared server-rendered markup for one listing card on the map-first page.
- `static/js/listings-page.js`
  Page entrypoint that coordinates filters, map bounds, live search, and card selection.
- `static/js/listings-map-view.js`
  MapLibre setup, price-marker rendering, active-marker state, and bounds tracking.
- `static/js/listings-results.js`
  Card rendering, selected-card state, and marker-to-card reveal behavior.
- `static/js/listings-address-picker.js`
  Verified address search UI, suggestion menu, signed-token wiring, and invalidation on text edits.

**Modify**

- `vibecoders/settings.py`
  Geoapify config and fail-closed authoring settings.
- `listings/urls.py`
  Add live search and address autocomplete endpoints.
- `listings/views.py`
  Add JSON endpoints and expand the listings page context for the map-first frontend.
- `listings/filtering.py`
  Add viewport-bounds filtering on top of existing query-string filters.
- `listings/selectors.py`
  Provide the base queryset used by map-first search without weakening access rules.
- `listings/forms.py`
  Add hidden verified-address fields, server-side token validation, and no-freeform rules.
- `listings/form_services.py`
  Use verified address coordinates instead of best-effort geocoding during save.
- `listings/geocoding.py`
  Remove its create/edit authority and leave only non-authoring helper behavior if anything still uses it.
- `templates/listings/listing_list.html`
  Rebuild into sticky top filters, dominant map, and cards-below layout.
- `templates/listings/listing_form.html`
  Add verified address picker hooks and blocking config/error states.
- `static/js/listing-form.js`
  Integrate the new address picker into the existing wizard flow.
- `static/js/listings-map.js`
  Replace or reduce to a compatibility shim that delegates to the new entrypoint.
- `static/css/listings.css`
  Redesign the listings page into a map-first surface and add price-marker/card states.
- `README.md`
  Document Geoapify setup and the required env vars.
- `AGENTS.md`
  Update repo-specific setup/config guidance for Geoapify-backed listings.
- `listings/tests/test_pages.py`
  Page, endpoint, form, and access regression coverage for the feature.
- `listings/tests/test_models.py`
  Signed-token/provider normalization coverage and any remaining save-flow unit tests.

**No schema change planned**

- Keep the existing `Listing.address`, `Listing.latitude`, and `Listing.longitude` fields.
- Do not introduce model fields unless a failing test proves the signed-token-only flow is insufficient.

**Feature gate rule**

- `LISTING_MAPS_ENABLED=False` should keep the conventional listings page usable and suppress the live map-first UI contract.
- The live search JSON endpoint may still exist for code simplicity, but the server-rendered page should not initialize the map controller when the feature gate is off.

### Task 1: Geoapify Config And Trusted Address Primitives

**Files:**
- Create: `listings/address_provider.py`
- Create: `listings/address_signing.py`
- Modify: `vibecoders/settings.py`
- Test: `listings/tests/test_models.py`

- [ ] **Step 1: Write the failing tests**

Add tests in `listings/tests/test_models.py` for:
- Geoapify settings fail-closed behavior when the API key is missing
- signed token round-trip for a normalized address selection payload
- expired or tampered token rejection
- provider response normalization into a minimal suggestion shape

Example test shape:

```python
def test_verify_address_selection_rejects_tampered_token(self):
    token = sign_address_selection(
        {
            "label": "140 Commonwealth Ave, Chestnut Hill, MA 02467",
            "lat": 42.3355,
            "lng": -71.1685,
        }
    )

    with self.assertRaises(SignatureExpired):
        verify_address_selection(f"{token}tampered")
```

- [ ] **Step 2: Run the targeted tests to verify RED**

Run:

```bash
python manage.py test listings.tests.test_models
```

Expected:
- FAIL because the new signing/provider helpers and config behavior do not exist yet

- [ ] **Step 3: Implement the minimal backend primitives**

Implement:
- Geoapify settings in `vibecoders/settings.py`, e.g.:

```python
GEOAPIFY_API_KEY = os.getenv("GEOAPIFY_API_KEY", "").strip()
GEOAPIFY_AUTOCOMPLETE_URL = "https://api.geoapify.com/v1/geocode/autocomplete"
GEOAPIFY_MAP_STYLE_URL = os.getenv(
    "GEOAPIFY_MAP_STYLE_URL",
    f"https://maps.geoapify.com/v1/styles/osm-bright/style.json?apiKey={GEOAPIFY_API_KEY}",
).strip()
```

- signing helpers using Django signing utilities, e.g.:

```python
from django.core import signing

def sign_address_selection(payload):
    return signing.dumps(payload, salt="listings.address-selection")
```

- Geoapify normalization helpers that return only the fields the app needs

- [ ] **Step 4: Run the tests to verify GREEN**

Run:

```bash
python manage.py test listings.tests.test_models
```

Expected:
- PASS for the new signing/provider coverage

- [ ] **Step 5: Commit**

```bash
git add vibecoders/settings.py listings/address_provider.py listings/address_signing.py listings/tests/test_models.py
git commit -m "feat: add trusted address primitives"
```

### Task 2: Verified Address Endpoint And Authoring Validation

**Files:**
- Modify: `listings/urls.py`
- Modify: `listings/views.py`
- Modify: `listings/forms.py`
- Modify: `listings/form_services.py`
- Modify: `templates/listings/listing_form.html`
- Test: `listings/tests/test_pages.py`

- [ ] **Step 1: Write the failing tests**

Add endpoint and form tests in `listings/tests/test_pages.py` for:
- address autocomplete endpoint returns signed suggestions for a valid query
- blank/short query returns an empty results list
- autocomplete provider failure returns a retry-friendly inline error contract
- create listing rejects submission without a selected signed token
- edit listing rejects changed freeform address text without reselection
- missing Geoapify config blocks authoring instead of silently falling back

Example test shape:

```python
def test_create_listing_requires_verified_address_selection(self):
    self.client.force_login(self.user)

    response = self.client.post(
        reverse("listings:create_listing"),
        {
            "title": "Verified only",
            "address": "140 Commonwealth Ave",
            "price": "1200.00",
            "start_date": "2026-09-01",
            "end_date": "2027-05-31",
            "description": "Close to campus.",
        },
    )

    self.assertEqual(response.status_code, 200)
    self.assertFormError(response, "form", "address", "Select a verified address suggestion.")
```

- [ ] **Step 2: Run the targeted tests to verify RED**

Run:

```bash
python manage.py test listings.tests.test_pages.ListingPageTests
```

Expected:
- FAIL because the endpoint, hidden verified-address fields, and fail-closed form rules do not exist yet

- [ ] **Step 3: Implement the minimal verified-address backend flow**

Implement:
- `listings:address_suggestions` JSON route in `listings/urls.py`
- a view in `listings/views.py` that proxies Geoapify autocomplete, normalizes results, and attaches signed tokens
- hidden form fields in `listings/forms.py`, with the signed token as the only authoritative hidden value, e.g.:

```python
verified_address_token = forms.CharField(required=False, widget=forms.HiddenInput())
```

- form `clean()` logic that:
  - requires a valid signed token
  - verifies the visible address still matches the signed payload
  - stores trusted coordinates in `cleaned_data`
- save-flow changes in `listings/form_services.py` that set `listing.address`, `listing.latitude`, and `listing.longitude` from the verified selection instead of `geocode_listing_address()`
- remove create/edit reliance on `listings/geocoding.py`; if that module remains, narrow it to explicit non-authoring helper usage only

- [ ] **Step 4: Run the tests to verify GREEN**

Run:

```bash
python manage.py test listings.tests.test_pages.ListingPageTests
```

Expected:
- PASS for the verified-address endpoint and create/edit validation coverage

- [ ] **Step 5: Commit**

```bash
git add listings/urls.py listings/views.py listings/forms.py listings/form_services.py templates/listings/listing_form.html listings/tests/test_pages.py
git commit -m "feat: require verified listing addresses"
```

### Task 3: Bounds-Aware Listings Search Backend

**Files:**
- Create: `listings/search_payloads.py`
- Modify: `listings/filtering.py`
- Modify: `listings/selectors.py`
- Modify: `listings/views.py`
- Modify: `listings/urls.py`
- Test: `listings/tests/test_pages.py`

- [ ] **Step 1: Write the failing tests**

Add tests in `listings/tests/test_pages.py` for:
- live search endpoint filters by viewport bounds
- viewport filtering combines correctly with query, price, lease type, and availability filters
- endpoint respects the current user’s access rules
- endpoint returns the expected marker/card payload structure
- `LISTING_MAPS_ENABLED=False` suppresses the map-first page contract

Example test shape:

```python
def test_live_search_filters_results_to_current_bounds(self):
    inside = self.create_listing(title="Inside", latitude=42.3355, longitude=-71.1685)
    self.create_listing(title="Outside", latitude=42.0, longitude=-71.9)
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
    self.assertEqual([item["id"] for item in payload["cards"]], [inside.id])
```

- [ ] **Step 2: Run the targeted tests to verify RED**

Run:

```bash
python manage.py test listings.tests.test_pages.ListingPageTests
```

Expected:
- FAIL because the live search endpoint and bounds filtering do not exist yet

- [ ] **Step 3: Implement the minimal live-search backend**

Implement:
- viewport bounds parsing in `listings/filtering.py`
- selector usage that starts from the same access-controlled queryset as the page
- JSON builders in `listings/search_payloads.py`, e.g.:

```python
def listing_marker_payload(listing):
    return {
        "id": listing.id,
        "price": f"${listing.price:.0f}",
        "lat": round(float(listing.latitude), 6),
        "lng": round(float(listing.longitude), 6),
    }
```

- `listings:search` JSON route/view returning:
  - `total`
  - `markers`
  - `cards`

- [ ] **Step 4: Run the tests to verify GREEN**

Run:

```bash
python manage.py test listings.tests.test_pages.ListingPageTests
```

Expected:
- PASS for bounds-aware live search coverage

- [ ] **Step 5: Commit**

```bash
git add listings/search_payloads.py listings/filtering.py listings/selectors.py listings/views.py listings/urls.py listings/tests/test_pages.py
git commit -m "feat: add live listings search endpoint"
```

### Task 4: Map-First Listings Shell And Styling

**Files:**
- Create: `templates/listings/includes/listing_result_card.html`
- Modify: `templates/listings/listing_list.html`
- Modify: `static/css/listings.css`
- Test: `listings/tests/test_pages.py`

- [ ] **Step 1: Write the failing tests**

Add DOM-focused tests in `listings/tests/test_pages.py` for:
- sticky filter shell exists at the top of the listings page
- the map root is the dominant primary surface and exposes the data hooks the new JS needs
- cards render below the map with data attributes for selection and detail navigation
- page no longer depends on popup links for listing navigation
- page exposes an empty-state container for zero results
- page exposes an inline live-search error container

Example test shape:

```python
def test_listing_page_renders_map_first_layout_hooks(self):
    self.create_listing(title="Mapped", latitude=42.3355, longitude=-71.1685)
    self.client.force_login(self.user)

    response = self.client.get(reverse("listings:listing_list"))

    self.assertContains(response, "data-listings-page")
    self.assertContains(response, "data-listings-filters")
    self.assertContains(response, "data-listings-map")
    self.assertContains(response, "data-listings-results")
```

- [ ] **Step 2: Run the targeted tests to verify RED**

Run:

```bash
python manage.py test listings.tests.test_pages.ListingPageTests
```

Expected:
- FAIL because the map-first layout hooks and card structure are not in the template yet

- [ ] **Step 3: Implement the minimal server-rendered shell**

Implement:
- a map-first `listing_list.html` layout with:
  - sticky top filter row
  - dominant map panel
  - results summary + cards below the map
  - inline live-search error region
  - clean empty-state region for zero viewport results
- a reusable card include for initial server render
- updated `static/css/listings.css` for:
  - cleaner map framing
  - denser, scannable cards
  - selected card state
  - restrained real-estate-app visual hierarchy

- [ ] **Step 4: Run the tests to verify GREEN**

Run:

```bash
python manage.py test listings.tests.test_pages.ListingPageTests
```

Expected:
- PASS for the map-first page shell coverage

- [ ] **Step 5: Commit**

```bash
git add templates/listings/includes/listing_result_card.html templates/listings/listing_list.html static/css/listings.css listings/tests/test_pages.py
git commit -m "feat: rebuild listings page around the map"
```

### Task 5: Live Map Controller, Price Markers, And Card Synchronization

**Files:**
- Create: `static/js/listings-page.js`
- Create: `static/js/listings-map-view.js`
- Create: `static/js/listings-results.js`
- Modify: `templates/listings/listing_list.html`
- Modify: `static/js/listings-map.js`
- Test: `listings/tests/test_pages.py`

- [ ] **Step 1: Write the failing tests**

Add page-contract tests in `listings/tests/test_pages.py` for:
- initial JSON payload hooks are embedded in the listings page
- the page exposes search endpoint URLs and initial state to the JS controller
- cards expose the selected/detail click contract expected by the JS
- the page exposes the live-search error and empty-state hooks expected by the controller

Example test shape:

```python
def test_listing_page_exposes_live_search_contract(self):
    self.create_listing(title="Mapped", latitude=42.3355, longitude=-71.1685)
    self.client.force_login(self.user)

    response = self.client.get(reverse("listings:listing_list"))

    self.assertContains(response, reverse("listings:search"))
    self.assertContains(response, "data-live-search-url")
    self.assertContains(response, "data-selected-listing-id")
```

- [ ] **Step 2: Run the targeted tests to verify RED**

Run:

```bash
python manage.py test listings.tests.test_pages.ListingPageTests
```

Expected:
- FAIL because the new JS contract and controller entrypoint are not wired in yet

- [ ] **Step 3: Implement the minimal live frontend**

Implement:
- `static/js/listings-page.js` to:
  - read filters and bounds
  - debounce requests
  - fetch `listings:search`
  - ensure newer requests win over older responses
  - keep current results visible on failed search requests
  - write inline error state on failed search requests
  - toggle empty-state visibility when zero results are returned
  - hand off marker/card updates
- `static/js/listings-map-view.js` to:
  - initialize MapLibre with the Geoapify style URL
  - render price-pill HTML markers
  - trigger fetches on `moveend`
  - highlight the selected marker
- `static/js/listings-results.js` to:
  - render cards from JSON
  - reveal/highlight the card matching a clicked marker
  - navigate only on direct card click
- reduce `static/js/listings-map.js` to a compatibility shim or replace the template entrypoint with `listings-page.js`

- [ ] **Step 4: Run the tests to verify GREEN**

Run:

```bash
python manage.py test listings.tests.test_pages.ListingPageTests
```

Expected:
- PASS for the server-rendered JS contract tests

- [ ] **Step 5: Commit**

```bash
git add static/js/listings-page.js static/js/listings-map-view.js static/js/listings-results.js static/js/listings-map.js templates/listings/listing_list.html listings/tests/test_pages.py
git commit -m "feat: add live map search interactions"
```

### Task 6: Address Picker Frontend, Docs, And Final Verification

**Files:**
- Create: `static/js/listings-address-picker.js`
- Modify: `static/js/listing-form.js`
- Modify: `templates/listings/listing_form.html`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Test: `listings/tests/test_pages.py`

- [ ] **Step 1: Write the failing tests**

Add tests in `listings/tests/test_pages.py` for:
- listing form renders the address-picker hooks and suggestion container
- missing Geoapify config renders the blocking message
- edit form preserves the verified-address UI contract
- autocomplete endpoint failure contract can be surfaced by the frontend without allowing freeform fallback

Example test shape:

```python
def test_listing_form_renders_verified_address_picker(self):
    self.client.force_login(self.user)

    response = self.client.get(reverse("listings:create_listing"))

    self.assertContains(response, "data-address-picker")
    self.assertContains(response, "data-address-suggestions")
```

- [ ] **Step 2: Run the targeted tests to verify RED**

Run:

```bash
python manage.py test listings.tests.test_pages.ListingPageTests
```

Expected:
- FAIL because the address-picker frontend hooks and config messaging are not complete yet

- [ ] **Step 3: Implement the minimal UI integration and docs**

Implement:
- `static/js/listings-address-picker.js` to:
  - fetch `listings:address_suggestions`
  - render suggestions
  - store the chosen signed token in hidden fields
  - clear stored selection when the user edits the visible address
  - surface retry-friendly inline errors when suggestion fetches fail
- `static/js/listing-form.js` integration so the wizard treats verified address selection as required progress
- README/AGENTS updates documenting:
  - `GEOAPIFY_API_KEY`
  - optional map style URL override
  - fail-closed authoring expectations

- [ ] **Step 4: Run focused verification**

Run:

```bash
python manage.py test listings.tests.test_pages.ListingPageTests
python manage.py test listings.tests.test_models
```

Expected:
- PASS for the form and helper coverage

- [ ] **Step 5: Run full repository verification**

Run:

```bash
ruff check .
ruff format --check .
python manage.py test
python manage.py check
python manage.py makemigrations --check --dry-run
```

Expected:
- all commands PASS
- `makemigrations --check --dry-run` reports no changes

- [ ] **Step 6: Commit**

```bash
git add static/js/listings-address-picker.js static/js/listing-form.js templates/listings/listing_form.html README.md AGENTS.md listings/tests/test_pages.py listings/tests/test_models.py
git commit -m "feat: finish map-first listings and verified address flow"
```
