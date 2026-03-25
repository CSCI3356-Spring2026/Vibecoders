# Map-First Listings Design

## Goal

Turn the listings experience into a map-first search surface, closer to Zillow or Redfin, while enforcing verified addresses during listing creation and editing so every new or updated listing is reliably mappable.

## Product Direction

The map is the primary browsing surface, not a secondary widget. Filters live at the top, the map updates automatically when filters or viewport bounds change, and the cards below the map act as the detailed companion view. Selecting a marker highlights and reveals the corresponding card without navigating away. Only clicking a card opens the listing detail page.

For listing authoring, users must choose a validated address suggestion. Freeform address entry is not accepted. The saved listing address and coordinates come from the provider-confirmed selection so that the listing can be rendered on the map immediately.

## Scope

This feature includes two tightly related parts:

1. A map-first listings browse experience with live viewport filtering and synchronized cards.
2. Verified address selection for listing creation and editing.

They ship together as one feature and one implementation plan because the browse experience depends on reliably mappable listing data.

This design does not include broader search ranking changes, saved searches, clustering analytics, commute overlays, or a SPA rewrite of the listings area.

## Existing Codebase Context

- The listings browse page is currently server-rendered by [`templates/listings/listing_list.html`](../../../templates/listings/listing_list.html) and enhanced by [`static/js/listings-map.js`](../../../static/js/listings-map.js).
- Listings access and visibility are centralized in [`listings/selectors.py`](../../../listings/selectors.py).
- Query-string filtering is centralized in [`listings/filtering.py`](../../../listings/filtering.py).
- Listing save workflows, image handling, and current geocoding hooks live in [`listings/form_services.py`](../../../listings/form_services.py).
- The listing form is implemented by [`listings/forms.py`](../../../listings/forms.py) and rendered through [`templates/listings/listing_form.html`](../../../templates/listings/listing_form.html).
- The project already uses MapLibre on the listings page, but the current implementation is a basic add-on rather than the main interaction model.

## Provider Choice

Use Geoapify for both map presentation and verified address search.

Reasons:

- It provides MapLibre-compatible `style.json` map styles, so the map can be upgraded from the current plain raster setup without changing libraries.
- It provides address autocomplete and place/geocoding APIs that fit the required “search, choose, confirm” authoring workflow.
- Its official pricing and docs indicate a free tier with API keys and commercial use support subject to attribution, which matches the requested “free and easy” direction for development and early rollout.

The design assumes an environment-managed Geoapify API key and explicit attribution where required by the selected plan.

## Feature Gating and Rollout

- `LISTING_MAPS_ENABLED` remains the top-level feature gate for the map-first browse experience.
- Verified address selection is a required part of the new listing create/edit flow once the Geoapify settings are configured.
- The older `LISTING_GEOCODING_ENABLED` path should not remain the authority for create/edit address capture. It may be retained temporarily only for legacy operational tasks such as backfill or compatibility code during rollout, but the new form flow should depend on verified address selection instead of best-effort geocoding.

### Behavior When Geoapify Is Not Configured

This feature should fail closed.

If the required Geoapify configuration is missing:

- listing create/edit pages should render a clear blocking configuration error
- the verified address picker should not attempt live requests
- form submission should fail server-side with a configuration error instead of falling back to freeform addresses or best-effort geocoding

There is no fallback authoring path once this feature lands.

### Legacy Listings Without Coordinates

For this rollout, existing listings can be treated as disposable mock data because the database will be wiped after the feature is shipped.

That means the implementation does not need a compatibility path for legacy unmappable listings, historical backfill logic, or mixed browse behavior where some visible marketplace listings lack verified coordinates. The post-rollout dataset can assume the new address-selection flow as the source of truth for mappable listings.

## Architecture

The listings page remains server-rendered on first load, preserving the current Django structure, permissions model, and SEO-friendly baseline. After initial render, it progressively enhances into a live map-first experience driven by targeted JSON endpoints.

This is not a SPA conversion. Django continues to own:

- route handling
- access control
- initial page render
- query construction and visibility rules
- form validation and persistence

Frontend JavaScript owns:

- map lifecycle and viewport state
- live fetches when filters or bounds change
- marker rendering and selection state
- card synchronization and reveal behavior
- address suggestion UX in the listing form

## Browse Experience

### Layout

The listings page is reorganized into three layers:

1. A sticky filter bar across the top of the page.
2. A large primary map directly beneath the filters.
3. A results section below the map containing listing cards.

The map must visually dominate the page. The cards are still important, but they are secondary to the map.

### Interaction Model

- Changing filters updates both map markers and cards.
- Panning or zooming the map automatically refreshes results on `moveend`.
- Map markers show listing prices directly on the marker.
- Clicking a marker selects that listing and reveals or scrolls to the matching card.
- Clicking a card is the only action that navigates to listing detail.
- The card list only shows listings that match both the active filters and the current map viewport.

### Marker Behavior

Markers are rendered as price pills rather than generic pins. The selected marker has a distinct active state. Marker design should be visually restrained and legible over the chosen basemap, with clear hover and selected states.

No popup-driven navigation is required. The marker-to-card interaction is the core behavior.

## Browse Backend Design

### Query and Selector Changes

The current listings query logic should be extended, not replaced.

- [`listings/filtering.py`](../../../listings/filtering.py) should support optional viewport bounds in addition to the existing query-string filters.
- [`listings/selectors.py`](../../../listings/selectors.py) remains the authority for who can see which listings.
- Bounds filtering should apply after access/visibility scoping, so users never get listings outside their allowed dataset.

### New Search Endpoint

Add a dedicated listings JSON endpoint under the listings app for live search updates.

The endpoint should accept:

- existing filter inputs
- west, south, east, north bounds

The endpoint should return:

- total visible count for the current filter + viewport state
- marker payloads with IDs, price labels, title, coordinates, and detail URLs
- card payloads with the fields required to render the results section below the map

Card payloads are intentionally JSON-first and client-rendered after hydration. The minimal card contract should include:

- listing ID
- detail URL
- title
- display address
- price
- status label/state
- lease type label
- property type label
- rooms
- bathrooms
- square footage when present
- short description excerpt
- primary image URL when present
- owner display name
- owner avatar URL when present

The endpoint should not return hidden or non-accessible listings, and it should reuse the same selector/filtering rules as the initial page render.

## Browse Frontend Design

### Map Rendering

Replace the current map implementation with a more structured module split, still under `static/js/`.

Recommended responsibilities:

- a page-level controller for listing search state and request orchestration
- a map module for MapLibre setup, style selection, bounds tracking, and marker rendering
- a cards module for rendering and highlighting cards
- a small shared serializer/adapter layer if needed for consistent payload handling

### State Rules

The client tracks:

- active form filters
- current map bounds
- current selected listing ID
- current request status

When filters change:

1. debounce briefly
2. fetch new results
3. redraw markers
4. redraw cards
5. clear selection if the selected listing is no longer visible

When map movement ends:

1. read the new bounds
2. fetch new results automatically
3. update markers and cards

### Progressive Enhancement

The first server-rendered page load still includes initial results and initial map payload. If JavaScript fails, the listings page should remain usable as a conventional filtered listings page.

## Map Visual Design

The current map styling is too utilitarian. The redesigned surface should feel intentional and product-grade:

- use a cleaner vector basemap rather than the current basic raster setup
- keep map chrome minimal
- use branded but restrained price-pill markers
- reduce visual noise in the surrounding panel styling
- keep listing cards understated and easy to scan

The visual target is “real-estate search application” rather than “generic embedded map”.

## Verified Address Workflow

### Authoring UX

The listing form address field becomes an address search and selection control.

Expected flow:

1. User types into the address field.
2. Suggestions are fetched from Geoapify autocomplete.
3. User selects one suggestion.
4. The UI stores the confirmed address selection in hidden fields.
5. Form submission is allowed only if a valid suggestion has been selected.

If the user edits the visible address text after selection, the stored selection becomes invalid and they must choose a suggestion again.

### Saved Address Data

The save flow must persist:

- the confirmed display address shown to users
- latitude
- longitude

The implementation may also persist lightweight provider metadata if it materially improves validation or edit-state round-tripping, but should avoid storing unnecessary third-party payloads.

### Validation Rules

- Raw typed text without a suggestion selection is invalid.
- A previously selected suggestion becomes invalid if the visible address text changes.
- Listing create and edit forms must both enforce this rule.
- New and updated listings should leave the save flow with valid coordinates.

### Server-Side Trust Model

The server must not trust raw hidden latitude/longitude fields from the browser by themselves.

The frontend should obtain suggestions from a Django-backed endpoint that proxies Geoapify results and returns a server-signed selection token for each suggestion. The signed token should encode only the minimal trusted selection payload needed for save-time validation, such as:

- normalized display address
- latitude
- longitude
- provider feature/place identifier when available
- expiration timestamp

On submit:

- the form sends the visible address plus the selected signed token
- the server verifies the token signature and expiry
- the server verifies the visible address still matches the signed selection
- only then does the save flow trust the coordinates and display address carried by the signed payload

This avoids trusting tamperable hidden inputs while also avoiding an unnecessary provider roundtrip on every save.

## Listing Save Flow Changes

[`listings/form_services.py`](../../../listings/form_services.py) remains the place for the multi-step listing save workflow.

Changes:

- replace best-effort geocoding for new/edited addresses with provider-confirmed coordinates from the selected address
- validate address selection before save
- preserve the existing transactional image-save behavior and owner immutability rules

Because the existing database will be wiped after rollout, the implementation does not need a legacy edit compatibility path for previously saved unverified addresses.

### Autocomplete Proxy Endpoint Contract

The Django-backed autocomplete endpoint should accept:

- `q`: the current user-typed address fragment

The endpoint should return:

- a `results` array
- for each result:
  - a human-readable display label
  - a secondary context label when useful
  - latitude
  - longitude
  - a signed selection token

Behavior rules:

- short or blank queries return an empty `results` array
- provider failures return an error response suitable for inline retry UX
- the endpoint should be rate-limited if needed during implementation, but the browse endpoint and autocomplete endpoint must remain distinct

This keeps address persistence, geospatial readiness, and image handling inside one coherent transactional workflow.

## Error Handling

### Browse Experience

- If a live search request fails, keep the current visible results and show an inline error state.
- Rapid filter or map changes should not leave stale results on screen; newer requests must win over older ones.
- Empty results should produce a clean empty state on both map and cards.

### Address Experience

- If autocomplete fails temporarily, show a clear inline error and allow retrying search, but do not allow freeform submission.
- If the provider returns no valid suggestions, the form stays invalid and the user must refine the address.
- If server-side validation rejects a submitted address payload, the form should re-render with a field-level error rather than silently falling back.

## Testing Strategy

Tests should be expanded in the nearest existing suites rather than creating a disconnected test structure.

### Django tests

Update or add tests in:

- [`listings/tests/test_pages.py`](../../../listings/tests/test_pages.py)
- [`listings/tests/test_models.py`](../../../listings/tests/test_models.py)

Required coverage:

- listings page renders the new map-first structure
- bounds-aware search returns only listings within the viewport
- filter + viewport combinations behave correctly
- marker/card payload endpoint respects access rules
- selecting a verified address is required on create
- selecting a verified address is required on edit
- changing the visible address after selection invalidates the submission
- successful create/edit persists provider-confirmed coordinates

### Frontend behavior coverage

Where practical in the current stack, add targeted tests for the JSON endpoint contract and the server-rendered DOM hooks the JS depends on. The JS implementation should be written so its behavior is simple enough to validate through Django responses and existing integration-style tests.

## Operational Changes

Add environment-managed settings for Geoapify integration, including:

- API key
- optional country bias or filter defaults if needed
- map style URL or style key

Development and production setup docs in the README and agent docs should be updated so the new requirements are explicit.

## Non-Goals

This feature does not include:

- saved searches
- drawing custom polygons
- map clustering analytics or heatmaps
- commute calculations
- list/map split panes that stay visible simultaneously on desktop
- migration to React or another frontend framework

## Success Criteria

The feature is successful when:

- the listings page feels map-first rather than map-adjacent
- filters and viewport changes automatically refresh the visible dataset
- markers show listing prices directly on the map
- marker selection reveals the associated card without navigation
- cards navigate to detail pages only when clicked directly
- new and edited listings require a provider-validated address selection
- newly created and updated listings consistently have valid coordinates for map rendering
