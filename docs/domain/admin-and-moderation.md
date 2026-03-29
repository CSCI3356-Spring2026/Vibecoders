# Admin and Moderation

## Overview

Padly has two admin surfaces:

1. A custom product admin workspace under `/users/admin-*`
2. Raw Django admin under `/admin/`

The custom workspace is the primary operational surface. Raw Django admin is intentionally narrower.

## Custom Admin Workspace

### Main routes

- `/users/admin-dashboard/`
- `/users/admin-listings/`
- `/users/admin-listings/<listing_id>/`
- `/users/admin-reports/`
- `/users/admin-users/`

### Access control

- All custom admin views are wrapped by `admin_required_view`
- Only users with the Padly admin role may access them
- This is separate from Django `is_staff`

## Listing Moderation

### Queue behavior

`admin_listings_queryset()` prioritizes listings in this order:

1. pending review
2. rejected
3. approved

Secondary ordering is by most recent submission and creation timestamps.

### Admin review actions

| Action | Effect |
| --- | --- |
| Approve | Sets approved status, reviewer, review timestamps, optional notes |
| Reject | Sets rejected status, reviewer, review timestamp, clears approval timestamp |
| Delete | Hard-deletes the listing and cascades related records |

### Guardrails

- Rejections require review notes so owners know what to fix.
- Listing detail pages surface reports, reviews, and core listing metadata for context.
- Listing approval decisions are logged.

## Report Moderation

### Queue behavior

`admin_reports_queryset()` prioritizes reports by status:

1. open
2. in review
3. resolved
4. dismissed

### Report actions

Admins can change a report's status and add resolution notes.

Rules:

- closing a report as resolved or dismissed requires notes
- reopening to `open` clears prior reviewer and resolution metadata
- report updates are logged

## User Administration

### User detail surface

The admin user detail page shows:

- role and active status
- listing and file counts
- related conversations and messages
- previews of listings, files, conversations, and messages

### User actions

| Action | Guardrail |
| --- | --- |
| Grant admin | Cannot target self |
| Restore default role | Cannot target self |
| Toggle active | Cannot deactivate self |

## Raw Django Admin

Raw Django admin still exists for operational use, but it is intentionally constrained.

### Current behavior

- `CustomUserAdmin` shows role but keeps it read-only in raw admin
- `UserFileAdmin` is view-only
- listing moderation does not run through raw admin

This keeps product moderation and file lifecycle aligned with the custom workflows instead of ad hoc edits.

## Metrics and Operational Signals

The custom admin dashboard aggregates:

- total listings
- pending, approved, and rejected listing counts
- student, realtor, and admin user counts
- open and in-review report counts
- total conversations and messages

These metrics provide a lightweight operational overview without requiring separate analytics infrastructure.

## Recommended Operational Use

- Use the custom admin workspace for listing review and report handling.
- Use `set_user_role` for scripted role management.
- Treat raw Django admin as a secondary operational/debug surface, not the main product workflow.
