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
| `student` | Default for configured student domains such as `bc.edu` | Can browse the login-gated marketplace | Can message about listings | No |
| `realtor` | Default for non-student external domains | Listing-only access to own inventory | Cannot initiate listing conversations | No |
| `moderator` | Explicit staff assignment only | Can browse the login-gated marketplace | Cannot initiate listing conversations | Listing/reports queues only |
| `support` | Explicit staff assignment only | Can browse the login-gated marketplace | Cannot initiate listing conversations | Support investigations only |
| `platform_admin` | Explicit staff assignment only | Can browse the login-gated marketplace | Cannot initiate listing conversations | Full staff workspace |

### Role policy rules

- `CustomUser.apply_email_role_policy()` keeps non-staff roles aligned with the current email policy.
- `set_admin_access(True)` remains a compatibility helper for promoting a user to `platform_admin`.
- `set_staff_role()` is the supported way to assign `moderator`, `support`, or `platform_admin`.
- Removing staff access returns the user to the email-derived default role.
- `set_user_role` is the supported operational command for role changes outside the UI.
- The Padly staff roles control the custom staff workspace. Raw Django `/admin/` access is still governed separately by Django staff permissions and is not auto-synced.

## User Model

`users.models.CustomUser` extends `AbstractUser` and adds:

- unique normalized email
- role
- profile completion timestamp
- account lifecycle fields for deactivation and anonymized closure
- legal acceptance timestamps and version
- profile image URL fallback

Useful computed properties include:

- `can_browse_marketplace`
- `can_start_listing_conversations`
- `can_use_roommate_matching`
- `has_listing_only_access`
- `can_access_staff_console`
- `can_manage_listing_moderation`
- `can_manage_reports`
- `can_manage_user_roles`
- `can_manage_user_status`
- `can_open_support_investigations`
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
2. If the current legal version has not been reviewed, the page switches into a stepped legal-review flow.
3. Privacy Policy is reviewed first, then Terms of Service.
4. The user must scroll each document before its acknowledgement unlocks.
5. A pending legal acceptance payload is stored in session state.
6. Allauth completes Google login and the adapter validates verified email identity.
7. The pending legal acceptance is persisted to the user record.

## Legal Acceptance

Legal acceptance is versioned by `LEGAL_DOCUMENT_VERSION`.

### Rules

- Users accept Terms and Privacy together.
- Acceptance is stored both in the session during the pre-OAuth flow and on the user after login succeeds.
- Users with stale acceptance are logged out by middleware and forced back through the review flow.
- Existing users with current acceptance are not asked again for the same version.

## Inactive Accounts

- `ActiveAccountMiddleware` logs out authenticated users whose accounts are no longer active and redirects them back to login.
- Listings owned by inactive accounts are removed from landing-page teasers, marketplace results, live search, and normal listing-detail access.
- Existing inbox threads remain visible to the active counterparty, but sending becomes read-only while either participant is inactive.

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
- Enforced for students, realtors, moderators, support users, and platform admins
- Redirect target is `/users/profile/setup/`
- Completion is recorded with `profile_completed_at`

### Profile models

| Model | Applies To | Purpose |
| --- | --- | --- |
| `StudentProfile` | student users | roommate and lifestyle questionnaire plus profile basics |
| `AdminProfile` | realtor and staff users | lightweight profile record used for completion and display |

### Profile lifecycle rules

- Promoting a student to admin creates or updates `AdminProfile` but preserves the existing `StudentProfile` for future reuse.
- Promoting a user to realtor creates or updates `AdminProfile`, removes `StudentProfile`, and clears `profile_completed_at`.
- Returning to `student` reuses preserved `StudentProfile` data when it still exists; otherwise a blank student profile is created and completion stays unset until the required fields are filled.
- `repair_profile_completion_integrity` is the operational command for recalculating `profile_completed_at` from the current role and current profile data.

## Dashboard and Workspace Access

### User dashboard

- `/users/dashboard/`
- Acts as the main account workspace
- Prioritizes document library, inbox, listings, and roommate discovery actions
- Shows recent listings and recent messages in one activity surface
- Surfaces the primary entry point into the roommate-post board

### Listing-only users

- Realtors do not browse the normal marketplace
- Their primary workspace is `/users/posts/`

### Staff users

- Can see the account workspace and the custom staff workspace
- Gain a staff dashboard link in the shared profile menu
- Sensitive user files and message previews require an active support investigation with a reason

## Recent Authentication

Account deletion and privileged staff actions are gated by recent-auth timestamps stored in the session.

### Behavior

- Timestamp is written after login
- `has_recent_auth()` checks the configured age window
- `has_recent_privileged_auth()` uses the shorter staff-action window
- `delete_account` blocks deletion if the user has not authenticated recently
- The last active platform admin account cannot be deleted

## Access Boundaries to Preserve

- Anonymous users cannot access account, files, inbox, or listing authoring flows.
- Staff status is a product-level role, not blanket permission to bypass every public-surface rule.
- Realtors remain listing-only users unless promoted to a staff role.
- Legal acceptance must never be bypassed by direct provider redirects.
- Sensitive support access must be opened with a reason and audited.
- Recent auth must not be weakened for account deletion or privileged staff actions.
