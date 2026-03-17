# Vibecoders

Vibecoders is a student housing and subletting platform built for Boston College students. This project is being developed for CSCI 3356 Software Engineering, Spring 2026.

## Team

Vincent Park, John Giglia, Austin Chan-Orsini, Cullen Bartz, Hunter Scheppat, Drew Petaccia

## Tech Stack

- **Backend:** Django 5.2, Python 3.12+
- **Database:** SQLite (default Django backend)
- **Authentication:** Google OAuth
- **Frontend:** Django templates, Bootstrap 5, custom CSS
- **Linting:** Ruff (enforced via pre-commit hooks and CI)
- **CI:** GitHub Actions

## Access Model

The platform currently supports three access levels:

- `Student`: full marketplace access for verified domains listed in `STUDENT_EMAIL_DOMAINS` (defaults to `bc.edu`)
- `Realtor`: listing-only access for external Google accounts
- `Admin`: elevated management access for the internal admin dashboard

Non-admin users are assigned their default role from their email domain at sign-in. Admin access is granted explicitly.

## Project Structure

```
Vibecoders/
├── vibecoders/            # Main Django project settings and root URL config
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── core/                  # App for landing page and shared utilities
├── listings/              # App for listing CRUD, search, and filtering
├── users/                 # App for authentication, profiles, and dashboards
├── templates/             # All HTML templates (organized by app)
│   ├── base.html          # Shared layout: Bootstrap, navbar, footer
│   ├── auth/              # Shared auth fragments/layout
│   │   ├── base.html
│   │   └── google_mark.html
│   ├── core/
│   │   └── landing.html
│   ├── listings/
│   │   ├── listing_form.html
│   │   ├── listing_list.html
│   │   ├── listing_detail.html
│   ├── account/
│   │   ├── login.html
│   │   └── logout.html
│   ├── socialaccount/
│   │   ├── authentication_error.html
│   │   ├── login.html
│   │   ├── login_cancelled.html
│   │   └── login_redirect.html
│   └── users/
│       ├── files.html
│       ├── login.html
│       ├── profile.html
│       └── dashboard.html
├── static/                # Static assets (CSS, JS, images)
│   ├── css/custom.css     # Bootstrap overrides and color scheme
│   ├── js/
│   └── images/
├── media/                 # Local user-uploaded files during development (gitignored)
├── manage.py
├── requirements.txt       # Runtime dependencies
├── requirements-dev.txt   # Local development tools (ruff, pre-commit)
├── pyproject.toml          # Ruff linting configuration
├── .pre-commit-config.yaml # Pre-commit hook definitions
└── .github/workflows/ci.yml  # GitHub Actions CI pipeline
```

## Getting Started

### Prerequisites

- Python 3.12 or higher
- Git

### Setup

1. Clone the repository:

```bash
git clone https://github.com/CSCI3356-Spring2026/Vibecoders.git
cd Vibecoders
```

2. Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. Install development dependencies:

```bash
pip install -r requirements-dev.txt
```

4. Install pre-commit hooks (required for all contributors):

```bash
pre-commit install
```

5. Run database migrations:

```bash
python manage.py migrate
```

6. Start the development server:

```bash
python manage.py runserver
```

The app will be available at `http://127.0.0.1:8000/`.

To grant admin access to an existing account:

```bash
python manage.py set_user_role user@bc.edu admin
```

To seed the local database with demo marketplace data:

```bash
python manage.py seed_demo_listings
```

The seed command is idempotent. It creates a small set of Boston College student accounts, external realtor accounts,
sample listings, and a few inquiries so the marketplace and owner views have realistic data during local development.

## Development Workflow

### Branching

All development happens on feature branches. Direct commits to `main` are NOT allowed. The branch protection rules require:

- A pull request for all changes to `main`
- CI checks (lint + tests) must pass before merging
- At least one approving review before merging

Name your branches descriptively, for example: `feature/landing-page`, `feature/user-profile`, `fix/search-filter-bug`.

### Linting

This project uses [Ruff](https://docs.astral.sh/ruff/) for linting and formatting. Pre-commit hooks run Ruff automatically on every commit. If your code has lint errors, the commit will be blocked until they are fixed.

To manually check linting:

```bash
ruff check .
```

To auto-fix issues:

```bash
ruff check --fix .
```

To check formatting:

```bash
ruff format --check .
```

To auto-format:

```bash
ruff format .
```

### CI

GitHub Actions runs on every pull request to `main`. The pipeline runs two jobs:

1. **Lint** - Runs `ruff check` and `ruff format --check`
2. **Test** - Runs `python manage.py test`

Both must pass before a PR can be merged.

### How Templates and Static Files Work

Django uses a template inheritance model. `templates/base.html` is the shared layout that all app pages extend. It contains the HTML skeleton, Bootstrap CDN links, the navbar, footer, and a content block that child templates override.

Auth-specific overrides live in `templates/account/`, `templates/socialaccount/`, and `templates/auth/`. The current listings flow uses `templates/listings/listing_form.html`, `templates/listings/listing_list.html`, and `templates/listings/listing_detail.html`.

Static files (CSS, JS, images) live in the `static/` directory. In templates, reference them using Django's `{% static %}` tag. `static/css/custom.css` is the main stylesheet entrypoint.

User-uploaded files are stored under `media/` in development and are intentionally ignored by git.

## Tests

Tests are organized by app:

- `core/tests/`
- `listings/tests/`
- `users/tests/`

The larger `listings` and `users` suites are split by concern so model, view, adapter, management-command, and file-library tests can evolve independently as the project grows.

## User Interface 

Consistent custom tokens are in `static/css/custom.css`:

```css
:root {
  --primary-600: #4f46e5;
  --primary-500: #6366f1;
  --primary-100: #e0e7ff;

  --secondary-600: #0d9488;
  --secondary-500: #14b8a6;
  --secondary-100: #ccfbf1;

  --accent-500: #f59e0b;

  --gray-900: #111827;
  --gray-700: #374151;
  --gray-500: #6b7280;
  --gray-300: #d1d5db;
  --gray-100: #f3f4f6;
  --white: #ffffff;
}
```
