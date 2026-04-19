# Environment Variables

This document lists the environment variables used by Padly's runtime configuration.

## Core Runtime

| Variable | Default | Required in production | Purpose |
| --- | --- | --- | --- |
| `DJANGO_DEBUG` | auto-enabled for common local commands | No | toggles debug mode |
| `DJANGO_SECRET_KEY` | stable local fallback in debug only | Yes | Django secret key |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost,testserver` in debug or `RENDER_EXTERNAL_HOSTNAME` on Render | Usually | host allowlist |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty or `RENDER_EXTERNAL_URL` on Render | Usually | trusted CSRF origins |
| `DJANGO_LOG_LEVEL` | `INFO` | No | root logging level |
| `DJANGO_STATIC_ROOT` | `<BASE_DIR>/staticfiles` | No | collected static asset output path |
| `DJANGO_MEDIA_ROOT` | `<BASE_DIR>/media` | No | uploaded media root path |

## Proxy and Host Handling

| Variable | Default | Purpose |
| --- | --- | --- |
| `DJANGO_TRUST_X_FORWARDED_PROTO` | `false` | enables `SECURE_PROXY_SSL_HEADER` |
| `DJANGO_USE_X_FORWARDED_HOST` | `false` | uses forwarded host header |
| `DJANGO_TRUST_X_FORWARDED_FOR` | `false` | trusts `X-Forwarded-For` for rate-limit identity |

Render also provides `RENDER_EXTERNAL_HOSTNAME` and `RENDER_EXTERNAL_URL`. Padly uses those as fallbacks for `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` when the explicit Django variables are blank.

## Branding and Policy

| Variable | Default | Purpose |
| --- | --- | --- |
| `SITE_PRODUCT_NAME` | `Padly` | site branding |
| `SITE_COMPANY_NAME` | `Vibecoders` | site branding |
| `LEGAL_DOCUMENT_VERSION` | `2026-03-18` | forces reacceptance when legal text changes |
| `STUDENT_EMAIL_DOMAINS` | `bc.edu` | maps email domains to the student role |
| `PROFILE_COMPLETION_REQUIRED` | `true` outside tests | enables profile completion middleware |

## Google OAuth

| Variable | Default | Required for login | Purpose |
| --- | --- | --- | --- |
| `GOOGLE_CLIENT_ID` | empty | Yes | Google OAuth app client id |
| `GOOGLE_CLIENT_SECRET` | empty | Yes | Google OAuth app secret |

## Channels and Realtime

| Variable | Default | Required in production | Purpose |
| --- | --- | --- | --- |
| `CHANNEL_REDIS_URL` | empty in debug | Yes | Redis channel-layer connection |
| `CACHE_REDIS_URL` | empty in debug | Yes | Redis cache connection for rate limits and unread counters |

## Listing Media and Map Experience

| Variable | Default | Purpose |
| --- | --- | --- |
| `LISTING_IMAGE_MAX_BYTES` | `5242880` | max bytes per listing image |
| `LISTING_IMAGE_UPLOAD_LIMIT` | `10` | max images in one request |
| `LISTING_IMAGE_TOTAL_LIMIT` | `20` | max total images per listing |
| `LISTING_MAPS_ENABLED` | `true` | enables map-first listings UI |
| `LISTING_GEOAPIFY_MAP_STYLE_URL` | derived from API key when unset | base map style override |
| `LISTING_MAP_SATELLITE_STYLE_URL` | `builtin://satellite` | satellite style override |

## Address Verification and Geocoding

| Variable | Default | Purpose |
| --- | --- | --- |
| `LISTING_GEOAPIFY_API_KEY` | empty | required for verified address authoring |
| `LISTING_GEOAPIFY_AUTOCOMPLETE_URL` | `https://api.geoapify.com/v1/geocode/autocomplete` | Geoapify autocomplete endpoint |
| `LISTING_ADDRESS_AUTOCOMPLETE_RATE_LIMIT` | `30` | request cap per window |
| `LISTING_ADDRESS_AUTOCOMPLETE_RATE_WINDOW_SECONDS` | `60` | address-lookup window |
| `LISTING_REPORT_RATE_LIMIT` | `10` | report submissions per user per window |
| `LISTING_REPORT_RATE_WINDOW_SECONDS` | `3600` | listing-report rate-limit window |
| `LISTING_GEOCODING_ENABLED` | `true` outside tests | legacy geocoder toggle |
| `LISTING_GEOCODER_URL` | `https://photon.komoot.io/api/` | legacy geocoder endpoint |
| `LISTING_GEOCODER_USER_AGENT` | `<SITE_PRODUCT_NAME>/1.0` | user agent for legacy geocoder |
| `LISTING_GEOCODER_TIMEOUT_SECONDS` | `4` | timeout for geocoder and Geoapify calls in current code paths |

## Messaging and Login Controls

| Variable | Default | Purpose |
| --- | --- | --- |
| `MESSAGE_SEND_RATE_LIMIT` | `20` | messages per user per window |
| `MESSAGE_SEND_RATE_WINDOW_SECONDS` | `60` | message rate-limit window |
| `LOGIN_INIT_RATE_LIMIT` | `10` | login attempts per request identity per window |
| `LOGIN_INIT_RATE_WINDOW_SECONDS` | `300` | login rate-limit window |

## Private Document Library

| Variable | Default | Purpose |
| --- | --- | --- |
| `USER_FILE_MAX_BYTES` | `10485760` | max bytes per uploaded file |
| `USER_FILE_TOTAL_LIMIT` | `25` | max files per user |
| `USER_FILE_UPLOAD_RATE_LIMIT` | `25` | upload cap per user per window |
| `USER_FILE_UPLOAD_RATE_WINDOW_SECONDS` | `300` | upload rate-limit window |

## Account Safety

| Variable | Default | Purpose |
| --- | --- | --- |
| `ACCOUNT_DELETION_RECENT_AUTH_SECONDS` | `1800` | max age for recent-auth deletion gate |

## Configuration Notes

- `.env` is loaded automatically by `python-dotenv`.
- Production fails closed when required secrets or host/channel settings are missing.
- Tests force some settings off or to deterministic values to avoid environment leakage.
- Test runs also force Django's MD5 password hasher so the full suite stays fast enough to run routinely in local development and CI.
