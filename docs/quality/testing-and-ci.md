# Testing and CI

## Quality Gates

Current CI on `main` runs:

```bash
ruff check .
ruff format --check .
python manage.py check
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
python manage.py test
```

The deploy check runs under explicit production-like environment variables in the workflow so security checks execute with `DJANGO_DEBUG=false` and required production settings present.

Workflow location:

- `.github/workflows/ci.yml`

## Test Organization

| Area | Primary test modules |
| --- | --- |
| Core pages and shared behavior | `core/tests/test_pages.py`, `core/tests/test_rate_limits.py` |
| Listings domain and UI | `listings/tests/test_models.py`, `listings/tests/test_pages.py` |
| User models, auth, files, admin, pages | `users/tests/test_models.py`, `users/tests/test_adapters.py`, `users/tests/test_files.py`, `users/tests/test_pages.py`, `users/tests/test_admin.py`, `users/tests/test_management.py` |
| Realtime messaging | `users/tests/test_messages_realtime.py` |

## What the Suite Covers Well

- role assignment and identity policy
- legal acceptance flow
- profile completion enforcement
- marketplace visibility rules
- listing authoring and verified address behavior
- messaging access control and websocket events
- private file validation and access
- moderation flows for listings and reports

## Practical Testing Strategy

### During development

- run targeted modules or classes while iterating
- keep changes scoped and update the closest relevant test suite

### Before handoff

Run:

```bash
ruff check .
ruff format --check .
python manage.py test
```

And additionally:

```bash
python manage.py makemigrations --check --dry-run
python manage.py check --deploy
```

when the change affects models or deployment/security behavior.

## Guidance for New Tests

- Prefer extending the nearest existing module.
- Cover both success and failure paths.
- Add regression tests when fixing authorization, visibility, or UI-contract bugs.
- If a template, JS module, and CSS file share a DOM contract, capture that in a page test.

## Local vs. CI Differences

| Concern | Local | CI |
| --- | --- | --- |
| Database | SQLite | SQLite |
| Channel layer | in-memory by default | in-memory |
| Google auth | depends on local env | not exercised through live OAuth |
| Geoapify | mocked in tests where appropriate | mocked in tests where appropriate |
| Password hashing | MD5 hasher forced during tests for speed | MD5 hasher forced during tests for speed |

## Test Runtime Notes

- `vibecoders/settings.py` detects test runs and applies deterministic test-only settings.
- Tests force a fast password hasher, disable profile completion and legacy geocoding gates, and keep local secret handling stable.
- The full suite is intentionally broad; optimize slow helpers before deleting useful behavioral coverage.

## Release Confidence Checklist

- lint passes
- full test suite passes
- schema check passes
- deployment check passes when relevant
- docs updated for behavior changes
- no private media or access-control regression has been introduced
