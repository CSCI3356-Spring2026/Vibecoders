# Files and Private Media

## Two Different Media Domains

Padly stores two distinct classes of uploads:

| Media type | Model | Visibility | Delivery path |
| --- | --- | --- | --- |
| Listing photos | `ListingImage` | Public for approved listings | Development-only direct route for listing photos; rendered on marketplace/detail pages |
| User document library files | `UserFile` | Private | Authenticated preview/download views only |

These two media domains have different access and privacy rules and should not be treated interchangeably.

## Listing Photos

### Storage and validation

- Stored under `media/listing_photos/`
- Validated by `listings.validators.validate_listing_image`
- Limited by:
  - `LISTING_IMAGE_MAX_BYTES`
  - `LISTING_IMAGE_UPLOAD_LIMIT`
  - `LISTING_IMAGE_TOTAL_LIMIT`

### Serving behavior

- In development only, `vibecoders/urls.py` exposes `media/listing_photos/<path>`
- This exception is limited to listing photos
- Private user uploads are not served this way

### Deletion behavior

- `ListingImage` registers a post-delete hook
- storage deletion happens inside `transaction.on_commit()`

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

| Actor | Listing photos | Private user files |
| --- | --- | --- |
| Anonymous user | Can see public listing photos in marketplace/detail pages | No access |
| Owner | Can manage their own listing photos and private files | Full access to own files |
| Admin | Can review listing photos in admin surfaces | Can access user files through authenticated admin-enabled selectors/views |

## Operational Caveats

- Padly uses local media storage by default in development.
- Production should move both public and private media to shared or object-backed storage.
- Cleanup is commit-aware, but blob writes can still orphan files if an outer transaction rolls back after storage writes have already happened. That is an operational limitation to keep in mind when evolving upload workflows.

## Rules to Preserve

- Never expose raw template links to private `UserFile` paths.
- Never add a blanket `/media/` route for private uploads.
- Keep preview restrictions limited to images and PDFs.
- Keep file-access checks behind authenticated, owner- or admin-authorized views.
