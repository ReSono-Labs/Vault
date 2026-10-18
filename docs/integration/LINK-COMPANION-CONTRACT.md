# Link Companion ⇄ Vault contract (owner chat + Agent Network)

Status: implemented in Vault on `feature/link-companion-owner-chat` (2026-10-18). The connector side follows this.

All calls go to `http://127.0.0.1:8766` (Vault's loopback bridge).

## Pairing issues the companion credential

1. `POST /link-companion/pairing/start` with `{"displayName", "pollToken"}`. This is unchanged.
2. The owner approves the code in Vault (External agents → Set up Link Companion).
3. The connector polls `POST /link-companion/pairing/status` with `{"pairingId", "pollToken"}`.
   - The first poll after approval returns `{"status": "approved", "companionToken": "<secret>"}`.
   - The token is returned once. Later polls return only `{"status": "approved"}`.
   - The token can be collected for 10 minutes after approval.
   - The connector stores the token as a secret (root-only state). It is never logged.
4. Every call below sends `Authorization: Bearer <companionToken>`.

About the credential:
- It is a dedicated owner session, separate from browser sessions.
- It slides forward on use, so it effectively never expires while it is used.
- It is revoked when:
  - the owner clicks Unpair;
  - the owner pairs again (the old token stops working at once);
  - the owner's password changes (Vault revokes all other sessions).
- Any call with a missing, revoked or wrong token gets 401 `{"error":"not_paired"}`. `agent-network/apply` returns 403 instead.
- When that happens, stop retrying and run `companion setup vault` again.

Vault records why a companion was revoked, in `link_companion_pairings.revocation_reason`. The values are `owner_unpaired` and `replaced_by_new_pairing`.

## Agent Network

`POST /link-companion/agent-network/apply` now requires the bearer token. The body and response are unchanged.

## Owner chat

| Call | Response |
|---|---|
| `GET /link-companion/chat/health` (token not required) | `{"ready": bool, "images": bool}`. `ready` means the companion is paired with a live credential and Chat is running. |
| `POST /link-companion/chat/sessions` with body `{}` | 201 `{"id": "<conversation id>"}` |
| `POST /link-companion/chat/sessions/{id}/messages` with body `{"text", "images"?, "client_message_id"?}` | 202 `{"run_id": "..."}`, returned at once without waiting for the agent |
| `GET /link-companion/chat/runs/{run_id}` | `{"state": "queued\|running\|completed\|failed", "session_id", "text"?, "error"?}`. `text` is present when completed; `error` is `failed` or `interrupted`. |
| `GET /link-companion/chat/sessions/{id}/messages?before=&limit=` | `{"messages": [{"id", "role": "user\|assistant", "text", "timestamp"}], "next_before": int\|null}`, oldest first |

Messages:
- **Retries:** send a `client_message_id` (1–100 characters, unique per message). A retry with the same ID returns the same `run_id` and does not send twice.
- **Images:** JPEG, PNG, GIF or WebP, as standard base64. Up to 4 per message, 1.5 MB each. A GIF becomes its first frame as a PNG. A message may be images only.
- **One turn at a time:** a second message while a turn is running in the same session returns 409 `busy`.
- **Confirmations are plain text:** when an action needs the owner's approval, the agent asks in its reply, and the owner answers in the next message.

History:
- It contains only visible user and assistant text: no tools, system prompt, internal steps or cards.
- Pages hold up to 100 turns, newest page first. Pass `next_before` as `before` to get older pages.

Sessions:
- Phone conversations are the owner's normal Vault chats. They appear in Vault's Chat history and go through the same memory and learning review.

Errors are `{"error": "<code>"}` with no other detail:

| Code | Status |
|---|---|
| `not_paired` | 401 |
| `not_found` | 404 |
| `rejected` | 400 |
| `busy` | 409 |
| `unavailable` | 503 |

The connector never has to hold a connection open; it polls `runs/{run_id}` (every 1–2 s is fine).
