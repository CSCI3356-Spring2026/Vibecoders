# Management Commands

## Project-Specific Command

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

- There is currently one custom project command checked into the repository: `set_user_role`.
- Some older references mention a demo listing seed command, but no checked-in custom listing management command currently ships in this working tree.
- Any future custom operational commands should be added here when introduced.
