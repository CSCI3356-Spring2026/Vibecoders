# Security and Privacy

## Security Model Overview

Padly is a role-aware web application that handles user identity, private files, login-gated marketplace listings,
admin workflows, and realtime messaging. The primary security posture is based on:

- verified Google identity
- explicit role and access rules
- versioned legal acceptance
- server-enforced authorization
- private-file delivery through authenticated views
- cache-backed rate limits
- conservative production security defaults

## Authentication and Identity

### Controls

- Google OAuth only
- verified email required from the provider
- email-based role policy for non-admin users
- custom Allauth adapters enforce both identity validation and legal acceptance gates

### Important implications

- There is no password auth fallback to secure separately.
- Direct signup routes are intentionally disabled.
- Existing users retain identity continuity across repeated social logins.

## Authorization Boundaries

### Marketplace

- login-gated browse only shows approved listings whose owners remain active
- listing-only users do not browse the marketplace
- admins can review private listing states through the admin workspace, not the normal marketplace surface

### Messaging

- only listing participants may access or send messages in a conversation
- owners cannot message themselves
- new conversations require public, messageable listings
- existing conversations become read-only when either participant is inactive

### Reviews and reports

- reviews are student-only, approved-listing-only, and require prior conversation history
- reports are student-only and approved-listing-only
- no self-review or self-report

### Private files

- user files are not directly served from `/media/`
- owner or admin authorization is enforced in the view layer

## Session and Legal Controls

- legal acceptance is stored in the session before OAuth completes
- legal acceptance is persisted to the user record after login
- inactive accounts are logged out on their next HTTP request
- stale legal acceptance logs users out
- recent authentication is required for account deletion

## Rate Limiting

Padly uses cache-backed rate limiting for:

- login initiation
- message sending
- address autocomplete
- document library uploads
- listing reports

### Request identity

The request identifier uses client IP plus a user-agent digest. `X-Forwarded-For` is trusted only when explicitly enabled by configuration.

### Deployment caveat

Because the settings module does not currently define a shared `CACHES` backend, default rate-limit enforcement is process-local unless deployment supplies shared cache infrastructure.

## HTTP Response Hardening

### Global or near-global controls

- `X_FRAME_OPTIONS = DENY` by default
- `SECURE_CONTENT_TYPE_NOSNIFF = True`
- strict referrer policy
- HSTS in non-debug mode
- secure session and CSRF cookies in non-debug mode

### Private file responses add:

- `Cache-Control: private, no-store`
- `Cross-Origin-Resource-Policy: same-origin`
- `Referrer-Policy: no-referrer`
- `X-Robots-Tag: noindex, nofollow`

## Data Privacy Model

| Data class | Privacy expectation |
| --- | --- |
| Listing detail and public photos | Public once the listing is approved and visible |
| User document library files | Private |
| Conversation contents | Private to conversation participants |
| Admin moderation notes | Internal/admin-only |
| Legal acceptance timestamps and versions | User-account internal data |

## Security-Sensitive Patterns to Preserve

- use `safe_next_url()` for redirect targets that accept `next`
- keep private file access behind authenticated views
- keep provider-verified address selection mandatory for listing authoring
- keep websocket events tied to authenticated user groups
- publish side effects after transaction commit when consistency matters

## Known Caveats

- default development runtime is not production-hardened by infrastructure standards because it uses SQLite, local media, and in-memory channels
- blob storage cleanup is commit-aware, but upload workflows still require operational awareness around outer-transaction rollback scenarios

## Review Surfaces

If you are auditing Padly, review these files together:

- `vibecoders/settings.py`
- `users/adapters.py`
- `users/middleware.py`
- `users/views.py`
- `users/validators.py`
- `core/rate_limits.py`
- `listings/selectors.py`
- `communications/services.py`
