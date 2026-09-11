# Extension and Shared-Memory Extraction Addendum

Date: 2026-08-28  
Status: research-derived planning input; not an active build contract  
Authority: documentation request only; no implementation or scope expansion

## Controlling boundary

This addendum records how secondary R1 behavior may fill demonstrated gaps in
the existing Voice Vault extraction. Voice Vault runtime and Browser Voice are
primary. This document does not authorize replacing their architecture.

Current-source evidence is documented in
[`docs/research/2026-08-28-extension-imports-and-memory-architecture.md`](../research/2026-08-28-extension-imports-and-memory-architecture.md).

Vault must have no required ReSono Labs cloud or account dependency. Local web
management owns onboarding, users, workspaces, extensions, memory, backups and
settings. Initial onboarding requires only a name and preferred interaction
experience. Remote management is a later adapter over the same authenticated
local API, not a second control plane.

## Reuse boundary

Extract these behaviors rather than redesigning them:

- quarantined archive inspection and content-hash-bound confirmation;
- Plugin component ownership, replacement, rollback and recovery;
- Agent Skill parsing and progressive disclosure;
- MCP configuration/credential separation, discovery and explicit tool grants;
- one canonical Tool Catalog with audience, effect and per-run intersections;
- post-session evidence-backed memory review;
- domain/type separation, reconciliation, immutable versions and provenance;
- hybrid exact/lexical/semantic retrieval; and
- confirmation-protected memory correction and forgetting.

Replace these device-global assumptions:

- `subject_id="primary"`;
- global management/search/context memory queries;
- device-global extension enablement and credentials;
- Voice/Text audience as the only authorization dimension; and
- ReSono-specific `platform` memory semantics.

## Dependency order for later planning

1. Define local `user_id`, `workspace_id`, membership and visibility scopes.
2. Extend invocation/session context with the authenticated principal.
3. Migrate transcripts, summaries, memory, evidence, vectors and pending
   actions to scoped keys and queries.
4. Add a canonical authenticated memory HTTP service.
5. Add an MCP adapter over that service for Hermes and other builds.
6. Intersect extension audience with user/workspace/integration grants.
7. Make installation owner-controlled and enablement appropriately scoped.
8. Port Browser Voice/R1 only after the scoped authority paths pass negative
   cross-user tests.

The service is the authority boundary. MCP, Link, OpenClaw, Hermes, and future
agent protocols are replaceable authenticated adapters. Each integration gets
its own identity and independently grantable read, propose, correct, forget,
and administration capabilities. External submissions enter the evidence and
reconciliation pipeline; they do not write canonical rows directly.

Future onboarding may offer an optional agent-system connection after account
and AI-provider setup. Same-host discovery is limited to user-approved,
platform-specific executable/version/config probes. An agent on another device
is never found by broad LAN scanning: it is enrolled through a short-lived,
single-use pairing flow and receives its own revocable integration identity.
Detection is not consent to install, configure, import, or synchronize memory.
See `../research/2026-08-29-HERMES-OPENCLAW-EXTERNAL-MEMORY-REVIEW.md`.

## Material decision gate

Question: may R1's device-global extension and memory model replace the existing
Voice Vault implementation?

- Governing direction: the target has separate local accounts/workspaces and
  optional shared memory.
- Evidence: current source uses `primary`, global queries and device-global
  extension ownership.
- Alternatives: copy unchanged; replace everything; extract behavior and add
  scoped authority.
- Decision: no. Merge the required updated R1 memory behavior and only missing
  extension controls into existing Voice Vault boundaries.
- Counterexample: any query, tool or integration can retrieve another user's
  private record without a matching grant.
- Dependents: schema, APIs, session context, tools, MCP, Hermes, UI and tests.
- Status: `CONDITIONAL` — suitable as planning input; implementation requires a
  separately accepted build contract and migration design.

## Minimum evidence for an accepted future plan

- User A cannot list, search, inject, explain, correct, delete or reindex User
  B's private memory.
- Workspace-shared memory is visible only to current members.
- Revoking an integration immediately removes its memory and tool catalog.
- Revoking an integration also denies new reads/writes without deleting
  attributable history required for audit and reconciliation.
- Hermes or OpenClaw cannot read private memory unless its exact user/workspace
  scope and operation were explicitly granted.
- Two integrations proposing different values produce normal reconciliation or
  conflict state rather than silent last-write-wins replacement.
- Plugin/MCP credentials remain scoped and never appear in manifests or model
  context.
- An unavailable embedding provider leaves canonical writes and lexical recall
  working.
- Extension safe mode boots with all third-party Skills, Plugins and MCP
  connections disabled.
- Removal and failed replacement preserve ownership and recover deterministically.
