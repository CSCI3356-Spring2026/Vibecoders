# Management Commands

## Project-Specific Commands

### `seed_demo_data`

Purpose:

- create a realistic local Padly demo environment across users, listings, roommate flows, inbox threads, reports, and private files
- download and cache reusable listing photos into a gitignored local bundle under `var/demo_seed/`
- recreate the same demo namespace on repeat runs without depending on checked-in media

Usage:

```bash
python manage.py seed_demo_data
python manage.py seed_demo_data --skip-image-downloads
python manage.py seed_demo_data --refresh-photo-cache
python manage.py seed_demo_data --reference-date 2026-09-01
```

Options:

- `--bundle-root <path>`: override the local cache/bundle directory; defaults to `var/demo_seed/`
- `--skip-image-downloads`: require an already-populated local photo cache instead of downloading source images again
- `--refresh-photo-cache`: re-download and re-normalize the source listing images
- `--reference-date YYYY-MM-DD`: anchor generated lease windows and roommate move-in dates

Notes:

- this command is intentionally limited to `DJANGO_DEBUG=true`
- the bundle root is local-only and already ignored by the repository because it lives under `var/`
- the summary files are written to `var/demo_seed/seed_summary.json` and `var/demo_seed/seed_summary.txt`
- the seeded admin account can exercise the custom `/users/admin-*` workspace; its password is only useful for raw `/admin/` when `DJANGO_ADMIN_ENABLED=true`
- the normal product login flow remains Google OAuth

Implementation:

- `core/management/commands/seed_demo_data.py`
- `core/demo_seed.py`

### `set_user_role`

Purpose:

- promote a user to admin
- restore a user to their email-derived default role

Usage:

```bash
python manage.py set_user_role <email> <student|realtor|admin>
```

Examples:

```bash
python manage.py set_user_role user@bc.edu admin
python manage.py set_user_role user@bc.edu student
python manage.py set_user_role user@example.com realtor
```

Behavior:

- fails if the user does not exist
- allows explicit admin promotion
- rejects assigning a non-admin role that does not match the email policy

Implementation:

- `users/management/commands/set_user_role.py`

## Operationally Important Django Commands

These are not custom commands, but they are part of the regular Padly workflow:

```bash
python manage.py migrate
python manage.py makemigrations --check --dry-run
python manage.py test
python manage.py check
python manage.py check --deploy
python manage.py createsuperuser
python manage.py runserver
```

## Command Usage Guidance

### Local development

Ensure your shell sees the expected environment, especially:

- `DJANGO_DEBUG=true` for normal local usage
- or a valid `DJANGO_SECRET_KEY` if running in non-debug mode

### Before merge

Prefer running:

```bash
ruff check .
ruff format --check .
python manage.py makemigrations --check --dry-run
python manage.py test
```

And add:

```bash
python manage.py check --deploy
```

when changing settings, auth, middleware, proxy behavior, or other security-sensitive areas.

## Notes

- The older `seed_listings` and `seed_roommate_posts` commands remain narrow development helpers. `seed_demo_data` is now the canonical full-environment seeding flow.
- Any future custom operational commands should be added here when introduced.
