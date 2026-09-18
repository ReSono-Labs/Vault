# Changelog

Notable release changes are recorded here. The project is currently preparing
its first public development release.

## Unreleased

- Hermes and OpenClaw memory pairing rewrite the host Vault CA from `GET /vault-local-ca.crt` so a container recreate does not leave a stale dashboard certificate. Pairing POSTs and memory HTTPS stay verified.
- Connections AI & Voice can connect xAI/Grok with the same device-code OAuth Hermes and OpenClaw use (`auth.x.ai`, SuperGrok or X Premium+). The selected xAI OAuth token is what the Background Agent uses; Voice over that token is not required.
- Docker Link Companion uses the packaged host-gateway to reach the host connector. Outbound Agent Network still uses Link `https://…:8443` URLs; companion does not ask the operator to configure a proxy.
- Link collab clients that POST `/a2a/v1` are accepted on the Background Card (same JSON-RPC as `/`).
- The Background Agent Card on `:8768` answers `GET /.well-known/agent-card.json` without a bearer so Link can discover it. JSON-RPC still requires `Authorization: Bearer`.
- After Link Companion is paired, Link Agent Network apply fills External agents with Link peers (`https://…:8443` Card/RPC and directional tokens). Callers presenting a Link inbound grant bearer are accepted on the Background Card. Unpair removes those Link-managed rows. Inbound from host Hermes/OpenClaw uses published `8768`.
- External agents includes **Set up Link Companion**: confirm a pairing code from `sudo resono-link-connector companion setup vault`. Vault stores only the pairing receipt, not the host connector token. Disconnect there (or disconnect Vault in Link) ends the pairing.
- Voice starts Background Agent goals through Goal Intake (`voice_mode_switch` then `goal_start`). The Background Agent page uses the R1 delegated-work layout (run logs, progress rail, reasoning logs) and does not submit work. Empty requested tool names freeze every Background-visible tool (including MCP grants restored at run start). Background uses the same selected-provider credential and background model as Voice.

- Docker Vault publishes host loopback `8768` (override `VAULT_A2A_PORT`) and binds inbound A2A on all container interfaces so Link and other host peers can reach the Agent Card. Standalone still binds `127.0.0.1`. The Agent2Agent option remains the on/off switch for accepting work.
- Collab uses the Hermes A2A coordinator automatically whenever Agent2Agent is on. There is no separate Collab switch. Turning Agent2Agent off stops collab tools.
- Agent2Agent inbound requires `Authorization: Bearer` (not a dashboard cookie, Basic, or this Vault's outbound connection token). The Agent Card advertises Bearer; outbound connect refuses reusing the inbound secret.

- Workspace page uses the signed-in name as `{name}'s Workspace`, drops the private-files subtitle, keeps the folder title above `Up one folder`, and adds Close on file preview.
- Connections AI & Voice no longer shows Use API key or Disconnect provider; Connect OAuth and Disconnect OAuth are mutually exclusive.
- Settings Linked folders heading is larger, centered, and spaced below the separator.
- Platform Guide matches current Workspace chrome, Connections AI & Voice buttons, and Library page headings.

- Added public installation, contribution, security, conduct, and licensing
  documentation.
- Hardened remote MCP destinations against private-network and DNS-rebinding
  targets while preserving explicit loopback integrations.
- Added non-executing Plugin package risk review to extension preflight.
- Added transport-aware `Secure` session cookies while preserving the
  loopback-only HTTP compatibility bridge.
