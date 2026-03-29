# Code Organization

## Repository Layout

| Path | Purpose |
| --- | --- |
| `vibecoders/` | Settings, URL root, ASGI/WSGI entrypoints, websocket routing |
| `core/` | Landing page, legal pages, shared helpers, rate limits, branding context |
| `users/` | Custom user model, auth integration, dashboard, profiles, files, admin workspace |
| `listings/` | Listing models, forms, selectors, moderation, maps, reviews, reports |
| `communications/` | Inbox, messages, selectors, services, websocket consumer |
| `templates/` | Server-rendered templates grouped by app plus shared includes |
| `static/css/` | Token layer plus shared and page-specific stylesheets |
| `static/js/` | Focused browser modules for page behavior and realtime enhancement |
| `core/tests/`, `listings/tests/`, `users/tests/` | Behavioral and regression test suites |

## Architectural Patterns

### Views stay thin

Views are responsible for:

- request/response wiring
- auth decorators
- binding forms
- choosing templates or JSON responses
- passing work into selectors, model methods, or service functions

### Selectors own reusable queryset composition

Examples:

- `listings/selectors.py`
- `communications/selectors.py`
- `users/selectors.py`

Put reusable access rules or annotated query behavior there instead of rebuilding filters inline.

### Services own transactional side effects

Examples:

- `listings/form_services.py` handles multi-step listing save and image work
- `communications/services.py` owns conversation creation, reply delivery, unread state, and websocket publishing

When multiple rows change together or post-commit effects matter, the logic belongs in a service or focused helper.

### Forms own validation and bound-form behavior

Examples:

- `users/forms.py` handles profile and legal review form validation
- `listings/forms.py` handles verified address selection, image limits, review/report forms, and group-match preferences

Forms are the right place for user-input validation, not websocket dispatch or unrelated persistence logic.

## Template and Frontend Organization

| Layer | Files |
| --- | --- |
| Shared shell | `templates/base.html`, `templates/includes/` |
| Auth shell | `templates/auth/base.html`, `templates/users/login.html` |
| Listings UI | `templates/listings/*`, `static/css/listings.css`, `static/js/listings-*.js` |
| Messaging UI | `templates/communications/messages.html`, `static/css/messages-*.css`, `static/js/messages*.js` |
| Dashboard/admin/files | `templates/users/*`, `static/css/dashboard.css`, `admin.css`, `files.css` |

The frontend is primarily server-rendered. JavaScript is used for progressive enhancement rather than replacing template output wholesale.

## Key Extension Points

| Area | Extend Here First |
| --- | --- |
| Login and identity policy | `users/adapters.py`, `users/legal.py`, `users/middleware.py`, `users/session_security.py` |
| Marketplace visibility | `listings/selectors.py`, `listings/models.py`, `listings/filtering.py` |
| Listing authoring | `listings/forms.py`, `listings/form_services.py`, `static/js/listing-form.js`, `static/js/listings-address-picker.js` |
| Messaging behavior | `communications/services.py`, `communications/selectors.py`, `communications/consumers.py` |
| Admin moderation | `users/admin_views.py`, `users/selectors.py`, `listings/forms.py` |
| Private file handling | `users/models.py`, `users/views.py`, `users/validators.py`, `users/tests/test_files.py` |

## Patterns to Preserve

- Use `transaction.atomic()` around multi-row writes.
- Use `transaction.on_commit()` for websocket publishing or storage cleanup.
- Use `safe_next_url()` for any redirect target that accepts `next`.
- Keep raw Django admin secondary to the custom admin workspace for product operations.
- Prefer updating the nearest existing test module rather than creating ad hoc test locations.

## Runtime vs. Non-Documentation Sources of Truth

| Source | Intended Use |
| --- | --- |
| Root `README.md` | External-facing setup and project overview |
| Root `AGENTS.md` | Repository-specific operating instructions for coding agents |
| `/docs` | Long-form engineering, operations, and reference documentation |
| The codebase | Final source of truth for behavior when docs drift |

## Common Mistakes to Avoid

- Reimplementing access rules directly inside views instead of using selectors.
- Writing storage-deletion side effects before transaction commit.
- Adding direct `/media/` links for private files.
- Bypassing verified address selection in listing authoring.
- Treating the admin role as equivalent to raw Django admin permissions on every surface.
