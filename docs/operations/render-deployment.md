# Deploying Padly on Render

This is the Render-specific deployment runbook for Padly as the repository is currently implemented.

## Bottom Line

Padly is now set up for a conventional Render deployment with:

- a Render PostgreSQL database wired through `DATABASE_URL`
- a Render Key Value instance used for both channels and shared cache
- WhiteNoise for production static files
- a checked-in `build.sh`
- a pinned Python version via `.python-version` and `PYTHON_VERSION`
- a checked-in `render.yaml`
- ephemeral filesystem media storage under `/tmp/padly-media`

The remaining operational caveat is deliberate: uploaded media is functional for demos and active sessions, but files stored under `/tmp/padly-media` are not durable across service restarts or redeploys.

## What Was Added to the Repo

Relevant deployment files now in source control:

- [`/.python-version`](../../.python-version)
- [`/build.sh`](../../build.sh)
- [`/start.sh`](../../start.sh)
- [`/render.yaml`](../../render.yaml)
- [`/vibecoders/settings.py`](../../vibecoders/settings.py)
- [`/vibecoders/urls.py`](../../vibecoders/urls.py)

Important runtime changes:

- `psycopg[binary]` is a runtime dependency, so Render Postgres works out of the box.
- WhiteNoise is enabled immediately after `SecurityMiddleware`.
- Production static files use `whitenoise.storage.CompressedManifestStaticFilesStorage`.
- `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` fall back to Render's `RENDER_EXTERNAL_HOSTNAME` and `RENDER_EXTERNAL_URL` when the explicit Django variables are blank.
- Listing photos and uploaded avatars are served through narrow Padly routes instead of a blanket production `/media/` file server.

## Recommended Render Architecture

Use:

- `1` Render web service for the Django ASGI app
- `1` Render PostgreSQL instance
- `1` Render Key Value instance
- no persistent disk

Padly's checked-in Blueprint uses:

- web service name: `padly-web`
- database name: `padly-db`
- key value name: `padly-kv`
- media root: `/tmp/padly-media`

## Why the Media Strategy Looks Like This

Padly has three different media classes:

- listing photos
- uploaded avatars
- private user document-library files

Those do not all share the same delivery rules.

### Listing photos

Listing photos are reachable at `/media/listing_photos/<path>`, but Padly resolves the `ListingImage` record first and then applies listing-detail visibility rules before opening the file.

That means:

- anonymous users can fetch images for public listings
- owners and admins can fetch non-public listing images they are allowed to see
- unrelated users cannot fetch pending, archived, or otherwise non-visible listing photos by guessing media paths

### Uploaded avatars

Uploaded avatars are reachable at `/media/avatars/<path>`, but only when the file is still attached to a `CustomUser.uploaded_avatar`.

### Private user files

Private document-library files are unchanged:

- `/users/files/<id>/preview/`
- `/users/files/<id>/download/`

Padly still does not expose raw `/media/` access for those files.

## Tradeoffs of the Chosen Render Media Plan

The repo chooses ephemeral filesystem media for the current Render deployment because it works on the free tier and keeps the current Django filesystem storage contract intact.

That comes with real tradeoffs:

- uploads can be lost on restart, redeploy, or instance replacement
- demo records may point to missing image files after a redeploy
- this is not appropriate for long-term production user data

This is acceptable for Padly's current stage and course demo. It is not the end-state architecture for real production use.

When you outgrow the demo deployment, move media to object storage or another durable media service and keep the authenticated/private file access rules intact.

## Deploy with the Checked-In Blueprint

The simplest path is to let Render create resources from [`/render.yaml`](../../render.yaml).

That Blueprint configures:

- `healthCheckPath: /healthz/`
- `buildCommand: ./build.sh`
- `preDeployCommand: python manage.py migrate`
- `startCommand: ./start.sh`
- `PYTHON_VERSION=3.12.5`
- `DJANGO_DEBUG=false`
- `DJANGO_MEDIA_ROOT=/tmp/padly-media`
- `DJANGO_MEDIA_FALLBACK_ROOT=/tmp/padly-media`
- `DATABASE_URL` from Render Postgres
- `CHANNEL_REDIS_URL` and `CACHE_REDIS_URL` from Render Key Value

Values you still need to supply in Render:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `LISTING_GEOAPIFY_API_KEY`

## Manual Render Setup

If you prefer to create the service manually instead of using the Blueprint:

### Web service

- Runtime: `Python 3`
- Health check path: `/healthz/`
- Build command: `./build.sh`
- Pre-deploy command: `python manage.py migrate`
- Start command: `./start.sh`

### Database

- Create a Render PostgreSQL instance
- Use its internal connection string for `DATABASE_URL`

### Redis / Key Value

- Create one Render Key Value instance
- Point both `CHANNEL_REDIS_URL` and `CACHE_REDIS_URL` at its internal connection string

### Media Storage

- Do not attach a persistent disk for the current free-tier deployment.
- Set `DJANGO_MEDIA_ROOT=/tmp/padly-media`.
- Keep `DJANGO_MEDIA_FALLBACK_ROOT=/tmp/padly-media`.
- Treat uploaded media as ephemeral until the project moves to durable object storage.

## Environment Variables

Minimum production environment for Render:

| Variable | Value |
| --- | --- |
| `DJANGO_DEBUG` | `false` |
| `DJANGO_SECRET_KEY` | generated secret |
| `DATABASE_URL` | Render Postgres internal URL |
| `CHANNEL_REDIS_URL` | Render Key Value internal URL |
| `CACHE_REDIS_URL` | Render Key Value internal URL |
| `DJANGO_MEDIA_ROOT` | `/tmp/padly-media` |
| `DJANGO_MEDIA_FALLBACK_ROOT` | `/tmp/padly-media` |
| `DJANGO_USE_X_FORWARDED_HOST` | `true` |
| `DJANGO_TRUST_X_FORWARDED_PROTO` | `true` |
| `GOOGLE_CLIENT_ID` | Google OAuth client id |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `LISTING_GEOAPIFY_API_KEY` | Geoapify key |

Optional but recommended when using custom domains:

| Variable | Purpose |
| --- | --- |
| `DJANGO_ALLOWED_HOSTS` | include your custom hostnames |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | include your custom HTTPS origins |

If those two Django variables are blank, Padly falls back to Render's default `onrender.com` host and origin for first deploys.

## No Pre-Deploy Fallback

The checked-in [`/start.sh`](../../start.sh) starts Daphne only. It deliberately does not run migrations during every boot.

If your Render plan or deployment path cannot use `preDeployCommand`, run migrations manually before routing traffic to the new service:

```bash
python manage.py migrate --noinput
```

Then start the service with `./start.sh`.

## Google OAuth Checklist

Because Padly uses Google OAuth only, remember to update the Google Cloud Console with:

- the deployed callback origin
- the deployed authorized redirect URI for Allauth

If you add a custom domain later, update Google as well as Render.

## Geoapify Checklist

Padly listing authoring fails closed when Geoapify address verification is unavailable.

That means a production deployment without `LISTING_GEOAPIFY_API_KEY` will boot, but listing create/edit flows that require verified address search will not behave like a complete product.

## Post-Deploy Verification

After the first deploy, verify:

1. `/` loads with CSS and JavaScript present.
2. `/healthz/` returns `{"status": "ok"}`.
3. Google sign-in redirects through the correct deployed domain.
4. Listing index and listing detail pages load with their images.
5. Listing image upload works on create/edit flows.
6. Private user files remain accessible only through authenticated preview/download routes.
7. Websocket messaging works in a real browser session.
8. `python manage.py check --deploy` passes in the deployed environment.

## Failure Modes to Watch

### Static assets missing

Check:

- `whitenoise` is installed
- `collectstatic` ran in the build
- the service is using the Python runtime, not Docker or the wrong native runtime

### Postgres import or connection failure

Check:

- `psycopg[binary]` is present in `requirements.txt`
- `DATABASE_URL` is populated from the Render Postgres internal URL

### Uploads disappear after redeploy

This is expected with the current no-disk Render deployment. The app should continue to work, but previously uploaded files may be gone after a restart or redeploy. Move to object storage when uploaded media needs to persist.

### CSRF or bad-host failures after adding a custom domain

Set:

- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`

The Render fallbacks only cover the default `onrender.com` hostname and origin.
