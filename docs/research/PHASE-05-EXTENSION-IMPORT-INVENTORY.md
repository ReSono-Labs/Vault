# Phase 5 Extension Import Inventory

Date: 2026-08-29  
Status: donor and standards freeze; implementation authority comes from the
Phase 5 contract  
Grounding: `GROUNDING.md`, `SKILLS.MD`, `INDEX.MD`

## Required result

Vault imports Plugins, Agent Skills and MCP configurations locally without
creating an agent identity or relying on ReSono Labs. Every imported item is a
capability available only after owner-controlled validation and explicit
user/workspace/system-agent grants. The only execution identities remain Voice
Agent and Background Agent.

## System-agent classification

| Imported concept | Classification | Rule |
|---|---|---|
| Plugin | `CAPABILITY_ONLY` | Ownership/lifecycle container; never executable agent identity |
| Agent Skill | `CAPABILITY_ONLY` | Progressively loaded instructions/resources; never a permission grant |
| MCP server | `CAPABILITY_ONLY` | External tool source; discovery grants nothing |
| MCP tool | `CAPABILITY_ONLY` | Projected into canonical `ToolCatalog` only after an explicit grant |
| Package/specialist/generated/build agent | `REMOVE_AGENT` | Never imported, registered, selected or delegated to |

An archive field such as `system`, `built_in`, `first_party`, `agent`, or
`assistant` cannot change this classification.

## Primary Voice donor

Primary donor root:
`/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace`

| Donor path | Borrowed behavior | Excluded behavior |
|---|---|---|
| `app/modules/skill_catalog/` | Product-facing Skill catalog, storage manifest and management concepts | Cloud/global authority and unscoped storage |
| `app/modules/skill_runtime/` | Skill activation/runtime concepts | Any additional agent identity |
| `app/modules/mcp_runtime/registry.py` | MCP registry and tool-discovery concepts | Cloud service authority |
| `app/modules/mcp_runtime/schemas.py` | Import/request shapes where compatible | Hosted authentication fields |
| `app/modules/mcp_runtime/service.py` | Connection lifecycle concepts | ReSono routing/control plane |
| `app/modules/runtime_tools/skill_executor.py` | Skill execution boundary concepts | Package-agent execution |
| `app/vault_runtime/tool_registry.py` | Existing Voice canonical tool ownership concept | Package-agent routing |

Voice `app/vault_runtime/agent_packages/` and donor Foundry/developer publishing
paths are removal evidence, not port candidates. MCP helpers below those paths
are not admitted merely because they mention MCP.

## Secondary R1 donor: admitted bounded files

Secondary donor root:
`/home/christian/Documents/Projects/ReSono-Labs-R1-Voice`

| Donor path | SHA-256 | Exact admitted behavior |
|---|---|---|
| `runtime/resono_runtime/plugins/archives.py` | `941087b1d8821add8fba72d03ba0afd2ba6fe69680f35ecbe59b635706cbc0b9` | ZIP/TAR quarantine, path/link/encryption/count/size/ratio defenses |
| `runtime/resono_runtime/plugins/lifecycle.py` | `c2de2ab624104b6e0f8bdd65b0a8b59b4d15659a3ea4370f0f3a91c589bd1979` | Hash-bound preflight, atomic replacement, rollback and recovery concepts |
| `runtime/resono_runtime/plugins/specification.py` | `acf5a1436ee58095794319554e6c5167abffc6890da8abad1d233fab73c78b27` | Pinned Plugin and MCP manifest validation |
| `runtime/resono_runtime/skills/specification.py` | `17600c8dc2b333aeaea86a54460f0b2fba1691ab3a1b809858f9db2e8da65b29` | Standard `SKILL.md` parser and field limits |
| `runtime/resono_runtime/skills/activation.py` | `4c0c3d4b304c72e57170b59aaa6c05c2929c19a07c95678e2acc41e34186f0c5` | Metadata-first progressive disclosure and load-time recheck |
| `runtime/resono_runtime/skills/lifecycle.py` | `bd897cdfeb389ef90f2f64d3b34a0d7b1a6765a2b6916e3ded3aed935af4a44e` | Direct Skill install/replace/disable/remove/rollback concepts |
| `runtime/resono_runtime/mcp/imports.py` | `4d52e75c1891ef80ac4bf2219f3cad0c1f12d67f2edc887fe10a7ed55f8bcd9d` | Exact-state overwrite confirmation |
| `runtime/resono_runtime/mcp/connections.py` | `bba62da0f6f5855cba465c50d218d20eab4b36d368d9c0125f9952013f8b3297` | Transport/URL/header/credential configuration validation |
| `runtime/resono_runtime/mcp/client.py` | `45d4537fd056866e315cc771b275e72af505d0a464b782c9f3349f3860049716` | MCP initialize, paginated discovery and calls |
| `runtime/resono_runtime/mcp/lifecycle.py` | `e1a1a15f77d0fc6ac322da8745ece468d8331a569a4ab433ac0507348802a102` | Discovery, explicit grants and atomic catalog projection |
| `runtime/resono_runtime/mcp/tool_adapter.py` | `29001ff206410e72550481f03c0c704cd44dcafa7d56f469c2a8ec21c602ba10` | MCP definition/result normalization |
| `runtime/resono_runtime/storage/plugin_components.py` | `d5ef0a3fb3d4a30dcde0ec08952cff75f9ce9e1b24c8c06ec9c68b58f5e1fb92` | Component ownership/collision evidence |
| `runtime/resono_runtime/storage/mcp_connections.py` | `8343c705396e5d6e85b8ea4f136fa372555a17dab5eacc0c4e35686eeab76da9` | Durable lifecycle/history concepts |
| `runtime/resono_runtime/standards/agent_plugins/plugin.schema.json` | `0a4aad95ce337878ad38802ebf0daa3fde76abe3f65400c86bcbb1ec0b3ab883` | Pinned Agent Plugins 1.0.0 Plugin schema |
| `runtime/resono_runtime/standards/agent_plugins/mcp.schema.json` | `6539175bfcdf43085855183e86da40ea94b166547a72b47ae9a0a390516d3acb` | Pinned Agent Plugins 1.0.0 MCP schema |

R1 APIs, Android credential envelopes, global audiences and bundled agent
packages are not admitted. Vault adapts these controls at its existing local
identity, workspace, filesystem and `ToolCatalog` boundaries.

## Public standards checked

### Agent Skills

The [Agent Skills specification](https://agentskills.io/specification) requires
a `SKILL.md` with YAML frontmatter, a 1–64 character lowercase/hyphenated name
matching its directory, a 1–1024 character description, and optional license,
compatibility, string metadata and experimental `allowed-tools`. It describes
metadata-first progressive disclosure and optional `scripts/`, `references/`
and `assets/` directories.

Vault adopts the format and progressive disclosure. It adds quarantine,
ownership, local scope and safe-mode controls. `allowed-tools` is parsed for
compatibility but never grants a tool. Scripts are untrusted files and are not
executed merely because a Skill was loaded.

### MCP

The [MCP 2025-11-25 tools specification](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
defines `tools/list`, `tools/call`, valid JSON Schema input, list-change
notifications and client-side confirmation/auditing expectations. It requires
servers to validate inputs, enforce access controls, rate limit and sanitize
outputs, while clients should validate results and use timeouts.

The [MCP security guidance](https://modelcontextprotocol.io/docs/2025-11-25/tutorials/security/security_best_practices)
also identifies confused-deputy, token-passthrough, SSRF, session-hijacking and
local-server compromise risks. Vault therefore separates credentials from
manifests, rejects embedded credential headers, restricts insecure HTTP to
loopback, validates tool schemas/results, uses bounded timeouts, records calls,
and treats annotations and discovered tools as untrusted.

## Frozen cut boundary

Phase 5 copies only phase-required, identity-neutral logic. It may preserve
donor algorithms while renaming imports and adding Vault scope. It must not
copy an entire donor tree, mutate either donor, introduce donor cloud auth, or
port any agent package. Every copied/adapted module records its donor path in a
module comment and in Phase 5 evidence.

Safe mode means third-party Plugins, Skills and MCP connections are unavailable
without deleting their durable records. Built-in canonical Vault tools and the
two fixed system agents remain available.
