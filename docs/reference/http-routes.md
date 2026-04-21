# HTTP Routes

## URL Root Composition

`vibecoders/urls.py` mounts the application like this:

| Prefix | Destination |
| --- | --- |
| `/` | `core.urls` |
| `/users/messages/` | `communications.urls` |
| `/users/` | `users.urls` |
| `/accounts/login/` | custom `users.views.login_page` |
| `/accounts/google/login/` | custom `users.views.google_login_gate` |
| `/accounts/` | Allauth routes |
| `/listings/` | `listings.urls` |
| `/admin/` | Django admin |

Padly also exposes these narrow media routes in every environment:

| Route | View | Auth | Purpose |
| --- | --- | --- | --- |
| `/media/listing_photos/<path>` | `listings.views.public_listing_photo` | conditional by listing visibility | serve listing images without exposing a blanket media root |
| `/media/avatars/<path>` | `users.views.public_avatar` | public | serve uploaded profile avatars still attached to a user |

## Core Routes

| Route | View | Auth | Purpose |
| --- | --- | --- | --- |
| `/` | `core.views.landing` | optional | landing page |
| `/healthz/` | `core.views.healthz` | optional | lightweight Render health check endpoint |
| `/readyz/` | `core.views.readyz` | optional | readiness check for DB, cache, channels, storage, and migrations |
| `/welcome/` | `core.views.welcome` | required | post-login redirect target |
| `/terms/` | `core.views.terms_of_service` | optional | Terms of Service |
| `/privacy/` | `core.views.privacy_policy` | optional | Privacy Policy |

## User and Account Routes

| Route | View | Auth | Purpose |
| --- | --- | --- | --- |
| `/users/login/` | `users.views.login_page` | anonymous | custom login page with embedded stepped legal review when required |
| `/users/profile/` | `users.views.profile` | required | redirect to dashboard |
| `/users/profile/setup/` | `users.views.profile_setup` | required | profile completion/update |
| `/users/dashboard/` | `users.views.dashboard` | required | account workspace |
| `/users/browse/` | `users.views.browse_roommates` | student users | legacy redirect into `/listings/group-match/` |
| `/users/profile/<user_id>/` | `users.views.public_profile` | student users | public roommate profile |
| `/users/posts/` | `users.views.posts` | required | current user's listings |
| `/users/files/` | `users.views.files` | required | private document library |
| `/users/files/<file_id>/preview/` | `users.views.file_preview` | required | authenticated inline preview |
| `/users/files/<file_id>/download/` | `users.views.file_download` | required | authenticated download |
| `/users/files/<file_id>/delete/` | `users.views.delete_file` | required + POST | delete own file |
| `/users/account/delete/` | `users.views.delete_account` | required + POST | anonymize and deactivate account after recent auth |

## Staff Workspace Routes

| Route | View | Auth | Purpose |
| --- | --- | --- | --- |
| `/users/admin-dashboard/` | `users.admin_views.admin_dashboard` | any staff role | operations overview |
| `/users/admin-listings/` | `users.admin_views.admin_listings` | moderator or platform admin | listing review queue |
| `/users/admin-listings/<listing_id>/` | `users.admin_views.admin_listing_detail` | moderator or platform admin | listing moderation detail |
| `/users/admin-listings/<listing_id>/review/` | `users.admin_views.admin_review_listing` | moderator or platform admin + POST | approve or reject listing |
| `/users/admin-listings/<listing_id>/delete/` | `users.admin_views.admin_delete_listing` | moderator or platform admin + POST | archive listing |
| `/users/admin-reports/` | `users.admin_views.admin_reports` | moderator or platform admin | listing reports queue |
| `/users/admin-reports/<report_id>/status/` | `users.admin_views.admin_update_report` | moderator or platform admin + POST | update report status and append moderation history |
| `/users/admin-users/` | `users.admin_views.admin_users` | any staff role | user administration overview |
| `/users/admin-users/<user_id>/` | `users.admin_views.admin_user_detail` | any staff role | user detail with sensitive data gated behind investigations |
| `/users/admin-users/<user_id>/investigation/` | `users.admin_views.admin_open_investigation` | support or platform admin + POST | open time-boxed sensitive access with a required reason |
| `/users/admin-investigations/<investigation_id>/close/` | `users.admin_views.admin_close_investigation` | support or platform admin + POST | close sensitive access |
| `/users/admin-users/<user_id>/role/` | `users.admin_views.admin_set_role` | platform admin + POST | assign or restore role |
| `/users/admin-users/<user_id>/active/` | `users.admin_views.admin_toggle_active` | platform admin + POST | toggle active status |

## Listing Routes

| Route | View | Auth | Purpose |
| --- | --- | --- | --- |
| `/listings/` | `listings.views.listing_list` | required | marketplace list/map view or listing-only inventory |
| `/listings/search/` | `listings.views.listing_search` | required | JSON live-search endpoint |
| `/listings/address-suggestions/` | `listings.views.address_suggestions` | authenticated in practice | JSON address autocomplete endpoint; returns JSON `401` instead of redirecting to HTML login when signed out |
| `/listings/group-match/` | `listings.views.group_match` | student users | roommate-post board and filters |
| `/listings/group-match/post/` | `listings.views.save_roommate_post` | completed student + POST | create, update, or reactivate own roommate post |
| `/listings/group-match/post/pause/` | `listings.views.deactivate_roommate_post` | completed student + POST | pause own roommate post |
| `/listings/<pk>/` | `listings.views.listing_detail` | required | listing detail |
| `/listings/<pk>/review/` | `listings.views.submit_listing_review` | eligible student + POST | submit or update review |
| `/listings/<pk>/report/` | `listings.views.report_listing` | eligible student + POST | submit report |
| `/listings/<pk>/message/` | `listings.views.message_listing` | eligible student + POST | start conversation |
| `/listings/<pk>/favorite/` | `listings.views.toggle_favorite` | eligible user + POST | save or unsave listing |
| `/listings/create/` | `listings.views.create_listing` | required | create listing |
| `/listings/edit/<pk>/` | `listings.views.edit_listing` | owner | edit listing |
| `/listings/delete/<pk>/` | `listings.views.delete_listing` | owner + POST | delete listing |

## Messaging Routes

| Route | View | Auth | Purpose |
| --- | --- | --- | --- |
| `/users/messages/` | `communications.views.messages_inbox` | required | inbox |
| `/users/messages/<conversation_id>/` | `communications.views.messages_inbox` | required | selected thread in inbox |
| `/users/messages/start/user/<user_id>/` | `communications.views.start_direct_conversation_view` | completed student + POST | start or reuse direct roommate chat |
| `/users/messages/<conversation_id>/reply/` | `communications.views.reply_conversation` | participant + POST | send reply |
| `/users/messages/<conversation_id>/delete/` | `communications.views.delete_conversation` | participant + POST | soft-delete thread for current user |

## Websocket Route

| Route | Consumer | Auth |
| --- | --- | --- |
| `/ws/messages/` | `communications.consumers.MessagesConsumer` | authenticated active user |

## Notes on Allauth Routes

Padly still mounts Allauth under `/accounts/`, but the application intentionally routes users into the custom login flow. Non-Google and password-centric routes are considered disabled product paths.
