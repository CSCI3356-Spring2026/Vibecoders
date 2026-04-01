# Listings and Marketplace

## Scope

The `listings` app owns the marketplace domain:

- listing records and listing images
- verified address authoring
- list and map browsing
- favorites
- resident reviews
- listing reports
- roommate posts
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
| `RoommatePost` | One active student-authored post for finding roommates |

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

Current desktop layout:

- filter controls live above the left results column instead of spanning the whole page
- results stay on the left in a dense stacked-card rail
- the map occupies the right column and extends higher than the results list
- the map can toggle between default and satellite styles

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

### Report moderation behavior

- `resolved` closes the report and removes the listing from the public marketplace by moving the listing back to rejected moderation state
- `dismissed` closes the report without changing the listing's approved status
- reopening to `open` clears prior reviewer and resolution metadata
- moderator notes and decisions are preserved as a timeline of `ListingReportUpdate` records instead of a single overwritten field
- the admin queue defaults to active reports, while closed history remains visible on listing-level moderation detail

## Roommate Posts and Group Discovery

Route: `/listings/group-match/`

The roommate-discovery surface is now a post-based board:

- students publish one active post for their current group
- each post captures budget, move-in timing, open spots, housing stage, neighborhoods, and a freeform summary
- viewers can filter the board, see compatibility against the post lead, and jump into direct chat or the poster's profile

Legacy roommate browse now redirects into this surface from `/users/browse/`, while the main product entry point lives on the account dashboard.

### Post rules

- only students with completed roommate profiles can publish
- each student has one post record that can be updated, paused, and reactivated
- stale posts automatically fall out of the active board once the target move-in date has passed
- compatibility is computed between the viewer's completed profile and the student leading the post
- direct roommate messaging still reuses the existing direct conversation flow and only allows new outreach to students with an active roommate post

### Filter behavior

- text query covers post title, description, neighborhoods, poster identity, and major
- housing stage filters between groups that already have a place, still need one, or are flexible
- budget filtering uses the viewer's ceiling against the group's minimum stated budget
- move-in and open-spot filters trim the board without changing compatibility logic

## Important Invariants

- Listing ownership cannot be reassigned after creation.
- Price must be positive.
- Rooms must be at least 1.
- Bathrooms must be greater than 0.
- Optional monetary fields and `distance_to_campus` must be non-negative.
- Lease type, status, property type, approval status, report status, and report reason values are DB-constrained.
- Listing images are deleted from storage only after DB commit.
