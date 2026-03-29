# Local Development

## Baseline Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pre-commit install
python manage.py migrate
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

## Minimum Useful `.env`

```env
DJANGO_DEBUG=true
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

Recommended local additions:

```env
SITE_PRODUCT_NAME=Padly
SITE_COMPANY_NAME=Vibecoders
STUDENT_EMAIL_DOMAINS=bc.edu
LISTING_GEOAPIFY_API_KEY=...
```

## Local Runtime Characteristics

| Concern | Local default |
| --- | --- |
| Database | SQLite |
| Media storage | local filesystem under `media/` |
| Channel layer | in-memory |
| Secrets | stable development fallback secret if `DJANGO_SECRET_KEY` is unset and debug mode is on |
| Hosts | `127.0.0.1`, `localhost`, `testserver` in debug |

## High-Value Commands

```bash
python manage.py test
ruff check .
ruff format --check .
python manage.py makemigrations --check --dry-run
python manage.py check --deploy
python manage.py set_user_role user@bc.edu admin
```

## Working with Login Locally

### Google OAuth

- Login requires Google OAuth configuration in `.env`.
- Legal acceptance is part of the login flow.
- If you change secrets or old cookies are out of sync, clear site cookies for the local origin and sign in again.

### Admin access

Once a real user has logged in at least once, promote them with:

```bash
python manage.py set_user_role user@bc.edu admin
```

If your shell is not inheriting `DJANGO_DEBUG=true` from `.env`, set it explicitly for local command usage.

## Working with Maps Locally

### Address verification

Listing authoring requires Geoapify autocomplete when verification is enabled.

Relevant variables:

- `LISTING_GEOAPIFY_API_KEY`
- `LISTING_GEOAPIFY_AUTOCOMPLETE_URL`

### Map browsing

The map-first listing view is controlled by:

- `LISTING_MAPS_ENABLED`
- `LISTING_GEOAPIFY_MAP_STYLE_URL`
- `LISTING_MAP_SATELLITE_STYLE_URL`

If the base style is missing, the page falls back to the non-map listings view.

## Local Testing Workflow

Recommended order before handing work back:

1. run targeted tests while iterating
2. run `ruff check .`
3. run `ruff format --check .`
4. run `python manage.py test`
5. run `python manage.py makemigrations --check --dry-run` if models changed
6. run `python manage.py check --deploy` if auth, security, or deployment settings changed

## Common Local Pitfalls

- missing Google OAuth credentials leads to broken sign-in
- missing Geoapify config blocks listing authoring by design
- using production-only settings without `DJANGO_SECRET_KEY` or `CHANNEL_REDIS_URL` will fail closed
- local media and SQLite are convenient, but they do not represent production scale or failure characteristics
