# Frontend System

## Rendering Model

Padly is primarily a server-rendered Django application with targeted JavaScript enhancement.

### What that means in practice

- Templates produce the baseline UI.
- CSS defines a shared visual system plus page-specific layouts.
- JavaScript enhances areas that need richer interaction:
  - maps
  - address suggestions
  - image galleries
  - inline confirm controls
  - realtime inbox behavior

## Shared Shell

`templates/base.html` provides:

- brand header
- shared centered desktop nav plus mobile offcanvas drawer
- role-aware nav actions
- authenticated account menu
- compact notification stack for Django messages
- footer with legal links

This is the default page shell unless a template intentionally overrides it.
Shared nav link markup is centralized in `templates/includes/site_nav_links.html`.

## Design System

### Foundations

- Bootstrap 5.3.7
- custom token layer in `static/css/base.css`
- current typography based on `Instrument Sans`

### Token categories

- brand colors
- neutral palette
- typography families
- surface and border colors
- radius scale
- shadow scale

### Current visual direction

- restrained, flat surfaces
- compact radii
- minimal decorative gradients
- clean app-shell layouts instead of marketing-heavy chrome

## CSS Organization

| File | Purpose |
| --- | --- |
| `base.css` | design tokens, typography, global element defaults |
| `navigation.css` | header, nav, account menu |
| `footer.css` | footer layout and styling |
| `forms.css` | form controls and shared form treatment |
| `layout.css` | shared app-shell layout primitives |
| `components.css` | reusable panels, metadata chips, shared UI pieces |
| `listings.css` | marketplace, listing cards, listing detail, map workspace |
| `listing-form.css` | guided listing authoring wizard |
| `messages-shell.css`, `messages-thread.css` | inbox layout and thread styling |
| `dashboard.css`, `files.css`, `auth.css`, `admin.css`, `home.css`, `responsive.css` | page-specific layers |

## JavaScript Modules

| Module | Responsibility |
| --- | --- |
| `listing-form.js` | multi-step listing wizard behavior |
| `listings-address-picker.js` | verified address lookup UX |
| `listings-page.js` | list + map synchronization and live search |
| `listings-map-view.js` | MapLibre state, markers, style toggling |
| `listings-results.js` | live card rendering for search responses |
| `listing-detail-gallery.js` | detail-page photo gallery interaction |
| `legal-review.js` | scroll-gated legal acceptance |
| `app-notifications.js` | auto-dismiss and dismissal behavior for the notification stack |
| `messages.js` plus `messages_*` modules | realtime inbox behavior |
| `inline-confirm.js` | shared confirmation popover logic |

## Contract-Sensitive Surfaces

Some templates, CSS modules, and JS modules are tightly coupled. Changes should be coordinated across all three layers.

### Most sensitive surfaces

- listings map/results page
- inbox thread and conversation list
- listing form stepper and address picker
- shared avatar rendering

If markup class names or data attributes change, update the matching JS and CSS in the same change.

## Page-Level Conventions

### Marketplace

- filters above the results/map workspace
- results on the left
- map on the right
- fixed shared navbar position consistent with the rest of the site
- desktop results pane scrolls independently inside the fixed-height workspace
- listing result cards reuse the same stacked media-first card language as landing cards instead of a split side-by-side treatment
- map style toggle when satellite mode is available

### Listing detail

- photo gallery is the visual focal point
- facts and contact actions are structured rather than prose-heavy
- pricing, facts, and owner actions are grouped into a single clear intro band instead of stacked micro-cards

### Dashboard and admin

- account/workspace framing rather than marketing copy
- action surfaces prioritized over entitlement jargon

### Login and legal review

- the standard login view is intentionally minimal and centered on the Google action
- stale-legal users move through a stepped review flow
- privacy policy is reviewed first, then Terms of Service
- acknowledgement only unlocks after each document has been scrolled

## Frontend Rules Worth Preserving

- Keep shared nav position and sizing consistent across pages.
- Prefer clear layouts and concise copy over decorative flourishes.
- Avoid duplicating large shell markup when template inheritance can do the job.
- Reuse shared tokens instead of hardcoding one-off colors or radii.
- Prefer compact notifications over full-width page banners for routine success and error feedback.
