# Hermes and OpenClaw External Memory Review

**Date:** 2026-08-29  
**Status:** `RESEARCH ONLY / CONDITIONAL`  
**Implementation authority:** None

## Question reviewed

Can Vault become the optional primary memory store for Hermes, OpenClaw, and
similar agent systems, including when Vault runs on an Orange Pi or another
edge device and the agent system runs on a different device?

## Anti-drift result

Yes, the architecture is feasible. It does **not** require another Vault agent,
direct database sharing, a new canonical memory implementation, or silent
network discovery. Vault's existing scoped memory service remains authoritative.
Hermes and OpenClaw receive small, separately installed adapters which translate
their native memory interfaces into authenticated Vault memory operations.

This is a future optional integration. This review does not authorize code,
onboarding UI, routing, device deployment, or changes to either upstream project.

Vault may also become the primary credential keystore for these integrations.
Memory and credential authority remain separately grantable. The token, broker,
raw-secret compatibility, and onboarding boundaries are reviewed in
`2026-08-29-VAULT-PRIMARY-KEYSTORE-AND-CREDENTIAL-BROKER-REVIEW.md`.

## Verified upstream interfaces

### Hermes Agent

The official Hermes repository defines pluggable memory providers. Providers
implement `MemoryProvider` and are selected through Hermes' memory-provider
discovery system. Relevant lifecycle operations include initialization, prompt
context, query prefetch, turn synchronization, tool schemas/calls, shutdown,
session-end handling, pre-compression handling, and mirroring built-in memory
writes. A provider may also implement `post_setup()` for setup-wizard work.

Hermes permits only one external memory provider at a time. Its built-in
`MEMORY.md` and `USER.md` memory remains active alongside that provider. Current
Hermes policy requires new third-party providers to ship as standalone plugin
repositories, installed under `~/.hermes/plugins/` or through a Python entry
point; they must not patch Hermes core.

Official evidence:

- <https://github.com/NousResearch/hermes-agent/blob/main/AGENTS.md>
- <https://github.com/NousResearch/hermes-agent/blob/main/agent/memory_provider.py>
- <https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/plugins.md>

**Vault fit:** a standalone Hermes `vault-memory` provider is a direct fit.
`prefetch()` maps to bounded Vault recall; `sync_turn()` and memory-write hooks
map to attributable proposals; provider tools map to explicitly granted Vault
operations. `post_setup()` may assist pairing after the user approves it.

### OpenClaw

OpenClaw's default memory is workspace Markdown (`MEMORY.md` and dated memory
files) indexed for recall. Its active memory implementation is an exclusive
plugin selected through `plugins.slots.memory`; the default is `memory-core`.
Native plugins require a manifest, and an exclusive memory plugin declares
`kind: "memory"`. Official design material also describes per-agent SQLite
state and an optional external `memory-lancedb` backend.

Official evidence:

- <https://docs.openclaw.ai/concepts/memory>
- <https://docs.openclaw.ai/cli/memory>
- <https://github.com/openclaw/openclaw/blob/main/docs/plugins/manifest.md>
- <https://github.com/openclaw/openclaw/blob/main/docs/help/faq.md>
- <https://github.com/openclaw/openclaw/blob/main/docs/refactor/database-first.md>

**Vault fit:** a native `vault-memory` plugin selected in
`plugins.slots.memory` is the intended direction. It must preserve the useful
OpenClaw file-memory compatibility expected by the installed release, or clearly
migrate it with user consent. Because the memory slot is exclusive, selecting a
Vault plugin can disable behavior owned by `memory-core`; exact compatibility
must be verified against a pinned OpenClaw release before implementation.

The database-first document is architectural direction, not sufficient proof of
a stable third-party write contract. A future donor inventory must inspect the
pinned plugin API and built-in memory plugin before freezing a build contract.

## What Vault should provide

Vault remains the sole authority for:

- user, workspace, visibility, and integration scope;
- canonical memory records, R1 labels, domains, provenance, evidence,
  reconciliation, learning, correction, retention, and deletion;
- authorization for `read`, `search`, `propose`, `correct`, and `forget` as
  independent grants;
- audit history and immediate integration revocation; and
- bounded context returned to an external agent.

External agent writes are proposals attributed to an integration identity.
They enter the existing reconciliation pipeline and never insert, update, or
delete canonical storage directly. Neither adapter receives database credentials,
a database mount, a master-user session, or another user's private memory.

## Discovery and onboarding review

### Same device

Vault may offer an optional **Connect agent systems** onboarding step. After
explicit user consent, platform-specific probes may check an executable's
presence and version and inspect only documented plugin/config locations. Do
not crawl home directories, run package installers, contact the internet, or
rewrite configuration merely because a package was detected.

Detection should report one of: `not detected`, `compatible`, `unsupported
version`, or `configured`. It is evidence for an offered action, never consent
to perform that action.

### Different device

An Orange Pi cannot reliably or safely discover arbitrary Hermes or OpenClaw
installations on other devices. Cross-device setup must use explicit pairing:

1. In Vault, the master user chooses **Pair another device**.
2. Vault creates a short-lived, single-use pairing credential without memory
   access.
3. The user runs the appropriate Vault adapter setup on the Hermes/OpenClaw
   device and supplies that credential or scans a locally displayed code.
4. The adapter authenticates the exact Vault endpoint through an approved
   transport and exchanges the credential for its own revocable integration
   identity.
5. In Vault, the user assigns that identity to one Vault user/workspace and
   selects its operation scopes and memory visibility.
6. Both sides perform a no-memory health check. Import or ongoing synchronization
   is offered separately and requires explicit confirmation.

Link or Tailscale may later provide reachability, but transport cannot grant
memory access. Vault authentication and authorization remain a separate layer.
The reviewed Link security material reaches the same boundary: target-owned
authentication must remain independent of Link authorization.

Local Link evidence reviewed read-only:

- `/home/christian/Documents/Projects/ReSono-Labs-Link/docs/security/RESO-LINK-V1-SECURITY-REVIEW-2026-08-28.md`
- `/home/christian/Documents/Projects/ReSono-Labs-Link-OpenSource/crates/link-connector/src/main.rs`

## Proposed optional onboarding placement

Keep the required first-run flow small. After the account and AI-provider
configuration, show an optional connection step with:

- **Not now**;
- **Check this device**; and
- **Pair another device**.

For each detected or paired system, the user chooses the Vault account/workspace,
private or workspace-shared visibility allowed, read/propose permissions, and
whether to import existing memory. Configuration changes require a preview and
confirmation, preserve a rollback copy where the external platform supports it,
and must be reversible from Vault's Connections management.

No automatic import, broad LAN scan, default shared-memory grant, or automatic
configuration of an under-18 account is authorized. Age-aware integration policy
belongs to the separately deferred parental-controls decision.

## Required adapters

| Adapter | Location | Responsibility | Must not own |
|---|---|---|---|
| Vault external-memory API | Vault | Scoped retrieval, proposal intake, correction/forget requests, health and revocation | Routing or third-party configuration |
| Hermes Vault memory provider | Standalone Hermes plugin | Native lifecycle translation and setup | Canonical memory or Hermes core changes |
| OpenClaw Vault memory plugin | Standalone OpenClaw plugin | Native memory-slot translation and compatibility | Canonical memory or OpenClaw state DB |
| Pairing client | Each external device adapter | One-time enrollment and credential storage | Vault master credentials |
| Optional transport | Link/Tailscale/direct TLS | Reachability only | Identity, workspace grants, or memory policy |

An MCP facade can remain available for generic consumers, but Hermes and
OpenClaw should use their native memory-plugin contracts when those contracts
cover the required behavior. MCP is an adapter, not the memory authority.

## Security and privacy gates

Before implementation can be authorized, a build contract must prove:

- mutual endpoint authentication and encrypted transport across devices;
- single-use, short-lived pairing resistant to replay and wrong-endpoint use;
- one integration identity per platform installation/profile, never per network;
- explicit mapping to one user/workspace and least-privilege operation grants;
- no cross-user retrieval, context injection, proposal, correction, or deletion;
- immediate denial after revocation, without erasing attributable audit history;
- secrets stored using the host's protected credential facility and never in
  model context, logs, plugin manifests, URLs, or QR payloads;
- bounded result sizes and resistance to malicious memory/prompt content;
- idempotent retries and conflict reconciliation rather than last-write-wins;
- export/import previews, provenance, rollback, and deletion semantics; and
- safe behavior when Vault, embeddings, transport, or the external agent is
  offline.

## Decisions and unresolved items

| Item | Status | Result |
|---|---|---|
| Vault as canonical external memory | `CONDITIONAL` | Architecturally supported; use scoped service only |
| Hermes adapter | `CONDITIONAL` | Standalone `MemoryProvider` plugin; one external provider active |
| OpenClaw adapter | `CONDITIONAL` | Native exclusive memory plugin; pin and inspect exact release first |
| Same-host discovery | `CONDITIONAL` | Opt-in, bounded executable/config probes only |
| Remote discovery | `REJECTED` | Replace network scanning with explicit pairing |
| Automatic configuration | `REJECTED` | Preview and informed confirmation required |
| Existing-memory import | `OPEN` | Requires platform-specific mapping, provenance, dedupe and rollback plan |
| Ongoing bidirectional synchronization | `OPEN` | Prefer proposal events; exact native hooks need pinned-release proof |
| Link/Tailscale | `DEFERRED` | Optional reachability only; not part of this review's implementation scope |
| Under-18 integration policy | `DEFERRED` | Must follow later parental-control decision |

## Next research gate

Before any Phase 10 build contract:

1. select and pin exact Hermes and OpenClaw releases;
2. inventory their adapter interfaces to exact source files and licenses;
3. define Vault's versioned external-memory API from the already implemented
   scoped R1 memory service;
4. define import, conflict, offline, deletion, and rollback behavior;
5. threat-model pairing and cross-device credentials independently of routing;
6. prototype contract tests with fake adapters before modifying either platform;
7. review grounding and `INDEX.MD`; and
8. obtain explicit implementation authorization.
