# Vault Network Page and Remote Access Plan

Status: planning only. No Vault, Link, connector, Tailscale, host-service, or
deployment changes are authorized by this document.

## Goal

Give the Vault owner one simple **Network** page for reaching Vault away from
this computer. ReSono Link is the primary route. Tailscale is a later optional
route. Local Vault use must continue when either route is unavailable.

## Grounded current state

- Vault runs in Docker and publishes HTTPS as host loopback
  `127.0.0.1:8765`.
- The Vault container has no Linux capabilities and does not use host
  networking. It has `host.docker.internal` mapped, but it does not receive
  Link's files, socket, credentials, or service account.
- ReSono Link connector `0.2.22` is installed as the enabled, hardened host
  service `resono-link-connector.service` under the dedicated `resono-link`
  account.
- The installed connector is currently not associated with a Link account.
- The connector's supported discovery profiles are exactly Hermes web on
  `127.0.0.1:9119`, Hermes A2A on `127.0.0.1:9900`, and OpenClaw web on
  `127.0.0.1:18789`.
- The connector does not currently define or discover a Vault web profile.
- Vault can therefore be reached by the host connector at its published
  loopback port, but the current Link product has no supported contract that
  permits it to publish Vault.

## Non-negotiable boundaries

1. Do not modify, repackage, patch, or replace the installed Link connector as
   part of Vault work.
2. Do not mount `/var/lib/resono-link`, Link keys, connector credentials, or
   the Docker socket into Vault.
3. Do not give Vault host networking, root, systemd control, or permission to
   execute the Link CLI.
4. Do not label Vault as Hermes or OpenClaw to reuse an existing Link profile.
5. Do not use Link's private MCP route as a generic web tunnel.
6. Do not expose PostgreSQL or any internal Vault-only service.
7. Network controls are installation-wide and available only to the permanent
   Vault owner. They are not per-user workspace settings.
8. Removing a remote route must not delete Vault data, accounts, agents,
   memory, or the local installation.

## Required Link-side prerequisite

Native Link support needs a separately owned Link change before Vault can use
it. That work is outside this Vault build and must follow Link's own review,
release, and security process.

The minimum Link-side result is a supported `vault_web` service contract that:

- targets only `127.0.0.1:8765` on the connector host;
- validates a Vault-specific readiness response before activation;
- publishes HTTPS and WebSocket traffic needed by the Vault browser and Voice;
- preserves the original public Host and Origin values in the supported Link
  forwarding contract;
- leaves Vault login and session authorization in Vault;
- never receives Vault passwords, sessions, provider credentials, prompts,
  memory, mail, or agent content;
- reports only route identity, lifecycle, health, and public address to the
  Link account interface; and
- supports explicit disable, revoke, and remove operations.

Vault work must not begin route activation until that contract exists in a
released Link version and passes a clean-host test. Merely detecting the Link
service is not proof that Vault routing is supported.

## Vault-side design after the Link prerequisite exists

### Readiness endpoint

Add one small unauthenticated Vault readiness endpoint intended for the local
Link connector. It returns only:

- product identifier `resono-vault`;
- a readiness-contract version;
- whether browser authentication is enabled; and
- whether HTTPS and browser Voice WebSocket handling are ready.

It returns no account, workspace, version-detail, hostname, provider, agent,
memory, or storage information. Link must reject activation unless the exact
product and security fields match.

### Ownership and stored state

Vault stores only the owner's selected network provider and the minimum route
display state: provider, public address, status, last successful check, and a
provider-owned route reference. Link credentials and connector identity remain
outside Vault.

The public address is accepted only from the supported Link handoff/contract;
the user cannot enter an arbitrary proxy URL and mark it trusted.

### Setup flow

1. Owner opens **Network** and chooses **Set up Link**.
2. Vault explains that Link is installed separately and that Vault login still
   protects the public page.
3. Vault opens the Link-owned browser approval/setup flow.
4. Link associates the existing host connector if needed and offers the
   supported Vault service.
5. Link activates the exact Vault route after its own approval and readiness
   checks.
6. Vault receives or verifies the resulting public address through the
   supported contract.
7. Vault performs a bounded external check of its public health and login
   landing page. It does not log in through the check.
8. The page shows **Available remotely** only after the check passes.

Interrupted setup resumes the same Link operation. It must not create duplicate
hosts or routes.

### Disable and removal

- **Pause remote access** disables the Link route but keeps the Link host
  association and local Vault unchanged.
- **Remove Link from Vault** removes the Vault route and Vault's display state.
- **Disconnect this computer from Link** is a separate Link-owned action and
  must be completed in Link; Vault does not delete Link's connector identity.
- Vault clearly states when Link still has a host association after the Vault
  route is removed.

## Network page

Add **Network** to the main sidebar between Connections and Agent2Agent. The
page has one heading and no developer terminology in its default view.

### Default view

**Network**  
Reach your Vault securely when you are away from this computer.

Two provider rows:

1. **ReSono Link** — primary, with one status and one relevant action.
2. **Tailscale** — labeled **Coming later** until its implementation is
   authorized.

The Link row may show only these user states:

- Not set up
- Setup needs attention
- Connecting
- Available remotely
- Paused
- Unavailable

When available, show the public Vault address with **Open Vault**, **Copy
address**, and **Manage**. Raw IDs, ports, revisions, certificates, and probe
output stay inside an optional details panel.

### Link setup panel

Show only after the owner chooses **Set up Link**:

- what will become remotely available;
- confirmation that Vault login remains required;
- confirmation that local Vault data is not copied to Link;
- the Link-owned approval action; and
- cancel.

Do not show connector forms, local ports, bearer tokens, or route fields.

### Manage panel

Show:

- current address;
- last successful check in plain language;
- **Test connection**;
- **Pause remote access** or **Resume remote access**;
- **Remove Link from Vault**; and
- a collapsed troubleshooting area with the exact next action.

## Tailscale later

OpenClaw's current model is useful as a behavior reference, not code to copy:
keep the application bound to loopback, let Tailscale Serve provide tailnet
HTTPS, distinguish private Serve from public Funnel, and never treat
`tailscale.mode=off` as proof that the Tailscale daemon is stopped.

For Vault, the later first release should support **Tailscale Serve only**.
Funnel is public exposure and should remain out of scope until a separate
security and authentication review. Vault must continue to require its own
login; Tailscale identity headers must not silently become Vault accounts.

Because Vault is containerized while `tailscaled` normally runs on the host,
do not copy OpenClaw's host-network/container-socket pattern into Vault without
a separate review. The preferred later design is a narrow host-owned helper or
installer-controlled host command that creates one exact Serve route to
`127.0.0.1:8765`. Vault should observe the result, not control the Tailscale
daemon broadly.

## Build sequence

### Gate 1 — Link contract

- Define and approve the Vault service contract in the Link project.
- Release it through Link's normal package process.
- Prove clean install, setup, retry, restart, disable, removal, and host reboot.
- Prove HTTP, WebSocket Voice, login, logout, and account isolation through the
  assigned public address.

No Vault route code proceeds if this gate is absent.

### Gate 2 — Vault backend

- Add the minimal readiness endpoint.
- Add owner-only network status and lifecycle APIs.
- Store only minimum provider/route display state.
- Add bounded public-address verification with SSRF and redirect controls.
- Add audit events for setup, activation, test, pause, resume, and removal.

### Gate 3 — Network page

- Add the sidebar destination and single-heading page.
- Add Link states, setup, manage, test, pause/resume, and removal flows.
- Add Tailscale as a non-interactive **Coming later** row.
- Add desktop and mobile tests for every state and destructive confirmation.

### Gate 4 — Package verification

- Build from the Vault package, not a direct runtime edit.
- Test local Vault before, during, and after Link failure.
- Test container recreation and host reboot.
- Confirm no Link state, socket, Docker socket, host networking, or extra Linux
  capability entered the Vault container.
- Confirm route removal leaves local Vault healthy and all data intact.

## Acceptance criteria

- A nontechnical owner can set up supported Link access from the Network flow
  without entering a port, hostname, token, or connector command into Vault.
- Remote Voice and normal browser use work through the public Link address.
- Vault login is always required.
- Secondary users cannot change installation-wide network exposure.
- Link outage never prevents local Vault use.
- Setup retry creates no duplicate route.
- Pause, resume, and removal have distinct, truthful outcomes.
- Vault contains no Link private keys or connector credentials.
- Tailscale is not presented as working before it is implemented and tested.

## Explicit current conclusion

The Network page can be designed now, but native Link activation cannot be
built honestly against Link connector `0.2.22` because it has no supported
Vault service profile. Under the no-Link-package-change rule, the next action
is to approve a separate Link-side Vault service contract or use Tailscale as
the interim remote-access route. No unsupported profile reuse is acceptable.
