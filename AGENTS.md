# AGENTS.md
Last Revised By: Hunter Scheppat -- February 18th, 2025 

**NOTE**: If you decide to use agentic AI tools (Claude Code, Cursor, etc) you MUST direct them towards this file. Additionally, this file is a good refresher on the code quality and branch protection standards outlined in the [README](/README.md)

Instructions for AI coding agents working in this repository.

## 1) Project Snapshot

- Stack: Django 5.2, Python 3.12+, SQLite, Bootstrap 5 templates.
- Apps: `core`, `listings`, `users`.
- Current state: app `models.py`, `views.py`, and `tests.py` are scaffold placeholders; templates and custom CSS/JS files are currently empty.
- CI: GitHub Actions runs Ruff lint/format checks and `python manage.py test` on pull requests to `main`.

## 2) Required Workflow

1. Read `README.md` before making architectural decisions.
2. Keep changes scoped to the user request; do not refactor unrelated areas.
3. Before finalizing, run:
   - `ruff check .`
   - `ruff format --check .`
   - `python manage.py test`
4. If a command cannot run in the environment, state that clearly in your final summary.

## 3) Code Quality Standards

- Follow Ruff rules configured in `pyproject.toml`:
  - line length 120
  - target version Python 3.12
- Prefer clear, small functions and readable templates over clever abstractions.
- Do not leave placeholder comments like "TODO later" unless explicitly requested.
- Add or update tests when behavior changes.

## 4) Django Structure Rules

- Keep app boundaries clean:
  - `core`: landing/shared pages
  - `listings`: listing creation/detail/search logic
  - `users`: auth/profile/dashboard logic
- Place templates in app-specific folders under `templates/<app>/`.
- Put shared layout in `templates/base.html` and use template inheritance.
- Put styling in `static/css/custom.css` and JavaScript in `static/js/main.js`.
- If adding routes, update `vibecoders/urls.py` and use app-level `urls.py` modules when appropriate.

## 5) Git and PR Expectations

- Do not commit directly to `main`.
- Use descriptive branch names such as:
  - `feature/<short-description>`
  - `fix/<short-description>`
- Keep commit messages specific and scoped to actual changes.
- Assume PRs require passing CI checks and at least one human review.

## 6) Security and Privacy

- Never commit secrets, API keys, OAuth credentials, or `.env` contents.
- Avoid hardcoding sensitive values in source files.
- Treat user data as private: do not add real personal data to fixtures, tests, or sample content.
- For authentication features, prefer configuration via environment variables and documented setup steps.

## 7) UI and Color System

When implementing UI, use Bootstrap 5 plus consistent custom tokens in `static/css/custom.css`:

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

**Typography**: 
- Headings: Inter (700/600)
- Body/UI: Inter (400/500)
- Optional accent (quotes/hero tagline): Source Serif 4 (400/600 italic optional)

## 8) Done Checklist (For Agents)

Before handing work back, confirm:

- Requested behavior is implemented.
- Lint/format/tests were run, or blockers were explicitly reported.
- Files changed are minimal and relevant.
- No secrets or unrelated changes were introduced.
