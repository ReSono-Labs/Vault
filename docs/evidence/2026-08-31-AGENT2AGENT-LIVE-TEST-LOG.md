# Agent2Agent Live Test Log — 2026-08-31

## Scope

This log covers the minimal outbound A2A v1.0 implementation shared by Vault Voice and the fixed Background Agent. It verifies mandatory Agent Card discovery, authenticated JSON-RPC messaging, durable continuity/task records, asynchronous completion polling, summaries/issues, the Voice-page activity surface, removal, and package inclusion.

Inbound execution of Vault by an external agent is intentionally not included. Vault does not yet have a non-human execution principal; reusing a browser session would weaken its local identity boundary.

## Automated results

- Python suite: 165 passed, 72 skipped.
- A2A protocol unit coverage: Agent Card URL policy, mandatory JSON-RPC v1.0 interface, same-origin RPC endpoint, bearer authentication, `SendMessage`, immediate-return configuration, completion summary, and failed-task issue.
- Browser Voice frontend: 9 tests passed.
- Production frontend TypeScript/Vite build: passed.
- Container image rebuild and package deployment: passed.
- Runtime migration created `vault_a2a_connections`, `vault_a2a_conversations`, and `vault_a2a_tasks` in `vault_private`.

## Installed Hermes live proof

Installed peer: Hermes Agent 0.20.5, listening on loopback port 9900.

1. Loaded `/.well-known/agent-card.json`.
2. Confirmed the card advertised JSON-RPC protocol version 1.0 and a bearer security scheme.
3. Sent an authenticated A2A `SendMessage` request with a stable `contextId` and immediate-return preference.
4. Hermes returned `TASK_STATE_COMPLETED`, a remote task ID, the same context ID, and the exact artifact text `VAULT A2A OK`.

The failed unauthenticated probe returned `unauthorized`, confirming that the installed Hermes endpoint enforces its advertised authentication boundary.

## Installed OpenClaw live proof

Installed peer: OpenClaw 2026.8.1 with its bundled `a2a` channel enabled.

1. Configured the channel for the local host bridge and a dedicated Vault bearer peer.
2. Set direct/source replies to `automatic`. Before this correction, OpenClaw completed the internal model run but its message-tool-only delivery mode suppressed the final A2A payload and left the remote task working.
3. Loaded and stored OpenClaw's mandatory A2A v1.0 Agent Card through the packaged Vault service.
4. Sent the request through `A2AService.send`, not a simulated adapter.
5. OpenClaw returned `TASK_STATE_COMPLETED` and the exact summary `VAULT OPENCLAW A2A COMPLETE`.
6. Deleted the proof task and its proof conversation while retaining the validated OpenClaw connection.

## Product behavior verified by construction and tests

- Voice and Background share the same `agent2agent_list` and `agent2agent_send` tools.
- Continuity is persisted by connected agent, user/workspace, owner kind, and Voice session or Background run ID.
- A poller independent of a Voice connection persists terminal state, result summary, or peer-reported issue.
- The Voice page polls durable activity, showing only the five latest completed tasks. Each row is a one-line summary that opens a full review dialog.
- Removing a connection deletes its credentials, conversation continuity, and task rows through database cascades, preventing stale connection/activity lists.
- Bearer credentials are AES-GCM encrypted with a local package key and never returned by the management API.

## Known boundary

The in-app browser could not open the deployed loopback HTTPS page because its isolated browser had not trusted Vault's local certificate. Browser policy forbids bypassing that warning. UI behavior was therefore verified through the frontend test suite and production build, while the deployed runtime, database migration, and Hermes protocol were verified live.

The packaged Vault uses Docker's `host.docker.internal` bridge for the installed local Hermes and OpenClaw gateways. Remote agents use the same Agent Card and A2A code path over an approved HTTPS Link/Tailscale/reverse-proxy address.
