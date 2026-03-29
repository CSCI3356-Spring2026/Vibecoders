# Listings and Marketplace

## Scope

The `listings` app owns the marketplace domain:

- listing records and listing images
- verified address authoring
- list and map browsing
- favorites
- resident reviews
- listing reports
- group matching
- moderation state and public visibility rules

## Listing Lifecycle

| Stage | Meaning | Publicly visible |
| --- | --- | --- |
| Draft-in-form | A bound form before persistence | No |
| Pending review | Newly created or edited listing waiting for admin action | No |
| Approved | Admin-approved listing | Yes, if also available, not hidden, and not expired |
| Rejected | Admin rejected listing with review notes | No |
| Taken or expired | Listing exists but is not actively available | No |

### Public visibility rule

A listing is public only when all of the following are true:

- `approval_status == approved`
- `status == AVAILABLE`
- `is_hidden == False`
- `end_date >= today`

This rule is enforced in `Listing.public_visibility_q()` and used by the public marketplace selectors.

## Core Models

| Model | Purpose |
| --- | --- |
| `Listing` | Primary listing entity and moderation state |
| `ListingImage` | Photo records with validation and versioned URLs |
| `ListingFavorite` | Saved-listing relationship between user and listing |
| `ListingReview` | Student-only resident review and star rating |
| `ListingReport` | Student report submitted for admin review |

See [Data Models](../reference/data-models.md) for the full reference summary.

## Authoring Flow

### Create and edit

- Routes:
  - `/listings/create/`
  - `/listings/edit/<id>/`
- Form logic:
  - `ListingForm`
  - `handle_listing_form_submission()`

### Verified address rules

- Verified address suggestions are provided by Geoapify.
- The selected suggestion is signed and posted back as `verified_address_token`.
- The server unsigns and validates the token during form cleaning.
- If Geoapify is unavailable or not configured, authoring fails closed instead of accepting a freeform fallback.
- Edits can keep the original verified address without requiring reselection when the saved address and coordinates are unchanged.

### Media rules

- At least one photo is required.
- Per-request upload count and per-listing total image limits are enforced.
- Image content is validated by extension, MIME type, file size, and actual image parsing.

## Moderation and Verification

### Submission behavior

Every create or edit triggers `listing.submit_for_approval()`, which:

- sets `approval_status` to pending
- clears prior review metadata
- records `submitted_for_approval_at`

### Approval behavior

Admin approval records:

- `reviewed_by`
- `reviewed_at`
- `approved_at`
- optional review notes

Approved listings show the verified badge in marketplace payloads and listing detail.

### Rejection behavior

- Rejections clear `approved_at`
- Rejections require review notes in the admin workspace
- Owners must edit and resubmit the listing for another review cycle

## Marketplace Browsing

### Public list and map view

Main route: `/listings/`

Server-side behavior:

- `marketplace_listings_for_user()` determines which listings a user can browse
- `apply_listing_filters()` handles text, price, lease, availability, saved-only, and optional map bounds
- `with_favorite_state()` annotates favorite state for authenticated users

Client-side behavior:

- `static/js/listings-page.js` coordinates the map and results
- `static/js/listings-map-view.js` manages MapLibre state
- `static/js/listings-results.js` renders live-search cards

### Important visibility rules

- The current `/listings/`, `/listings/search/`, and listing-detail HTTP surfaces are login-gated even though selector helpers can still produce anonymous/public querysets for shared internal use such as the landing page.
- Students and admins browse the approved public marketplace.
- Realtors see their own inventory instead of the public marketplace.
- Even admins do not see pending or rejected listings on the normal marketplace or map.

## Favorites

Favorites are available only when:

- the user is authenticated
- the user can browse the marketplace
- the listing is not owned by that user

Constraints:

- one favorite per `(user, listing)`
- no self-favoriting

## Reviews

Reviews are intentionally strict so public trust signals are tied to real renter interaction.

### Review requirements

- author must be a student user
- listing must be approved
- author cannot own the listing
- author must have previously been a conversation participant for that listing
- one review per `(listing, author)`
- rating must be between 1 and 5

## Reports

Reports let student users flag approved listings for admin review.

### Report requirements

- reporter must be a student user
- listing must be approved
- reporter cannot own the listing
- only one active open or in-review report per `(listing, reporter)`
- submissions are rate limited

### Report states

- `open`
- `in_review`
- `resolved`
- `dismissed`

## Group Match

Route: `/listings/group-match/`

The group-match surface is a live listing-inventory planner, not direct roommate-to-roommate matching. It builds scenarios from the marketplace using:

- current group size
- budget range
- cleanliness and social preference
- sleep schedule
- desired household size
- optional location keywords

The scoring model balances:

- inventory depth
- per-person price fit
- target size fit
- bathrooms-per-person comfort signal

Group match is available only to users who can browse the marketplace.

## Important Invariants

- Listing ownership cannot be reassigned after creation.
- Price must be positive.
- Rooms must be at least 1.
- Bathrooms must be greater than 0.
- Optional monetary fields and `distance_to_campus` must be non-negative.
- Lease type, status, property type, approval status, report status, and report reason values are DB-constrained.
- Listing images are deleted from storage only after DB commit.
