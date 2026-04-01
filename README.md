# Padly

Padly is a student housing and subletting marketplace built by Vibecoders for the Boston College community. It combines listing creation, search, role-based access control, Google-authenticated accounts, and real-time messaging in a single Django application.

## Overview

- Google OAuth sign-in with verified-email-based role assignment
- Marketplace flows for creating, managing, browsing, and messaging about listings
- Roommate matching with compatibility profiles, household planning, and direct student-to-student chat
- Role model for `Student`, `Realtor`, and `Admin` users
- Real-time conversations between listing owners and interested renters
- Admin tooling for listing approval, report moderation, and operations
- Private user-file handling through authenticated views

## Architecture

Padly is a Django 5.2 monolith with a small number of clear app boundaries:

- `core`: landing page, shared utilities, branding context
- `listings`: listing models, forms, search, media, and publishing flows
- `communications`: inbox, conversations, websocket messaging
- `users`: authentication, profiles, dashboards, admin operations
- `templates/`: server-rendered UI organized by app
- `static/`: shared design tokens plus page-specific CSS and JavaScript

Runtime notes:

- HTTP is served by Django; websockets run through Channels
- Local development uses SQLite and an in-memory channel layer
- Production websocket delivery requires Redis and the ASGI app
- Local media is stored under `media/`

Long-form engineering and operations documentation lives under [`docs/`](docs/README.md).

## Stack

- Python 3.12+
- Django 5.2
- Django Channels + Daphne
- Django Allauth with Google provider
- Bootstrap 5 with custom CSS/JS
- SQLite by default
- Ruff for linting and formatting

## Local Setup

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/CSCI3356-Spring2026/Vibecoders.git
cd Vibecoders
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
pre-commit install
```

### 3. Create a local `.env`

At minimum, set Google OAuth credentials if you want login to work locally:

```env
DJANGO_DEBUG=true
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
```

Optional local configuration:

```env
SITE_PRODUCT_NAME=Padly
SITE_COMPANY_NAME=Vibecoders
STUDENT_EMAIL_DOMAINS=bc.edu
LISTING_GEOAPIFY_API_KEY=your-geoapify-api-key
```

### 4. Apply migrations

```bash
python manage.py migrate
```

### 5. Run the app

```bash
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

## Useful Commands

```bash
python manage.py test
ruff check .
ruff format --check .
python manage.py set_user_role user@bc.edu admin
```

`set_user_role` is useful after a real user has signed in once and needs elevated access.

## Configuration

Common environment variables:

- `DJANGO_DEBUG`: enables local debug mode
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`: required for Google sign-in
- `STUDENT_EMAIL_DOMAINS`: comma-separated student domains, defaults to `bc.edu`
- `SITE_PRODUCT_NAME` / `SITE_COMPANY_NAME`: branding
- `LEGAL_DOCUMENT_VERSION`: forces re-acceptance when legal text changes
- `LISTING_MAPS_ENABLED`: enables the map-first listings UI; if enabled without a working map style URL, the page falls back to the conventional list view with an unavailable notice
- `LISTING_GEOAPIFY_API_KEY`: required for verified address authoring and used to derive the default Geoapify map style URL
- `LISTING_GEOAPIFY_AUTOCOMPLETE_URL`: optional override for the Geoapify autocomplete endpoint
- `LISTING_GEOAPIFY_MAP_STYLE_URL`: optional MapLibre style override; if blank and `LISTING_GEOAPIFY_API_KEY` is set, Padly uses Geoapify's `positron` style automatically
- `LISTING_MAP_SATELLITE_STYLE_URL`: optional satellite style override; defaults to the built-in satellite fallback
- `LISTING_GEOCODING_ENABLED`: legacy geocoding helper toggle; verified address selection is now the create/edit source of truth
- `LISTING_GEOCODER_URL` / `LISTING_GEOCODER_USER_AGENT` / `LISTING_GEOCODER_TIMEOUT_SECONDS`: legacy geocoder controls
- `LISTING_REPORT_RATE_LIMIT` / `LISTING_REPORT_RATE_WINDOW_SECONDS`: listing-report submission burst control

Listings authoring now fails closed when Geoapify autocomplete is not configured. Users must choose a verified suggestion on create, and freeform addresses are not accepted as a fallback.

Production-only requirements:

- `DJANGO_DEBUG=false`
- `DJANGO_SECRET_KEY`
- `CHANNEL_REDIS_URL`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`

Optional proxy-aware production settings:

- `DJANGO_TRUST_X_FORWARDED_PROTO=true`
- `DJANGO_USE_X_FORWARDED_HOST=true`
- `DJANGO_TRUST_X_FORWARDED_FOR=true` only when a trusted reverse proxy sets the header

## Production Notes

- Run the ASGI app, not WSGI, when deploying realtime messaging:

```bash
daphne vibecoders.asgi:application
```

- Redis is required for production channels.
- The repo defaults to SQLite and local media storage; a real production deployment should move to a managed database and shared/object-backed media storage.
- Private user uploads are intentionally served through authenticated views, not raw `/media/` routes.

## Development Standards

- Open pull requests against `main`; do not commit directly to `main`
- CI runs `ruff check .`, `ruff format --check .`, and `python manage.py test`
- Keep changes scoped to the feature or fix being shipped

## License

See [LICENSE](LICENSE).
