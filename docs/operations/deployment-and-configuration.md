# Deployment and Configuration

For a step-by-step Render-specific deployment runbook, see [Deploying Padly on Render](render-deployment.md).

## Production Requirements

Padly is a Django ASGI application with websockets. A production deployment should assume:

- ASGI runtime, not WSGI, for the live application
- Redis-backed channel layer
- Redis-backed cache for rate limits and unread counters
- explicit host and proxy configuration
- managed database instead of SQLite
- WhiteNoise or another production static-file layer
- persistent or object-backed media storage

## Required Production Environment

These settings must be provided when `DJANGO_DEBUG=false`:

- `DJANGO_SECRET_KEY`
- `DATABASE_URL`
- `CHANNEL_REDIS_URL`
- `CACHE_REDIS_URL`

Recommended supporting configuration:

- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DJANGO_MEDIA_ROOT`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `LISTING_GEOAPIFY_API_KEY`

## Runtime Entry

Use the ASGI app:

```bash
daphne vibecoders.asgi:application
```

`vibecoders/asgi.py` routes:

- HTTP through Django
- websocket traffic through `AllowedHostsOriginValidator` and `AuthMiddlewareStack`

Recommended Render health check path:

- `/healthz/`

## Security-Sensitive Settings

### HTTPS and cookies

When not in debug mode, Padly enables:

- `SECURE_SSL_REDIRECT`
- secure session cookies
- secure CSRF cookies
- HSTS
- `X-Content-Type-Options: nosniff`
- strict referrer policy

### Proxy trust

Proxy-related settings are opt-in:

- `DJANGO_TRUST_X_FORWARDED_PROTO`
- `DJANGO_USE_X_FORWARDED_HOST`
- `DJANGO_TRUST_X_FORWARDED_FOR`

Only enable `DJANGO_TRUST_X_FORWARDED_FOR` when a trusted reverse proxy is actually setting the header.

## Channels and Realtime

| Mode | Channel layer |
| --- | --- |
| Debug or no Redis configured | in-memory channel layer |
| Production with `CHANNEL_REDIS_URL` | Redis-backed `channels_redis.core.RedisChannelLayer` |

In-memory channels are acceptable for local development and tests only.

## Caching and Rate Limiting

Padly uses Django's cache framework for rate limiting, but the settings module does not currently define a shared `CACHES` backend.

Operational implication:

- out of the box, rate-limit enforcement uses the default local-memory cache and is process-local
- if you need multi-process or multi-node rate-limit consistency, provide a shared cache backend as part of deployment

## Maps and Addressing

### Verified address authoring

Listing creation/editing requires a working Geoapify autocomplete integration when verification is enabled.

### Map-first browse

The listing map requires a base style URL. This can come from:

- explicit `LISTING_GEOAPIFY_MAP_STYLE_URL`
- or the Geoapify API key-derived fallback

Satellite mode can use:

- `LISTING_MAP_SATELLITE_STYLE_URL`
- or the built-in satellite fallback

## Storage Expectations

### Current defaults

- SQLite database
- local filesystem media
- repo-local `staticfiles/` output for collected static assets

### Production recommendation

- move to a real database platform
- serve static files with WhiteNoise from collected `STATIC_ROOT`
- on the current no-disk Render deployment, point `DJANGO_MEDIA_ROOT` and `DJANGO_MEDIA_FALLBACK_ROOT` at `/tmp/padly-media`
- move media to shared or object-backed storage when you need horizontal scale or zero-downtime deploys
- treat private file delivery separately from public listing imagery

## Logging

Padly configures a console logger with a standard formatter:

- timestamp
- level
- logger name
- message

Admin moderation actions also emit operational logs for approvals, rejections, and report updates.

## Deployment Checklist

1. Set production secrets and allowed hosts.
2. Configure Google OAuth credentials for the deployed origin.
3. Configure Redis and run the ASGI app.
4. Configure Geoapify if listing authoring and map-first browse are enabled.
5. Verify secure cookie, proxy, and static/media settings.
6. Run:
   - `ruff check .`
   - `ruff format --check .`
   - `python manage.py check --deploy`
   - `python manage.py makemigrations --check --dry-run`
   - `python manage.py test`
7. Confirm listing photos and uploaded avatars still resolve through Padly's guarded media routes.
8. Confirm private user files are still served only through authenticated views.
