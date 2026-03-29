# Padly Documentation

This directory is the engineering and operations handbook for Padly. It complements the root
[`README.md`](../README.md) and [`AGENTS.md`](../AGENTS.md) by documenting the system as it exists
today: product scope, architecture, domain rules, operational procedures, security controls, and
reference material.

## Who This Is For

| Audience | Start Here | Then Read |
| --- | --- | --- |
| New engineers | [Architecture Overview](architecture/system-overview.md) | [Code Organization](architecture/code-organization.md), [Local Development](operations/local-development.md), [Testing and CI](quality/testing-and-ci.md) |
| Feature engineers | [Request Lifecycle](architecture/request-lifecycle.md) | [Listings and Marketplace](domain/listings-and-marketplace.md), [Messaging and Realtime](domain/messaging-and-realtime.md), [Frontend System](frontend/frontend-system.md) |
| Admin and moderation owners | [Admin and Moderation](domain/admin-and-moderation.md) | [Runbooks](operations/runbooks.md), [HTTP Routes](reference/http-routes.md) |
| Security and privacy reviewers | [Security and Privacy](security/security-and-privacy.md) | [Identities and Access](domain/identities-and-access.md), [Files and Private Media](domain/files-and-private-media.md), [Environment Variables](reference/environment-variables.md) |
| Operators and deployers | [Deployment and Configuration](operations/deployment-and-configuration.md) | [Runbooks](operations/runbooks.md), [Management Commands](reference/management-commands.md) |

## System Snapshot

Padly is a Django 5.2 monolith for the Boston College housing marketplace. The live runtime is
organized around four first-party apps:

- `core`: landing page, legal pages, shared helpers, branding, rate limiting
- `users`: authentication, profiles, dashboard, document library, admin workspace
- `listings`: listing creation, moderation, marketplace browsing, maps, favorites, reviews, reports
- `communications`: inbox, conversations, websocket messaging, unread and delete state

The application uses Google OAuth for sign-in, Django Allauth for social auth plumbing, Channels
for realtime messaging, MapLibre plus Geoapify for the listing map and verified address lookup, and
SQLite plus local media by default in development.

## Documentation Map

### Architecture

- [System Overview](architecture/system-overview.md)
- [Code Organization](architecture/code-organization.md)
- [Request Lifecycle](architecture/request-lifecycle.md)

### Domain

- [Identities and Access](domain/identities-and-access.md)
- [Listings and Marketplace](domain/listings-and-marketplace.md)
- [Messaging and Realtime](domain/messaging-and-realtime.md)
- [Admin and Moderation](domain/admin-and-moderation.md)
- [Files and Private Media](domain/files-and-private-media.md)

### Frontend

- [Frontend System](frontend/frontend-system.md)

### Operations

- [Local Development](operations/local-development.md)
- [Deployment and Configuration](operations/deployment-and-configuration.md)
- [Runbooks](operations/runbooks.md)

### Security

- [Security and Privacy](security/security-and-privacy.md)

### Quality

- [Testing and CI](quality/testing-and-ci.md)

### Reference

- [HTTP Routes](reference/http-routes.md)
- [Data Models](reference/data-models.md)
- [Management Commands](reference/management-commands.md)
- [Environment Variables](reference/environment-variables.md)

## Documentation Principles

- Prefer code-backed facts over assumptions.
- Document invariants, not just happy paths.
- Call out operational caveats and failure modes where they matter.
- Keep root onboarding documents short; keep system detail in `/docs`.
- Update the nearest document when changing auth, moderation, messaging, maps, private files, or deployment behavior.

## Relationship to Existing Root Docs

- [`README.md`](../README.md) remains the external-friendly project entry point.
- [`AGENTS.md`](../AGENTS.md) remains the repository-specific operating guide for coding agents.
- `/docs` is the long-form source of truth for engineers, operators, and reviewers who need to
  understand how Padly works end to end.
