# Messaging and Realtime

## Scope

The `communications` app owns the inbox, conversation model, reply flows, unread state, soft-delete
behavior, websocket delivery, and supporting selectors and services.

## Domain Model

| Model | Purpose |
| --- | --- |
| `ListingConversation` | Listing-context or direct student-to-student conversation |
| `ListingMessage` | Individual messages inside a conversation |

### Core relationship rule

There is at most one listing conversation per `(listing, participant)` and at most one direct
conversation per student pair.

That means the listing owner never has multiple parallel threads with the same renter for the same listing,
and roommate matches do not spawn duplicate direct threads.

## Access Model

### Who can start a conversation

- authenticated, active user
- user can start listing conversations
- listing is currently public and messageable
- user is not the listing owner

### Who can start a direct roommate chat

- authenticated, active student
- sender has a completed roommate profile
- recipient is an active student with a completed roommate profile and an active roommate post, unless the direct thread already exists
- sender is not messaging themself

### Who can send a reply

- only the conversation owner or participant

### Who can view a thread

- only the conversation owner or participant
- and only while the thread is not soft-deleted for that viewer

## HTTP Surface

Routes live under `/users/messages/`:

- inbox: `/users/messages/`
- thread detail: `/users/messages/<conversation_id>/`
- reply: `/users/messages/<conversation_id>/reply/`
- delete for current viewer: `/users/messages/<conversation_id>/delete/`

The inbox is server-rendered and progressively enhanced with realtime updates.

Additional direct-message entry point:

- `/users/messages/start/user/<user_id>/`

## Websocket Surface

- Route: `/ws/messages/`
- Consumer: `communications.consumers.MessagesConsumer`
- Group naming: `messages-user-<user_id>`

### Supported incoming actions

| Action | Payload |
| --- | --- |
| `send_message` | `conversation_id`, `body` |
| `mark_read` | `conversation_id` |

### Outgoing event types

| Event | Meaning |
| --- | --- |
| `message.created` | New message plus updated conversation summary |
| `conversation.read` | Read-state change plus unread summary delta |
| `error` | Unsupported action, validation problem, or access failure |

## Service Layer Responsibilities

`communications/services.py` owns the important side effects:

- creating or reusing listing conversations
- creating or reusing direct roommate conversations
- validating conversation participants
- sending replies
- updating unread flags and preview fields
- soft-delete behavior
- publishing websocket events after commit

### Why the service layer matters

- write ordering is transactional
- websocket events must not publish before DB success
- unread summary deltas are computed centrally

## Read and Delete Semantics

### Read state

- owner and participant unread flags are stored separately
- opening a thread marks it read for the current user
- websocket read events update the active session summary

### Delete state

- delete is soft-delete per user, not immediate hard delete
- `owner_deleted_at` and `participant_deleted_at` track visibility separately
- the conversation is removed fully only after both sides delete it
- a new message restores visibility for a participant who previously deleted the thread

## Rate Limiting

Message sending is rate limited by user ID using cache-backed counters.

Relevant settings:

- `MESSAGE_SEND_RATE_LIMIT`
- `MESSAGE_SEND_RATE_WINDOW_SECONDS`

The same policy applies to HTTP reply flow and websocket send flow.

## Conversation Payload Design

Conversation serialization includes only the data needed by the inbox UI:

- listing summary when the conversation is listing-context
- roommate-chat context labels for direct conversations
- listing image URL when a listing exists
- counterparty display data
- preview text and timestamp
- unread status

Message serialization includes:

- sender identity
- sender avatar URL
- body
- timestamp

## Important Invariants

- conversation owner must match the listing owner
- owner and participant cannot be the same user
- only participants can send messages
- message bodies are normalized and length-limited
- listing conversations are unique per listing and participant
- direct conversations are unique per student pair
- realtime events are delivered only after transaction commit
