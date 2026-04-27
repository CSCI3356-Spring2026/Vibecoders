# Files and Private Media

## Three Different Media Domains

Padly stores three distinct classes of uploads:

| Media type | Model | Visibility | Delivery path |
| --- | --- | --- | --- |
| Listing photos | `ListingImage` | Public only when the listing itself is accessible | App-served `/media/listing_photos/<path>` route with listing-access checks |
| Uploaded avatars | `CustomUser.uploaded_avatar` | Public while attached to a user profile | App-served `/media/avatars/<path>` route for known avatar files |
| User document library files | `UserFile` | Private | Authenticated preview/download views only |

These media domains have different access and privacy rules and should not be treated interchangeably.

## Listing Photos

### Storage and validation

- Stored under `media/listing_photos/`
- Validated by `listings.validators.validate_listing_image`
- Limited by:
  - `LISTING_IMAGE_MAX_BYTES`
  - `LISTING_IMAGE_UPLOAD_LIMIT`
  - `LISTING_IMAGE_TOTAL_LIMIT`

### Serving behavior

- Padly exposes `media/listing_photos/<path>` in all environments
- The route resolves the `ListingImage` record first, then applies the same access rules as listing detail
- Anonymous users can fetch photos only for public listings
- Owners, admins, and otherwise-authorized viewers can fetch non-public listing photos through the same route
- Private user uploads are still not served this way

### Deletion behavior

- `ListingImage` registers a post-delete hook
- storage deletion happens inside `transaction.on_commit()`

## Uploaded Avatars

### Storage and validation

- Stored under `media/avatars/`
- Uploaded through the profile setup flow
- Validated by the avatar form and image field handling already used by `users.views.upload_avatar`

### Serving behavior

- Padly exposes `media/avatars/<path>` in all environments
- The route only serves files still referenced by `CustomUser.uploaded_avatar`
- This route is intentionally narrower than a blanket `/media/` file server

## Private Document Library

### Model behavior

`users.models.UserFile` stores:

- `owner`
- `title`
- `file`
- `uploaded_at`

### Validation

Validation is split between model and file-validator layers:

- max bytes via `USER_FILE_MAX_BYTES`
- allowed file types and MIME/content inspection via `users.validators.validate_user_upload`
  - PDFs plus JPG/PNG/WebP only
- per-user total capacity via `USER_FILE_TOTAL_LIMIT`
- per-user upload burst limit via `USER_FILE_UPLOAD_RATE_LIMIT`

### Delivery behavior

Private files are accessed only through:

- `/users/files/<id>/preview/`
- `/users/files/<id>/download/`

Response headers enforce privacy:

- `Cache-Control: private, no-store`
- `X-Content-Type-Options: nosniff`
- `Cross-Origin-Resource-Policy: same-origin`
- `Referrer-Policy: no-referrer`
- `X-Robots-Tag: noindex, nofollow`

Only images and PDFs are previewable inline.

## Access Rules

| Actor | Listing photos | Uploaded avatars | Private user files |
| --- | --- | --- | --- |
| Anonymous user | Can see public listing photos in marketplace/detail pages | Can load avatars already attached to a user profile | No access |
| Owner | Can manage their own listing photos and private files | Can replace their own uploaded avatar | Full access to own files |
| Moderator | Can review listing photos in staff moderation surfaces | Can inspect user avatars through normal product/staff surfaces | No access by default |
| Support / Platform Admin | Can review listing photos in staff surfaces | Can inspect user avatars through normal product/staff surfaces | Access only through authenticated views with an active support investigation and audit logging |

## Operational Caveats

- Padly uses local media storage by default in development.
- The current no-disk Render deployment uses `/tmp/padly-media` so uploads work without a persistent disk.
- Private document-library files remain app-served even when public listing media also lives on disk.
- Uploaded files in `/tmp/padly-media` are ephemeral and may disappear after restart or redeploy.
- Long-term production scale still favors shared or object-backed storage instead of ephemeral local media.
- Cleanup is commit-aware, but blob writes can still orphan files if an outer transaction rolls back after storage writes have already happened. That is an operational limitation to keep in mind when evolving upload workflows.

## Rules to Preserve

- Never expose raw template links to private `UserFile` paths.
- Never add a blanket `/media/` route for private uploads.
- Keep preview restrictions limited to images and PDFs.
- Keep file-access checks behind authenticated, owner-authorized, or investigation-authorized views.
