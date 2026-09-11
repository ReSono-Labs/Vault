# Extension Imports and Memory Architecture Review

Date: 2026-08-28  
Status: current-source research; no implementation authority  
Grounding: `GROUNDING-BASELINE-v0.6-link-amendment`, OD-08 through OD-10,
OD-25 and OD-33

## Purpose

Document secondary R1 evidence for Agent Plugins, Agent Skills, MCP, tools and
the required updated memory taxonomy/lifecycle. The existing Voice Vault runtime
and Browser Voice are primary; this review cannot replace their architecture.

## One extension path, four distinct owners

```text
archive/document upload
  -> quarantined preflight
  -> standard-specific validation
  -> explicit confirmation/replacement
  -> durable catalog + component ownership + audience
  -> enablement/discovery/grants
  -> canonical Tool Catalog or just-in-time Skill loader
  -> Voice or Background Agent projection
```

| Concern | Current owner | What it does not own |
|---|---|---|
| Plugin | `plugins/lifecycle.py` | Tool dispatch, credentials, agent execution |
| Agent Skill | `skills/specification.py`, `skills/activation.py` | Permissions or tools |
| MCP connection | `mcp/lifecycle.py` | Plugin lifecycle or credential plaintext storage |
| Tool | `tools/catalog.py` | Package installation or agent workflow instructions |
| Audience | `agents/routing.py` | Validation, permissions or execution |

## Plugin imports

JackRabbit pins the Agent Plugins 1.0.0 `plugin.json` and `mcp.json` schemas in
`runtime/resono_runtime/standards/agent_plugins/`.

Import behavior:

1. `PluginArchiveInspector` accepts ZIP/TAR data into quarantine.
2. It rejects unsafe paths, duplicate case-folded paths, links, encrypted ZIP
   entries, non-regular TAR entries, over 512 files, over 16 MiB compressed,
   over 64 MiB expanded, and per-entry ratios over 100:1.
3. The archive must have one root directory containing `plugin.json`.
4. The manifest is validated against the pinned JSON Schema.
5. Each `skills/<name>/SKILL.md`, optional `mcp.json`, and optional JackRabbit
   Card are inspected independently. Invalid components remain visible in the
   preflight result rather than being silently treated as valid.
6. `PluginLifecycle.preflight()` rejects Skill and Card ownership collisions
   and issues a short-lived token bound to identity, candidate hash, current
   hash and selected audience.
7. Confirmation stages the tree, preserves the previous version for rollback,
   atomically replaces the install directory, records the catalog/component
   ownership and audience, installs valid MCP entries, and replaces the owned
   Card.
8. Disablement removes audience exposure, disables Plugin MCP connections and
   Card visibility. Removal follows ownership and deletes those components.
9. `ImportRecovery` restores interrupted filesystem/catalog operations.

A Plugin is therefore a lifecycle and ownership container. It does not load
arbitrary Python into the trusted runtime. Shipped Plugins use the same public
lifecycle through `BundledPluginInstaller`.

## Skill imports and activation

There are two separate concepts:

- `SKILLS.MD` owner instruction documents: one slot for Voice and one for the
  Background Agent, exposed by the current Management Skills tab.
- Standard Agent Skills: `SKILL.md` packages represented in the Skill catalog
  or owned by an enabled Plugin.

The standard parser validates UTF-8 YAML frontmatter, directory/name identity,
name and description bounds, optional license/compatibility/metadata, and the
experimental `allowed-tools` string. `allowed-tools` never grants capability.

`SkillActivation` implements progressive disclosure:

1. It lists only name and description for enabled, audience-matched Skills.
2. Voice instructions tell the model which Skills exist.
3. The model calls the built-in `load_agent_skill` tool when one is relevant.
4. The runtime rechecks lifecycle and audience, parses the installed file, and
   returns the instruction body.

Standard Skills owned by Plugins are active. A complete direct standard-Skill
archive/lifecycle implementation also exists, including quarantine, rollback
and recovery, but the current public management route is wired to `SKILLS.MD`
instruction documents rather than that direct package lifecycle. Treat direct
Skill upload as an internal capability gap, not as a currently exposed product
claim.

## MCP imports and projection

Standalone and Plugin-owned MCP imports share Agent Plugins 1.0.0 `mcp.json`.
The schema recognizes Streamable HTTP, SSE and stdio, but this R1 build executes
only Streamable HTTP.

The runtime separates configuration from secrets:

- non-loopback remote URLs require HTTPS;
- embedded credentials, fragments and public auth/API-key headers are rejected;
- credential headers are added separately and sealed through the Android-owned
  credential envelope path;
- discovery uses MCP protocol revision `2025-11-25` and normalizes `tools/list`;
- duplicate/invalid names, schemas and annotations fail discovery; and
- discovery alone grants nothing.

An outbound tool reaches an agent only after all of these are true:

1. transport is supported;
2. discovery succeeded;
3. that exact tool has an explicit enabled grant and effect classification;
4. the connection is enabled; and
5. its audience includes the current agent.

`McpLifecycle` then atomically projects the connection's enabled tools into
`ToolCatalog` under a dynamic source ID. Disabling or removing the connection
removes those definitions.

## Canonical tool handling

Built-in and MCP tools converge on `ToolDefinition` and one `ToolCatalog`.
Each definition has a stable ID, unique model name, description, JSON Schema,
handler, effect class, availability rule and optional audience resource.

`ToolCatalog.invoke()` enforces:

- registered identity and current audience;
- live Voice-mode authorization when configured;
- JSON Schema argument validation;
- context-aware dispatch; and
- failure-isolated invocation evidence recording.

The same definitions are rendered into MCP `inputSchema` or OpenAI Realtime
function schemas. Providers do not own separate device tools.

Background Agent runs apply one additional immutable intersection:

- the tool must already be available to the Text audience;
- its name must be explicitly granted to the run;
- its effect must fit the selected autonomy profile; and
- the run must remain inside its tool-call budget.

Hard-approval effects include destructive, credential and package-lifecycle
operations.

## Memory ownership and flow

```text
ordered transcript + bounded redacted tool evidence
  -> one post-session Agents SDK reviewer (no tools)
  -> session summary + cited memory candidates
  -> deterministic validation and reconciliation
  -> canonical record + immutable versions + exact evidence
  -> optional provider embedding
  -> startup profile capsule and hybrid lookup tools
```

### Memory domains: what the memory concerns

| Domain | Intended content | Important exclusion |
|---|---|---|
| `identity` | Explicit stable identity | Inferred identity |
| `personal` | Durable user facts and preferences | One-time requests |
| `relationship` | Explicit people/organization relationships | Unverified inference |
| `environment` | Stable home/network/development setup | Live tool-owned status |
| `project` | Durable scope, decisions and terminology | Temporary plans/source files |
| `device` | Durable device configuration | Current battery/runtime state |
| `platform` | Owner-accepted platform decisions/constraints | Model recommendations |

Mail, Calendar and Tasks are separate canonical data domains. Their live
records must not be copied into conversational memory merely because the
reviewer saw them. Tool-verified facts may provide evidence for an appropriate
durable memory, but the domain service remains authoritative for its records.

### Memory types: what kind of memory it is

- `fact`
- `preference`
- `decision`
- `episode`
- `constraint`
- `correction`

Domain and type are intentionally independent. Canonical identity is currently
`(subject_id, domain, memory_type, memory_key)`.

### Authority, confidence, sensitivity and reconciliation

Source authority is one of `user_asserted`, `tool_verified` or
`model_derived`. Confidence is `low`, `medium` or `high`; sensitivity is
`normal` or `sensitive`.

The reviewer proposes one of four intents:

- `create`: make a new canonical record;
- `confirm`: reinforce the existing value and evidence;
- `correct`: create a new active version from explicit correction; or
- `conflict`: preserve an unresolved changed value as conflicted.

Conflicted records are not injected into startup context. Duplicate logical
records are superseded rather than silently competing.

### Evidence, versions and idempotency

- `memory_records` holds current canonical state.
- `memory_record_versions` retains content, validity, reviewer and state history.
- `memory_evidence` binds a version to a session entry, source type, source
  authority and bounded supporting excerpt.
- `memory_ingestions` binds finalization to reviewer contract version and the
  exact transcript fingerprint.
- `memory_embeddings` is a replaceable derived index, not the source of truth.
- `memory_pending_actions` requires a later user utterance before correction or
  deletion is applied.

The reviewer receives indexed transcript entries plus up to 64 existing
canonical records. Contract v2 requires cited entry indexes. Secret markers,
invalid taxonomy, missing evidence and `shouldStore=false` candidates are
discarded. Empty extraction is valid.

### Retrieval and model context

Retrieval is hybrid:

- exact key/content matching;
- bounded lexical matching; and
- real provider embeddings with model/dimension checks and cosine ranking.

Lexical/exact retrieval continues without embeddings. Startup injects up to
eight active, normal-sensitivity, medium/high-confidence memories in a fixed
domain priority plus the previous completed session summary. Deeper recall uses
the `memory_lookup` tool. Additional tools explain evidence, record explicit
remember intent, prepare correction/forget actions, and apply them only after a
later confirmation.

## Extraction findings for a multi-user/shared-memory Vault

The architecture is reusable, but current identity is single-user:

- the pipeline writes `subject_id="primary"`;
- management memory routes do not accept a user/workspace scope;
- startup context and search query the global active store;
- tool invocation context identifies agent/session, not user/workspace;
- audience bindings distinguish Voice/Text, not principals or workspace grants;
  and
- Plugin/MCP credential and ownership records are device-global.

Do not expose this database directly to Hermes or another build. Extract the
service boundaries and add local authorization before sharing memory.

The intended future shape is for Vault—not Hermes, OpenClaw, MCP, or Link—to
remain the canonical memory authority. External systems use revocable service
identities and scoped adapters. Their writes should enter as cited proposals or
tool-verified evidence and pass the same validation, reconciliation, versioning,
correction, and deletion rules as native Vault sessions.

Required merge/adaptation into the existing Voice Vault:

1. Replace `primary` with authenticated `user_id` plus `workspace_id` and an
   explicit visibility scope (`user_private`, `workspace_shared`, `system`,
   `external_shared`).
2. Bind transcripts, summaries, reviewer jobs, canonical memory, embeddings and
   pending actions to the same scope.
3. Add scope predicates to every list, search, context, evidence, delete and
   reindex operation; never filter only after fetching.
4. Extend invocation context with user, workspace and integration principal.
5. Keep Agent audience selection, but intersect it with user/workspace grants.
6. Give Hermes/MCP integrations distinct revocable identities and memory
   read/write scopes; same-machine execution is not authorization.
7. Preserve the current domain/type/evidence/reconciliation model unchanged
   unless multi-user tests prove a necessary correction.
8. Make Plugin/Skill/MCP installation owner-controlled and enablement
   user/workspace-scoped where appropriate.

## Verified limitations and follow-up tests

- Direct standard-Skill lifecycle is implemented but not exposed by the current
  Management Skill route.
- Only Streamable HTTP outbound MCP is executable.
- Plugin validation records invalid components but installs valid siblings;
  product wording must not imply all-or-nothing component success.
- Startup selection is deterministic profile recall, not query relevance.
- `platform` memory is currently ReSono-specific and should become generic
  system/product policy in an independent rebuild.
- Sensitive memories are stored but excluded from startup profile injection;
  every explicit search/sharing path still needs scope authorization.

Follow-up extraction tests should prove cross-user denial, workspace sharing,
integration revocation, Plugin ownership isolation, MCP credential isolation,
memory deletion across evidence/vectors/summaries, and safe boot with every
third-party extension disabled.

## Primary implementation evidence

- `runtime/resono_runtime/plugins/{archives,lifecycle,specification}.py`
- `runtime/resono_runtime/skills/{specification,activation,lifecycle,documents}.py`
- `runtime/resono_runtime/mcp/{imports,lifecycle,connections,client,tool_adapter}.py`
- `runtime/resono_runtime/tools/{definitions,catalog}.py`
- `runtime/resono_runtime/background_agent/tool_supply.py`
- `runtime/resono_runtime/memory/`
- `runtime/resono_runtime/agents/memory_reviewer.py`
- `runtime/resono_runtime/storage/{memory,plugin_components,mcp_connections}.py`
- `runtime/resono_runtime/storage/migrations/v042_domain_memory.py`
- `runtime/resono_runtime/api/{plugin_routes,mcp_routes,skill_routes,routes}.py`
