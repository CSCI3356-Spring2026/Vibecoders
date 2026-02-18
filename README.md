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
│   ├── core/
│   │   └── landing.html
│   ├── listings/
│   │   ├── create_listing.html
│   │   ├── listing_detail.html
│   │   └── search.html
│   └── users/
│       ├── login.html
│       ├── profile.html
│       └── dashboard.html
├── static/                # Static assets (CSS, JS, images)
│   ├── css/custom.css     # Bootstrap overrides and color scheme
│   ├── js/main.js
│   └── images/
├── manage.py
├── requirements.txt
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

3. Install dependencies:

```bash
pip install -r requirements.txt
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

Django uses a template inheritance model. `templates/base.html` is the shared layout that all other pages extend. It should contain the HTML skeleton, Bootstrap CDN links, the navbar, footer, and a content block that child templates override.

Each app has its own subdirectory under `templates/`. For example, `templates/listings/search.html` is the template for the listing search page, rendered by a view in the `listings` app.

Static files (CSS, JS, images) live in the `static/` directory. In templates, reference them using Django's `{% static %}` tag. The custom color scheme and any Bootstrap overrides go in `static/css/custom.css`.

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