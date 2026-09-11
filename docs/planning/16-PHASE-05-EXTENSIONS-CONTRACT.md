# Phase 5 Plugins, Skills and MCP Contract

Status: accepted build contract  
Entry: Phase 4 anti-drift exit complete  
Authority: `GROUNDING.md`, `INDEX.MD`, Phase 5 donor inventory

## User-visible outcome

An authenticated local device owner can preflight and confirm a Plugin, Agent
Skill or MCP configuration. A workspace member sees or uses only capabilities
explicitly enabled for that user/workspace and fixed system-agent role. The
system starts safely with third-party extensions disabled when safe mode is
selected. No ReSono Labs account or service is involved.

## In scope

1. Safe ZIP/TAR quarantine with bounded size/count/expansion and no traversal,
   links, encrypted entries, duplicate case-folded paths or special files.
2. Pinned Plugin/MCP schema validation and standard Agent Skill parsing.
3. Hash-bound, expiring preflight confirmation; replacement must be explicit.
4. Durable Plugin, Skill, MCP connection, component ownership, grants and
   lifecycle history scoped to local users/workspaces.
5. Atomic install/replace with previous-version rollback and startup recovery.
6. Skill metadata discovery and just-in-time instruction loading with a second
   lifecycle/scope check.
7. MCP configuration/secret separation, transport validation, discovery,
   explicit per-tool effect/grants and projection into canonical `ToolCatalog`.
8. Disable, revoke and remove behavior that immediately removes runtime
   projection.
9. Safe mode that suppresses all third-party capability projection.
10. Owner-only mutation endpoints using existing local session, strict JSON and
    CSRF controls.
11. Non-executing package risk review over quarantined Plugin bytes, returned
    as advisory preflight findings without creating an agent identity or
    weakening deterministic rejection and owner confirmation.

## Immutable agent rule

`SYSTEM_AGENT_INVENTORY` remains exactly Voice Agent and Background Agent.
Plugin, Skill, MCP and tool records may reference those two values only as an
audience. Phase 5 must expose no agent registration, creation, generation,
selection, publication or delegation API. There is no Build Agent.

## Scope and authority

- Installation, replacement, removal and credential changes require the local
  device owner.
- Enablement/grants are keyed by `user_id`, `workspace_id`, component identity
  and `AgentKind`.
- Reads and invocation require an active workspace membership plus the exact
  grant.
- Revocation removes catalog/instruction projection before success is returned.
- Discovery and manifest declarations grant nothing.
- Skill `allowed-tools` grants nothing.
- MCP annotations/effect hints are untrusted; owner confirmation controls the
  canonical effect class.
- Credentials are never stored in an archive tree, manifest, prompt, catalog
  description, log or API response.

## Filesystem contract

All paths derive from `resolve_vault_data_root()`:

```text
extensions/
  quarantine/<candidate-id>/
  plugins/<plugin-id>/current/
  plugins/<plugin-id>/previous/
  skills/<skill-id>/current/
  skills/<skill-id>/previous/
  recovery/<operation-id>.json
```

Install uses a same-filesystem staging directory and atomic rename. Candidate,
root and component paths are canonicalized and confined beneath their expected
root. Recovery records contain identifiers and hashes, never secrets.

## Plugin contract

- One archive root and root `plugin.json` are required.
- Invalid embedded Skills or MCP documents make confirmation fail; partial
  component installs are forbidden.
- Component names are exclusive within the effective workspace scope.
- Replacement is permitted only with a fresh preflight bound to the current
  installed hash.
- Disable/remove follows recorded ownership; it cannot remove components owned
  by another Plugin or direct import.
- Plugin content is data. Python/shell/JavaScript is not imported into Vault's
  trusted process merely by installation.

## Skill contract

- Parser behavior follows the public Agent Skills format recorded in research.
- Listing returns only name/description metadata for enabled, granted Skills.
- Loading returns the instructions only after rechecking active membership,
  lifecycle, safe mode and agent audience.
- Resource access remains confined to the Skill root.
- No Skill script executes automatically.

## MCP contract

- Phase 5 executes Streamable HTTP. SSE and stdio may validate as standard
  configuration but remain disabled until a later explicit transport gate.
- Non-loopback HTTP is rejected; remote endpoints require HTTPS.
- URL userinfo/fragments and credential-bearing public headers are rejected.
- Private, link-local, metadata, multicast and reserved destinations are
  rejected; DNS destinations are resolved and revalidated immediately before
  each request. Explicit loopback endpoints remain supported.
- `initialize` negotiates protocol revision `2025-11-25`; `tools/list` handles
  pagination with count/page/response limits.
- Duplicate/invalid tool names, invalid schemas and malformed results fail
  discovery or invocation.
- Each enabled tool has an explicit effect and Voice/Background grant.
- Dynamic source replacement in `ToolCatalog` is atomic; collision leaves the
  prior catalog intact.
- Calls have timeouts and bounded response sizes, validate input and structured
  output when declared, and write invocation evidence.

## Required negative tests

1. Traversal, absolute paths, symlinks, hardlinks, encrypted ZIP entries,
   case-fold collisions, zip bombs, too many entries and multiple roots fail.
2. Invalid Plugin/MCP schemas and malformed/oversized/non-UTF-8 Skills fail.
3. A stale/expired/wrong-principal/wrong-hash confirmation token fails.
4. Replacement without explicit consent fails and preserves current content.
5. Cross-user and cross-workspace list/load/invoke attempts fail.
6. Revoked membership/grant, disabled component/connection and safe mode fail
   closed immediately.
7. Discovery without grants produces zero catalog tools.
8. Embedded credentials, remote HTTP, SSRF-prone endpoint forms and unsupported
   transports fail before I/O.
9. Tool name/schema collisions and failed projection preserve prior catalog.
10. Plugin removal cannot delete another owner's component.
11. No secret appears in persistence, logs, API output or model-visible data.
12. Production-source scan proves no third agent or Build Agent surface.

## Exit gate

Phase 5 completes only when unit tests and real PostgreSQL integration tests
prove all lifecycle, isolation, revocation, recovery, safe-mode and negative
requirements; donor integrity remains unchanged; the Phase 5 evidence record,
anti-drift review, `INDEX.md` and progress tracker are current. File presence or
a passing happy path is insufficient.

Phase 6 may begin only after this gate passes.
