# AGENTS.md
Last Revised By: Hunter Scheppat -- April 1, 2026

Repository-specific instructions for AI coding agents working in this codebase.

If you use another agentic tool or delegate work to another agent, point it at this file and `README.md` first.

## 1. Purpose and Instruction Priority

This file is the operating manual for agents working in Padly.

Follow instruction priority in this order:

1. System / developer / user instructions in the active session
2. `AGENTS.md`
3. `README.md`
4. Local code patterns already present in the repository

If this file conflicts with active session instructions, obey the active session instructions.

## 2. Project Snapshot

Padly is a student housing and subletting marketplace for the Boston College community. The application is a Django 5.2 monolith with Google OAuth login, role-based access control, listing creation and search, private user-file handling, a custom admin workspace, and realtime listing conversations over Django Channels.

Current production-facing runtime apps:

- `core`: landing page, shared pages, branding, cross-app utilities
- `listings`: listing domain, forms, publishing, listing media, marketplace flows
- `communications`: inbox, conversations, websocket messaging, realtime payloads
- `users`: authentication, profile/dashboard flows, legal acceptance, private files, admin workspace
- `vibecoders`: settings, ASGI/WSGI entrypoints, root urls, websocket routing

Important repository directories:

- `templates/`: server-rendered templates organized by app
- `static/css/`: shared tokens plus page and feature stylesheets
- `static/js/`: page entrypoints and focused UI/realtime modules
- `media/`: local development uploads
- `.github/workflows/ci.yml`: CI pipeline

Present in the repository but not currently wired into `INSTALLED_APPS`:

- `geo/`
- `maps/`

Treat `geo/` and `maps/` as parked or future-facing code unless the user explicitly asks you to activate or expand them. Do not assume they are part of the live runtime.

## 3. Environment Setup

Local development setup:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pre-commit install
python manage.py migrate
```

Start the app locally:

```bash
python manage.py runserver
```

Minimum useful local `.env` values for login-enabled development:

```env
DJANGO_DEBUG=true
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

Important environment variables:

- `DJANGO_DEBUG`
- `DJANGO_SECRET_KEY`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DJANGO_TRUST_X_FORWARDED_FOR`
- `CHANNEL_REDIS_URL`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `STUDENT_EMAIL_DOMAINS`
- `SITE_PRODUCT_NAME`
- `SITE_COMPANY_NAME`
- `LEGAL_DOCUMENT_VERSION`
- `LISTING_MAPS_ENABLED`
- `LISTING_GEOAPIFY_API_KEY`
- `LISTING_GEOAPIFY_AUTOCOMPLETE_URL`
- `LISTING_GEOAPIFY_MAP_STYLE_URL`
- `LISTING_GEOCODING_ENABLED`
- `LISTING_GEOCODER_URL`
- `LISTING_GEOCODER_USER_AGENT`
- `LISTING_GEOCODER_TIMEOUT_SECONDS`

Production notes:

- When `DJANGO_DEBUG=false`, `DJANGO_SECRET_KEY` is required.
- Production realtime messaging requires `CHANNEL_REDIS_URL`.
- Production messaging must be served through `vibecoders.asgi`, not WSGI.
- Verified listing authoring fails closed when Geoapify autocomplete is not configured.
- Map-first listings require either `LISTING_GEOAPIFY_MAP_STYLE_URL` or `LISTING_GEOAPIFY_API_KEY` when `LISTING_MAPS_ENABLED=true`.
- The repo defaults to SQLite and local media; true production scale needs a real database and shared/object-backed media storage.

## 4. Commands

Primary commands:

```bash
python manage.py runserver
python manage.py migrate
python manage.py test
ruff check .
ruff format --check .
```

Useful project commands:

```bash
python manage.py set_user_role user@bc.edu admin
python manage.py makemigrations --check --dry-run
python manage.py check --deploy
```

Command guidance:

- Run `python manage.py makemigrations --check --dry-run` when you change models or constraints.
- Run `python manage.py check --deploy` when you change security-sensitive settings, middleware, auth, or deployment behavior.
- Use targeted test modules while iterating when appropriate, but run the full suite before handing work back unless the user explicitly narrows scope and time.

## 5. Required Workflow

1. Read `README.md` and this file before making architectural decisions.
2. Inspect the existing code before proposing abstractions or new structure.
3. Keep changes scoped to the user request. Do not refactor unrelated areas unless the refactor is necessary to safely complete the task.
4. Prefer extending existing patterns over inventing new ones.
5. Add or update tests when behavior changes.
6. Before finalizing, run:
   - `ruff check .`
   - `ruff format --check .`
   - `python manage.py test`
7. If you changed models, also run `python manage.py makemigrations --check --dry-run`.
8. If you changed deployment/auth/security settings, also run `python manage.py check --deploy` when feasible.
9. If any command cannot run, state that clearly in the final summary.

## 6. Repository Map

### Runtime and entrypoints

- `vibecoders/settings.py`: environment-driven configuration, security settings, Channels config
- `vibecoders/urls.py`: root HTTP routes
- `vibecoders/asgi.py`: HTTP + websocket ASGI entrypoint
- `vibecoders/routing.py`: websocket route table, currently `/ws/messages/`

### Core

- `core/views.py`: landing page, welcome redirect, legal document pages
- `core/context_processors.py`: branding values exposed to templates
- `core/utils.py`: shared pagination and redirect helpers
- `core/rate_limits.py`: cache-backed rate limiting helpers used by login and messaging

### Listings

- `listings/models.py`: listing and listing image models, visibility rules, DB constraints
- `listings/forms.py`: listing form and summary helpers
- `listings/form_services.py`: transactional listing save workflow and image handling
- `listings/group_match_service.py`: group-match defaults, compatibility decoration, and scenario assembly
- `listings/report_services.py`: report state transitions that can also change listing moderation state
- `listings/selectors.py`: listing visibility and access querysets
- `listings/views.py`: marketplace, detail, create/edit/delete, message-from-listing flow
### Communications

- `communications/models.py`: conversation and message models
- `communications/selectors.py`: inbox and conversation query helpers
- `communications/services.py`: transactional message sending, publish, read-state logic
- `communications/views.py`: inbox/detail/reply/delete HTTP flows
- `communications/consumers.py`: websocket consumer for live messaging
- `communications/forms.py`: reply form

### Users

- `users/models.py`: custom user, role logic, student/admin profiles, private user files
- `users/views.py`: login gate, dashboard/profile/files, account deletion
- `users/admin_views.py`: custom product admin workspace
- `users/adapters.py`: allauth adapters, verified-email enforcement, signup restriction
- `users/profile_images.py`: safe avatar URL extraction and sync
- `users/middleware.py`: stale legal acceptance enforcement
- `users/session_security.py`: recent-auth session tracking
- `users/signals.py`: profile sync, avatar sync, legal acceptance persistence
- `users/validators.py`: private upload validation by extension, MIME, and file contents
- `users/management/commands/set_user_role.py`: role-management command

### Frontend

- `templates/base.html`: shared layout
- `templates/includes/site_nav_links.html`: shared desktop/mobile nav links
- `templates/includes/user_avatar.html`: shared avatar partial used across navbar, profile, listings, and messages
- `static/css/base.css`: design tokens and global typography/surfaces
- `static/css/navigation.css`, `footer.css`, `forms.css`, `layout.css`, `components.css`: shared UI layers
- `static/css/home.css`, `listings.css`, `listing-form.css`, `messages-shell.css`, `messages-thread.css`, `files.css`, `auth.css`, `admin.css`, `responsive.css`: page and feature styles
- `static/js/app-notifications.js`: compact notification stack behavior
- `static/js/listing-form.js`: guided listing wizard
- `static/js/messages.js`: messages entrypoint
- `static/js/legal-review.js`: stepped legal-review flow on the login page
- `static/js/messages_dom.js`, `messages_list.js`, `messages_avatar.js`, `messages_socket.js`: live inbox UI modules

### Tests

- `core/tests/test_pages.py`
- `core/tests/test_settings.py`
- `listings/tests/`
- `users/tests/`

Messaging coverage is split across `users/tests/` and listing/page tests rather than living in a dedicated `communications/tests/` package.

## 7. Architecture and Design Patterns

### 7.1 General boundaries

- Keep views reasonably thin.
- Put queryset composition and access filtering in selectors when a query is reused.
- Put transactional workflows and side effects in services or focused helper modules.
- Keep forms responsible for validation and bound-form behavior, not websocket publishing or unrelated persistence.
- Reuse `core.utils` helpers for pagination and safe redirects instead of hand-rolling them repeatedly.

### 7.2 Query and service patterns already in use

- `listings/selectors.py`, `communications/selectors.py`, and `users/selectors.py` are the current pattern for reusable query logic.
- `communications/services.py` is the canonical place for message send/read/delete side effects and realtime publishing.
- `listings/form_services.py` is the canonical place for multi-step listing save behavior involving uploads and deletions.
- `listings/report_services.py` is the canonical place for admin report state transitions.
- `listings/group_match_service.py` is the canonical place for non-HTTP roommate-planning logic.

Prefer using or extending these modules before adding duplicate helpers in views.

### 7.3 Transactions and side effects

- Use `transaction.atomic()` for multi-row writes.
- Use `transaction.on_commit()` for side effects that must happen only after DB success.
- Existing code already uses `transaction.on_commit()` for:
  - deleting file blobs after model deletes
  - publishing websocket updates after message writes

Do not publish websocket events or delete storage blobs before the surrounding DB transaction is safely committed.

## 8. Domain Rules You Must Preserve

### 8.1 Authentication and access model

- Login is Google OAuth only. Traditional signup/password auth is intentionally disabled.
- Verified Google email is required.
- Roles are:
  - `student`
  - `realtor`
  - `admin`
- Default role is derived from the email domain in `STUDENT_EMAIL_DOMAINS`.
- Admin is the only role that bypasses the domain-derived default.
- Regular users should not have their role arbitrarily reassigned by bypassing `set_admin_access()` or the existing role policy.

If you touch login or social auth behavior, inspect:

- `users/adapters.py`
- `users/views.py`
- `users/models.py`
- `users/signals.py`
- `users/middleware.py`

### 8.2 Legal acceptance

- Users must accept Terms of Service and Privacy Policy before completing Google login.
- Legal acceptance is versioned by `LEGAL_DOCUMENT_VERSION`.
- If a user has stale legal acceptance, `CurrentLegalAcceptanceMiddleware` logs them out and sends them back through the login flow.

Do not add auth shortcuts that bypass legal acceptance.

### 8.3 Recent auth

- Account deletion is gated by recent authentication stored in session state.
- Recent auth is stamped during login flows via `users/session_security.py` and `users/signals.py`.

Do not weaken account deletion checks without explicit user approval.

### 8.4 Listings

Important invariants in `listings/models.py`:

- Listing owner is immutable after creation.
- Public listing visibility means:
  - `is_hidden=False`
  - `status=AVAILABLE`
  - `end_date >= today`
- Price must be positive.
- Room/bath counts must stay valid.
- Optional monetary fields and `distance_to_campus` must be non-negative.
- Lease/status/property type values are DB-constrained.
- Listing create/edit flows require a provider-verified address selection when Geoapify autocomplete is configured.
- Listing authoring should fail closed if Geoapify autocomplete is unavailable; do not add a freeform-address fallback.

Access rules:

- Anonymous users see public listings only.
- Students and admins can browse the marketplace.
- Realtors have listing-only access and generally operate on their own listings.
- Admins can access all listings.

If you change listing visibility or access rules, update selectors and tests together.

### 8.5 Listing images

- Listing images are validated by extension, MIME, size, and actual image contents.
- Per-request upload limit and per-listing total image limit are enforced.
- File deletion happens after commit, not immediately.

Do not bypass `ListingImage` validation or `listings/form_services.py` when changing upload flows.

### 8.6 Messaging

Important invariants in `communications/models.py` and `communications/services.py`:

- A conversation is unique per `(listing, participant)`.
- Conversation owner must match the listing owner.
- Owners cannot message themselves.
- Only conversation participants can send messages.
- Conversations support per-user soft delete via `owner_deleted_at` / `participant_deleted_at`.
- Read/unread state is tracked separately for owner and participant.
- Realtime updates are published to per-user websocket groups.

HTTP routes:

- inbox lives under `/users/messages/`

Websocket route:

- `/ws/messages/`

If you touch messaging, audit these files together:

- `templates/communications/messages.html`
- `static/css/messages-shell.css`
- `static/css/messages-thread.css`
- `static/js/messages.js`
- `static/js/messages_dom.js`
- `static/js/messages_list.js`
- `static/js/messages_avatar.js`
- `static/js/messages_socket.js`
- `communications/views.py`
- `communications/services.py`
- `communications/consumers.py`

The messages UI is contract-sensitive. If you change DOM class names or data attributes in one place, verify the JS and CSS modules still agree.

### 8.7 Avatars

- Google avatars are resolved through safe URL extraction in `users/profile_images.py`.
- Shared avatar rendering goes through `templates/includes/user_avatar.html`.
- `CustomUser.avatar_url` is the common source of truth.

If avatar rendering changes, update the shared include and only diverge when a surface truly needs a different contract.

### 8.8 Private user files

- User files are private.
- In development, only listing photos are served directly from `/media/listing_photos/...`.
- User uploads must stay behind authenticated preview/download views.
- Only images and PDFs are previewable inline.
- File responses should keep private caching behavior and `nosniff` protection.

Do not add raw template links or direct `/media/` serving for private user uploads.

## 9. Frontend System

### 9.1 Design system

The UI is based on Bootstrap 5 plus a custom token layer in `static/css/base.css`.

Current design language:

- Palette: Padly red + secondary blue + warm gold accent
- Core typography: `Instrument Sans`
- Surfaces are intentionally flat and compact rather than decorative

Current token source of truth:

```css
:root {
  --primary-600: #d9392e;
  --primary-500: #e45146;
  --primary-400: #ee7b73;
  --primary-100: #fde3e0;

  --secondary-600: #1761c2;
  --secondary-500: #2a76d2;
  --secondary-400: #5f9be4;
  --secondary-100: #deebfb;

  --accent-500: #efb444;

  --gray-900: #19212b;
  --gray-700: #495868;
  --gray-500: #667686;
  --gray-300: #d3d9df;
  --gray-100: #f4f6f8;
  --white: #ffffff;
}
```

Design expectations:

- Keep the UI professional and streamlined.
- Prefer restrained gradients and light-tint surfaces over loud glassmorphism.
- Reuse tokens instead of hard-coding colors in feature CSS.
- If you change typography or colors, change them at the token/base layer first.

### 9.2 Template structure

- Shared layout lives in `templates/base.html`.
- Shared fragments belong in `templates/includes/`.
- App templates belong in their app folders under `templates/`.
- Use template inheritance rather than duplicating shells.

### 9.3 Frontend behavior to preserve

- Listing creation/editing uses a gated multi-step wizard driven by `static/js/listing-form.js`.
- Login/legal acceptance uses a stepped embedded review flow driven by `static/js/legal-review.js`.
- Messaging uses a server-rendered baseline with progressive realtime enhancement.
- Django messages render through the compact notification stack rather than full-width status banners.
- The navbar, profile surfaces, listing cards, and messages all rely on consistent avatar markup and shared styles.

## 10. Testing Standards

- Add or update tests for user-visible or behavior-changing work.
- Cover success cases, failure cases, and edge cases.
- Prefer extending the nearest existing test module rather than creating one-off tests in random locations.

Current test organization:

- `core/tests/test_pages.py`: landing and shared pages
- `listings/tests/test_models.py`: listing invariants
- `listings/tests/test_pages.py`: listing flows and page behavior
- `listings/tests/test_management.py`: demo seed command
- `users/tests/test_models.py`: user and avatar behavior
- `users/tests/test_pages.py`: login/dashboard/files/admin/user-facing page flows
- `users/tests/test_files.py`: private file validation and access
- `users/tests/test_messages_realtime.py`: messaging + websocket behavior
- `users/tests/test_adapters.py`: allauth adapter rules
- `users/tests/test_admin.py`: custom admin behavior
- `users/tests/test_management.py`: role-management command

When changing:

- auth, roles, or legal acceptance: update `users/tests/test_adapters.py`, `users/tests/test_pages.py`, or `users/tests/test_models.py`
- uploads or media access: update `users/tests/test_files.py` or listing tests
- messaging or websockets: update `users/tests/test_messages_realtime.py` and relevant page tests
- listing visibility or invariants: update `listings/tests/test_models.py` and `listings/tests/test_pages.py`

## 11. Security and Privacy Rules

- Never commit secrets, tokens, OAuth credentials, or `.env` contents.
- Never hard-code production secrets into source files.
- Treat all user data as private.
- Do not add real personal data to tests, fixtures, screenshots, or sample content.
- Use `safe_next_url()` for redirect targets that accept a `next` parameter.
- Preserve verified-email enforcement in the Google login path.
- Preserve rate limiting on login initiation and message sending.
- Keep avatar URLs constrained to safe HTTPS URLs.
- Keep private file access behind authenticated views.

When editing security-sensitive code, inspect the surrounding system rather than changing a single file in isolation.

## 12. Code Quality Standards

- Ruff is configured in `pyproject.toml`:
  - line length `120`
  - target version `py312`
- Prefer clear, small functions over clever abstractions.
- Keep imports at the top unless there is a specific lazy-import reason.
- Do not leave placeholder comments such as `TODO later` unless the user explicitly requests them.
- Prefer explicit validation and domain rules over implicit assumptions.
- Preserve existing DB constraints when changing model behavior.
- Avoid introducing large files when a selector/service/helper split already exists.

## 13. File and Data Boundaries

Avoid editing or relying on these without a specific reason:

- `.venv/`
- `.ruff_cache/`
- `__pycache__/`
- `db.sqlite3`
- `media/` uploaded artifacts

Do not hand-edit old migrations unless the user explicitly asks or the migration has not been shared yet. Prefer adding new migrations.

## 14. Git and PR Expectations

- Do not commit directly to `main`.
- Use descriptive branches such as:
  - `feature/<short-description>`
  - `fix/<short-description>`
- Keep commits scoped and descriptive.
- Do not revert unrelated local changes you did not make.
- Never use destructive git commands unless the user explicitly requests them.
- Assume CI must pass before merge.

Current CI on pull requests to `main`:

- `ruff check .`
- `ruff format --check .`
- `python manage.py test`

## 15. Ask First vs. Do Directly

### Ask first

- Large cross-app refactors
- New dependencies
- Schema or migration changes with destructive data impact
- Activating `geo/` or `maps/` in the live runtime
- Replacing the auth model or login provider assumptions
- Major UI redesigns that go beyond the requested surface

### Do directly

- Scoped bug fixes
- Small UX and styling improvements inside the existing design system
- Test additions and targeted refactors needed to safely complete the task
- Selector/service extraction when it is the minimal clean solution to the requested change

## 16. Done Checklist

Before handing work back, confirm:

- The requested behavior is implemented.
- Architecture boundaries were respected.
- Existing domain invariants still hold.
- Tests were added or updated when behavior changed.
- `ruff check .` ran successfully, or the blocker was reported.
- `ruff format --check .` ran successfully, or the blocker was reported.
- `python manage.py test` ran successfully, or the blocker was reported.
- Model changes were checked with `python manage.py makemigrations --check --dry-run` when relevant.
- No secrets or unrelated changes were introduced.
- No private media or auth protections were accidentally weakened.
