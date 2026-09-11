# Phase 10 Agent Plugins and External Memory Inventory

Date: 2026-08-31  
Status: evidence freeze; implementation authority comes only from the Phase 10
build contract  
Grounding: `GROUNDING.md`, `SKILLS.MD`, `INDEX.MD`

## Owner outcome

Vault follows Agent Plugins 1.0.0 and supports useful portable Plugins. Hermes
and OpenClaw can optionally use Vault as canonical memory through separately
installed adapters. This does not add an agent, replace Vault memory, expose
the database, or authorize general remote access.

## Standards evidence

Agent Plugins 1.0.0 defines only two portable component types:

- Agent Skills at `skills/<name>/SKILL.md`; and
- MCP servers in root `mcp.json`.

It permits clients to support only a subset of component types/transports. It
also requires unknown manifest fields to be reported and ignored, empty
`mcpServers` to remain valid, and independent component failures not to disable
otherwise valid components. Client-specific behavior belongs under a
reverse-domain namespace in `plugin.json.extensions` and a matching root
directory.

Authoritative sources:

- `https://agent-plugins.org/specification`
- `https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`
- `https://agent-plugins.org/schemas/1.0.0/mcp.schema.json`

The standard does not define memory-provider lifecycle hooks, inbound service
authentication, pairing, or canonical memory semantics.

## Current Vault facts

Vault already validates the pinned 1.0.0 manifests, installs Skills and MCP
components, executes Streamable HTTP MCP, separates secrets, and applies exact
user/workspace/system-agent grants. Phase 5 evidence remains valid for that
implemented boundary.

Verified gaps:

1. unknown `plugin.json` top-level fields currently fail schema validation
   instead of being diagnosed and ignored;
2. an empty `mcpServers` object is rejected; and
3. one invalid Skill or MCP document rejects the whole Plugin rather than
   preserving independently valid components.

Vault currently ignores client extension namespaces. That is conforming Agent
Plugins behavior and is not a Phase 10 gap. No Vault-specific extension
namespace is needed for the admitted memory integration.

These are conformance gaps. They do not authorize
arbitrary in-process Plugin code. Streamable HTTP remains the only executable
MCP transport in this phase; Agent Plugins permits that incremental support.

## Hermes donor freeze

Local read-only checkout:
`/home/christian/.hermes/hermes-agent`

Commit: `41447a6d7063b2772b0c2f26a5b22d9bd444fb43`  
License: MIT, local `LICENSE` SHA-256
`821556e6336796450ab852d375117b48a4887e71d255794fd6318d99982a5ab6`

| Exact path | SHA-256 | Evidence |
|---|---|---|
| `/home/christian/.hermes/hermes-agent/agent/memory_provider.py` | `a6468b09388c5a8626f3cfbd34473db3d1551e0695394e6e2d069756e1dd9cd2` | Native external-memory lifecycle contract |
| `/home/christian/.hermes/hermes-agent/agent/memory_manager.py` | `cb3769674fb7ca0215f6babb7980dda6010b48c5db18f5183ac9616339468b0c` | Prefetch and serialized turn synchronization |
| `/home/christian/.hermes/hermes-agent/plugins/memory/__init__.py` | `8a52882f0a2569f241d0a9078478b82b936b3ca465915a8971f57f058ef343ac` | Provider discovery and package entry point |
| `/home/christian/.hermes/hermes-agent/hermes_cli/agent_plugins.py` | `fa412146545167486fa6688ed582c6aca28406f5c6f071db8074bdbda5e4877d` | Agent Plugins 1.0 compatibility behavior |

Hermes can use a standalone `MemoryProvider` without a Hermes core patch. Its
built-in `MEMORY.md` and `USER.md` remain active. The adapter may translate
prefetch and completed-turn hooks, but Vault remains the classifier and
canonical authority.

## OpenClaw evidence and blocker

Official current documentation proves Agent Plugins bundle support and a
native exclusive memory Plugin slot. The exact build donor is not frozen:
there is no local OpenClaw checkout in the inspected project locations, and no
owner-selected release has been recorded.

Authoritative orientation:

- `https://docs.openclaw.ai/plugins/bundles`
- `https://docs.openclaw.ai/plugins/manifest`
- `https://docs.openclaw.ai/concepts/memory`

`BLOCKED/REOPEN`: no OpenClaw adapter implementation may begin until a stable
release is selected, inspected at exact local paths, hashed, license-reviewed,
and its memory-slot compatibility tests are identified. Planning may retain an
OpenClaw adapter slice, but cannot claim it build-ready.

## Required Vault boundary

The smallest new Vault boundary is a loopback-only external-memory service
using distinct revocable integration identities. It exposes only:

- scoped search/get;
- attributable memory proposal intake;
- correction request;
- forget request; and
- health/revocation behavior.

Vault derives user and workspace from the integration identity. External
clients cannot choose arbitrary principals, write canonical rows, access
PostgreSQL, or bypass reconciliation and confirmation.

## Explicit exclusions

- cross-device routing, Link, Tailscale, LAN discovery, or remote management;
- Vault credential/keystore brokering;
- Mail, Contacts, Calendar, files, or general Vault API exposure;
- stdio or SSE MCP execution;
- arbitrary Plugin Python/JavaScript import;
- client-specific extension namespace, event bus, webhooks, marketplace,
  update registry, signing system, or Plugin UI framework;
- new agent identities or Background automatic memory writeback; and
- changes to Hermes or OpenClaw core.

## Material decision gate

Question: what is the smallest Phase 10 that satisfies the owner outcome?

- Authority: owner request; Grounding canonical shared-memory role; Agent
  Plugins 1.0.0; current Vault/Hermes/OpenClaw evidence.
- Alternatives: expose broad Vault APIs; add a general executable Plugin SDK;
  direct database access; portable Skills/MCP plus one scoped memory service
  and native adapters; remain deferred.
- Decision: correct portable-standard behavior, add the one scoped local memory
  service required by adapters, prove Hermes, then prove OpenClaw only after
  its donor gate.
- Counterexample: a Plugin can read another user's memory, write canonical rows
  directly, create another agent, or requires a transport/framework unrelated
  to the admitted memory scenario.
- Dependents: extension parsing/lifecycle, local API, integration identity,
  memory proposal/retrieval service, adapter packages, tests and evidence.
- State: `CONTINUE` for Vault conformance/service and Hermes;
  `BLOCKED/REOPEN` for OpenClaw implementation pending exact donor freeze.
