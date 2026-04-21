# Data Models

This reference summarizes the main persisted models and the rules that matter most for engineering decisions.

## Users App

| Model | Purpose | Key relations | Important rules |
| --- | --- | --- | --- |
| `CustomUser` | primary account model | one-to-one profiles, related listings, files, messages | email unique and normalized; role constrained to `student`, `realtor`, `moderator`, `support`, `platform_admin`; non-staff role follows email policy; deactivation and deletion lifecycle fields tracked |
| `StudentProfile` | student roommate/profile questionnaire | one-to-one to `CustomUser` | completion-oriented fields for roommate posts, compatibility, and profile setup; preserved across admin promotion for later reuse |
| `AdminProfile` | staff/realtor profile record | one-to-one to `CustomUser` | lighter profile schema than student profile; required for staff and realtor completion state |
| `SupportInvestigation` | time-boxed sensitive-access grant | belongs to subject and opening staff user | required before support/platform-admin staff can inspect private files or message previews |
| `AuditEvent` | append-only audit trail record | optional actor plus generic target reference | captures role changes, deactivations, sensitive data access, moderation actions, and account closure events |
| `UserFile` | private document library file | belongs to `CustomUser` | per-user capacity enforced; validators inspect file contents; limited to PDFs and images; storage delete happens after commit |

## Listings App

| Model | Purpose | Key relations | Important rules |
| --- | --- | --- | --- |
| `Listing` | marketplace listing plus moderation state | belongs to owner; has images, favorites, reviews, reports, conversations | owner immutable; positive price; public visibility also requires an active owner; moderation timestamps and notes tracked |
| `ListingImage` | listing photo | belongs to `Listing` | total image cap enforced; validated as real image content; delete after commit |
| `ListingFavorite` | saved listing | `user` to `listing` | unique per `(user, listing)`; owner cannot favorite own listing |
| `ListingReview` | resident review | `author` to `listing` | unique per `(listing, author)`; rating 1-5; student-only at submission time; approved-listing-only; prior conversation required |
| `ListingReport` | abuse or quality report | `reporter` to `listing` | student-only at submission time; approved-listing-only; active-report uniqueness while open or in review; reopening clears resolution metadata |
| `ListingReportUpdate` | moderator activity log entry for a report | belongs to `ListingReport`, optional actor | preserves comments and status decisions over time; supports reopen, in-review, dismiss, and listing-closed actions |
| `RoommatePost` | student-authored roommate search post | one-to-one to `CustomUser` | one post per student; requires completed student profile; captures budget, move-in, housing stage, open spots, and active/paused state |

## Communications App

| Model | Purpose | Key relations | Important rules |
| --- | --- | --- | --- |
| `ListingConversation` | thread about a listing or a roommate match | optional listing plus owner/participant | listing threads unique per `(listing, participant)`; direct threads unique per student pair and normalized into a stable owner/participant order; owner and participant cannot be same user |
| `ListingMessage` | message in conversation | belongs to conversation and sender | sender must be conversation participant; body normalized and length-limited |

## Listing State and Moderation Fields

### `Listing`

Important fields:

- ownership: `owner`
- location: `address`, `latitude`, `longitude`
- pricing: `price`, `utilities_estimate`, `parking_fee`, `security_deposit`, `application_fee`
- availability: `start_date`, `end_date`, `status`
- moderation: `approval_status`, `submitted_for_approval_at`, `reviewed_at`, `approved_at`, `reviewed_by`, `approval_notes`
- visibility: `is_hidden`

Computed helpers:

- `is_publicly_active`
- `is_approved`
- `is_pending_review`
- `is_rejected`
- `is_verified`
- `estimated_monthly_total`
- `estimated_upfront_total`

## User Profile Fields Used by Product Features

### `StudentProfile`

High-value fields used beyond simple display:

- `messy_level`
- `guest_level`
- `bedtime`
- `noise_level`
- `drink`
- `party`

These inform profile completion, compatibility scoring, and roommate-post matching.

## Conversation State Fields

### `ListingConversation`

Unread and deletion are tracked separately for owner and participant:

- `owner_has_unread_messages`
- `participant_has_unread_messages`
- `owner_deleted_at`
- `participant_deleted_at`

This enables per-user soft delete without removing the thread for the other participant.

Conversation context is typed:

- `conversation_type = listing` for listing inquiries
- `conversation_type = direct` for roommate-match chats

## Indexing Highlights

The project includes targeted indexes for:

- public listing visibility
- listing ownership and review queues
- user file access by owner and upload time
- conversation list ordering and unread state
- message thread lookup
- report queues

Read the model `Meta.indexes` sections when changing high-traffic queries.

## Schema Design Notes

- The project uses database constraints for enum-like values and core numeric/date invariants.
- Moderation state is modeled directly on the listing instead of in a separate workflow table.
- Private file access is enforced at the application layer, not by storage segmentation alone.
