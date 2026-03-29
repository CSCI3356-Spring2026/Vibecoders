# Runbooks

## 1. Promote a User to Admin

Prerequisites:

- the user has already signed in once, so the account exists
- your environment is loading the expected settings

Command:

```bash
python manage.py set_user_role user@bc.edu admin
```

To restore the user to their email-derived default role:

```bash
python manage.py set_user_role user@bc.edu student
```

or:

```bash
python manage.py set_user_role user@example.com realtor
```

depending on the email policy.

## 2. Review or Reject a Listing

1. Sign in as an admin user.
2. Open `/users/admin-listings/`.
3. Filter or search for the listing.
4. Open the listing detail review page.
5. Approve or reject.

Important rule:

- rejections require review notes

## 3. Resolve a Listing Report

1. Sign in as an admin user.
2. Open `/users/admin-reports/`.
3. Review listing context and reporter details.
4. Change status.
5. Add resolution notes if closing the report.

Important rule:

- resolved or dismissed reports require resolution notes

## 4. Troubleshoot Login or Legal Acceptance Problems

### Symptoms

- user is redirected back to login
- Google flow feels like it loops
- stale legal acceptance blocks access

### Checks

1. confirm Google OAuth credentials are present
2. confirm the user has a verified Google email
3. confirm `LEGAL_DOCUMENT_VERSION` matches the expected active documents
4. check whether the user has current acceptance timestamps and version
5. if local cookies are stale after settings changes, clear site cookies and reauthenticate

Relevant files:

- `users/views.py`
- `users/adapters.py`
- `users/legal.py`
- `users/middleware.py`

## 5. Troubleshoot Address Suggestions or Listing Authoring

### Symptoms

- address suggestions return inline errors
- listing create/edit blocks on verified address selection
- map-first browse falls back to list-only view

### Checks

1. verify `LISTING_GEOAPIFY_API_KEY`
2. verify `LISTING_GEOAPIFY_AUTOCOMPLETE_URL`
3. verify `LISTING_GEOAPIFY_MAP_STYLE_URL` or an API-key-derived base style
4. check rate-limit settings if autocomplete is unexpectedly returning 429
5. confirm the user is authenticated, because the suggestions endpoint returns JSON 401 for anonymous requests

## 6. Troubleshoot Messaging Problems

### Symptoms

- replies do not arrive in the inbox
- websockets fail to connect
- unread counts drift

### Checks

1. confirm the user is authenticated and active
2. confirm the conversation is visible to that user
3. confirm Redis is configured in production
4. verify the ASGI app is serving the deployment
5. inspect rate-limit settings for message-send throttling

Relevant files:

- `communications/services.py`
- `communications/consumers.py`
- `users/tests/test_messages_realtime.py`

## 7. Troubleshoot Private File Access

### Symptoms

- preview/download returns 404
- preview refuses to render
- uploads fail even though the file looks valid

### Checks

1. confirm the file belongs to the current user or the current user is an admin
2. confirm the upload passes extension, MIME, and content validation
3. confirm the file count limit has not been reached
4. confirm upload rate limiting has not been triggered
5. remember that only images and PDFs are previewable inline

## 8. Release Readiness Checklist

Before opening or merging a production-intended PR:

1. update the nearest docs page if auth, moderation, messaging, or config changed
2. run `ruff check .`
3. run `ruff format --check .`
4. run `python manage.py makemigrations --check --dry-run`
5. run `python manage.py test`
6. run `python manage.py check --deploy` for security-sensitive changes
7. verify marketplace public visibility still excludes pending and rejected listings
8. verify private user files are not directly exposed
