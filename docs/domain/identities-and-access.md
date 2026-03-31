# Identities and Access

## Authentication Model

Padly uses Google OAuth exclusively. Traditional email/password signup and password reset flows are intentionally disabled.

### Why this matters

- Identity is anchored to a verified Google email.
- Role defaults are derived from email domain.
- Legal acceptance is enforced before login completion.
- Recent authentication is tracked for sensitive account actions.

## Role Model

| Role | How it is assigned | Marketplace access | Messaging access | Admin workspace |
| --- | --- | --- | --- | --- |
| `student` | Default for configured student domains such as `bc.edu` | Can browse the public marketplace | Can message about listings | No |
| `realtor` | Default for non-student external domains | Listing-only access to own inventory | Cannot initiate listing conversations | No |
| `admin` | Explicit promotion only | Can browse marketplace and access admin-only detail paths | Can message about listings | Yes |

### Role policy rules

- `CustomUser.apply_email_role_policy()` keeps non-admin roles aligned with the current email policy.
- `set_admin_access(True)` is the supported way to promote a user to admin.
- Removing admin access returns the user to the email-derived default role.
- `set_user_role` is the supported operational command for role changes outside the UI.
- The Padly admin role controls the custom admin workspace. Raw Django `/admin/` access is still governed separately by Django staff permissions and is not auto-synced.

## User Model

`users.models.CustomUser` extends `AbstractUser` and adds:

- unique normalized email
- role
- profile completion timestamp
- legal acceptance timestamps and version
- profile image URL fallback

Useful computed properties include:

- `can_browse_marketplace`
- `can_start_listing_conversations`
- `can_use_roommate_matching`
- `has_listing_only_access`
- `has_current_legal_acceptance`
- `display_name`
- `avatar_url`

## Login and Signup Flow

### Entry points

- `/users/login/`
- `/accounts/login/` routed to the same custom login page
- `/accounts/google/login/` for the guarded Google redirect

### Flow summary

1. The user lands on the custom login page.
2. If the current legal version has not been reviewed, the page embeds the Terms of Service and Privacy Policy review surfaces.
3. The user must scroll both documents before the acceptance checkboxes unlock.
4. A pending legal acceptance payload is stored in session state.
5. Allauth completes Google login and the adapter validates verified email identity.
6. The pending legal acceptance is persisted to the user record.

## Legal Acceptance

Legal acceptance is versioned by `LEGAL_DOCUMENT_VERSION`.

### Rules

- Users accept Terms and Privacy together.
- Acceptance is stored both in the session during the pre-OAuth flow and on the user after login succeeds.
- Users with stale acceptance are logged out by middleware and forced back through the review flow.
- Existing users with current acceptance are not asked again for the same version.

### Files involved

- `users/legal.py`
- `users/middleware.py`
- `users/views.py`
- `users/adapters.py`
- `users/signals.py`
- `static/js/legal-review.js`

## Profile Completion

`ProfileCompletionMiddleware` can force users to finish profile setup before using the application.

### Details

- Controlled by `PROFILE_COMPLETION_REQUIRED`
- Enforced for students, realtors, and admins
- Redirect target is `/users/profile/setup/`
- Completion is recorded with `profile_completed_at`

### Profile models

| Model | Applies To | Purpose |
| --- | --- | --- |
| `StudentProfile` | student users | roommate and lifestyle questionnaire plus profile basics |
| `AdminProfile` | admin and realtor users | lightweight profile record used for completion and display |

## Dashboard and Workspace Access

### User dashboard

- `/users/dashboard/`
- Shows recent listings, files, and conversations
- Acts as the main account workspace
- Surfaces the entry point into group match and roommate discovery

### Listing-only users

- Realtors do not browse the normal marketplace
- Their primary workspace is `/users/posts/`

### Admin users

- Can see the account workspace and the custom admin workspace
- Gain an admin dashboard link in the shared profile menu

## Recent Authentication

Account deletion is gated by a recent-auth timestamp stored in the session.

### Behavior

- Timestamp is written after login
- `has_recent_auth()` checks the configured age window
- `delete_account` blocks deletion if the user has not authenticated recently
- The last active admin account cannot be deleted

## Access Boundaries to Preserve

- Anonymous users cannot access account, files, inbox, or listing authoring flows.
- Admin status is a product-level role, not blanket permission to bypass every public-surface rule.
- Realtors remain listing-only users unless promoted to admin.
- Legal acceptance must never be bypassed by direct provider redirects.
- Recent auth must not be weakened for account deletion.
