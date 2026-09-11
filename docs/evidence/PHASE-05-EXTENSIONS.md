# Phase 5 Extensions Evidence

Date: 2026-08-29  
Result: complete  
Contract: `docs/planning/16-PHASE-05-EXTENSIONS-CONTRACT.md`

## Delivered boundary

Phase 5 adds local Plugin, Agent Skill and MCP imports as capabilities available
only to the immutable Voice Agent and Background Agent identities. It adds no
agent registry, Build Agent, package agent, specialist or delegation path.

Implemented controls:

- ZIP/TAR quarantine with entry, upload, expanded-size and compression-ratio
  limits; unsafe path, special file, link, encryption, multiple-root and
  case-fold collision rejection;
- pinned Agent Plugins 1.0.0 Plugin and MCP manifests;
- public Agent Skills parsing, progressive disclosure and root-confined
  resources, with `allowed-tools` explicitly non-authoritative;
- one-use, expiring, principal/workspace/candidate/current-hash-bound preflight
  confirmation and explicit replacement;
- atomic filesystem current/previous replacement, rollback and interrupted
  operation recovery;
- PostgreSQL extension/component/grant/discovery/event/runtime-setting state;
- device-owner-only mutation, active-membership reads and exact
  user/workspace/Voice-or-Background grants;
- third-party projection disabled by default and safe mode that removes active
  MCP projections without deleting durable catalog records;
- MCP credential-free public configuration, HTTPS for non-loopback transport,
  Streamable HTTP execution only, and separate AES-GCM encrypted secret headers;
- MCP 2025-11-25 initialization, bounded paginated discovery, schema/name/result
  validation, discovery-without-grant and exact effect/audience projection into
  the canonical scoped `ToolCatalog`;
- immediate grant recheck during Skill load and MCP invocation; and
- removal of owned components, grants, tools, secrets, installed files and
  runtime projections.

## Donor provenance

The exact admitted donor paths and source SHA-256 values are frozen in
`docs/research/PHASE-05-EXTENSION-IMPORT-INVENTORY.md`. Source module comments
identify R1-derived algorithms. Voice remains the primary product/runtime donor;
R1 supplies bounded missing security/lifecycle behavior only.

Donor integrity after implementation:

| Donor | Commit | Tracked diff SHA-256 |
|---|---|---|
| Voice | `0f3b34223f745920e79d1d9db301f3b639d08393` | `0d9a4ce77e3707940c4f3becc5ecbfb641eb50f4df975c7e971f52e14e6942da` |
| R1 | `91d9e70bbe156f03c79399a458416f0bebd20210` | `90f9c55912d93683e5e3dea53688b6190c2685c6437259d418520fc6be7551ff` |

These match the admitted pre-implementation donor state. Neither donor was
cleaned, reset or modified.

## Verification

PostgreSQL 16 ran in a disposable loopback-only container at
`127.0.0.1:55435`. Command:

```text
VAULT_TEST_DATABASE_URL=postgresql://postgres:<redacted>@127.0.0.1:55435/resono_vault_test uv run pytest -q
```

Final result:

```text
151 passed in 89.05s (0:01:29)
```

The suite includes 104 unit tests plus real database/API coverage accumulated
through Phases 1–5. Phase 5 tests prove:

- hostile archive and malformed standard rejection;
- preflight expiry, wrong scope, stale hash, reuse and replacement gates;
- rollback/recovery and component collision transactionality;
- owner-only mutation and cross-workspace denial;
- default-off, safe mode, disable, revocation and removal behavior;
- metadata-only Skill listing followed by load-time scope recheck;
- encrypted credential persistence and no API/list echo;
- MCP negotiation, pagination, duplicate/cursor/schema/result rejection;
- discovery grants nothing, exact projection and invocation-time revocation;
- scoped tool names/definitions are invisible and non-invokable outside their
  user/workspace; and
- database and production-source rules allow only `voice` and `background` as
  agent audiences.

## Accepted Phase 5 limits

- Streamable HTTP is the only executable MCP transport. SSE and stdio parse as
  standard configuration but remain disabled.
- MCP transport behavior is verified with deterministic protocol transports;
  tests do not contact a third-party service.
- Plugin content is installed as untrusted data. Installing a Plugin or Skill
  does not execute bundled scripts.
- Third-party capabilities require the owner to exit safe mode and then grant
  exact capabilities. There is no automatic enablement.

These limits are contract behavior, not missing Phase 5 features.
