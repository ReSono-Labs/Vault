# Project Borrowing Matrix

Status: controlling donor authority

## ReSono-Labs-Voice — primary product donor

Borrow the existing Vault product, not merely its ideas.

| Borrow | Exact source | Exclude/adapt |
|---|---|---|
| Complete Vault runtime behavior and module boundaries | `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/vault_runtime/` | Remove mandatory hosted API polling, ReSono registration/presence, hosted route grants, ReSono cloud auth and operator authority; retain optional owner-selected providers |
| Exact Browser Voice UI, interactions and tests | `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/frontend/src/browser-voice/` | Replace cloud login/session/API calls with local Vault endpoints; remove billing/operator/cloud-only controls without redesigning visuals |
| Browser Voice build entry | `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/frontend/browser-voice.html`; `vite.browser-voice.config.ts`; `tsconfig.browser-voice.json` | Bind local management safely; preserve build structure |
| Existing account/session/workspace contracts | `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/modules/identity_access/`; `app/api/dependencies/auth.py`; account/workspace models | Move authentication/session authority local; no ReSono-issued identity or hosted callback |
| Existing memory and scope behavior | `app/vault_runtime/runtime_memory/`; `app/vault_runtime/session_context_builder.py`; `app/vault_runtime/session_transcript_capture.py`; `app/modules/runtime_memory/` | Preserve account/workspace scope and canonical behavior; replace hosted coordination only |
| Voice system agent, tools and provider behavior | `app/vault_runtime/session_*`; `app/vault_runtime/session_tools/`; `app/vault_runtime/tool_registry.py`; Voice realtime modules | Retain one fixed Voice Agent; remove package-agent routing and cloud authority |
| Direct public Web search tool | `app/contracts/internal/browser_voice_tools.py::web_search_tool_definition`; `app/vault_runtime/web_search_provider.py`; `app/vault_runtime/signals/openai_search.py`; `app/vault_runtime/session_tools/brokers/web.py`; `app/vault_runtime/session_provider_request.py` | Port only the proven `web_search` → `web.search` registered-adapter path; resolve local shared/individual provider credentials; require public URL citations; no External AI product or unrelated signals |
| Background system-agent behavior | `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/background_agent/`; supporting `agents/delegation.py`, `storage/agent_runs.py`, `storage/background_agent_settings.py`; applicable tests | Port the single fixed generic Background Agent service/run/tool-supply behavior into Voice Vault boundaries; no specialist/package identities and no Build Agent |
| Existing Vault local API/datastore/storage | `app/vault_runtime/local_api/`; `app/vault_runtime/datastore/`; `app/vault_runtime/local_store.py`; `app/vault_runtime/runtime_paths.py` | Adapt paths and startup for Linux/Windows/macOS; do not invent a second datastore architecture |
| Built-in Mail client | `app/vault_runtime/email_provider.py`; `email_service.py`; `email_store.py`; `session_tools/email_adapters.py`; `signals/email/session_tools.py` | Preserve multi-account client behavior; detach cloud authority and keep credentials local |
| Built-in Contacts and Calendar | `app/vault_runtime/session_tools/contacts_adapters.py`; `session_tools/brokers/contacts.py`; `calendar_provider.py`; `calendar_sync.py`; `session_tools/calendar_adapters.py` | Port only modular local service/tool behavior under workspace authority |

## ReSono-Labs-R1-Voice — secondary local/privacy donor

R1 is secondary to the Voice Vault architecture. Its updated memory system is
a specifically required merge; other R1 behavior is used only for a proven gap.
For memory and learning functionality, updated R1 is authoritative and may not
be narrowed to older Voice behavior. Voice remains authoritative for Vault's
PostgreSQL ownership and local user/workspace authorization boundary.

| Borrow | Exact source | Boundary |
|---|---|---|
| **Required updated R1 memory system**: domains `identity`, `personal`, `relationship`, `environment`, `project`, `device`, `platform`; types `fact`, `preference`, `decision`, `episode`, `constraint`, `correction`; authority `user_asserted`, `tool_verified`, `model_derived`; confidence; sensitivity; create/confirm/correct/conflict reconciliation; evidence, versions, idempotency, embeddings, pending actions and hybrid retrieval | `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/memory/`; `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/agents/memory_reviewer.py`; `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/storage/memory.py`; `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/storage/migrations/v042_domain_memory.py`; R1 memory tests | Merge all behavior/labels into Voice Vault memory boundaries; preserve Voice account/workspace scoping and datastore architecture; do not collapse or rename taxonomy |
| R1 Voice finalize and startup-memory behavior | `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/api/routes.py`; `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/application.py`; `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/tests/runtime/test_runtime_http_finalize.py`; `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/tests/runtime/test_memory_sessions.py` | Port complete execution semantics into the Voice Vault/local API boundary; do not copy R1 single-user storage assumptions |
| Agent Plugin archive/lifecycle hardening | `runtime/resono_runtime/plugins/`; `runtime/resono_runtime/imports/`; `runtime/resono_runtime/storage/plugin_components.py` | Use only if Voice package/signal lifecycle lacks equivalent validation/recovery |
| Agent Skill standard parsing/progressive disclosure | `runtime/resono_runtime/skills/` | Use as a bounded standards adapter, not a replacement agent system |
| MCP config, secret separation, discovery and tool grants | `runtime/resono_runtime/mcp/`; `runtime/resono_runtime/tools/` | Merge only missing local security behavior into Voice tool/integration boundaries |
| Cross-platform installer patterns | `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/installer/` | Reuse launcher/release patterns; do not copy R1 flashing/images/device logic |

## ReSono-Labs-Link — later optional connectivity donor

Borrow only the Link client/connector/runtime pieces needed to reach a Vault
that otherwise lacks a routing plane. Do not borrow Link's hosted customer,
operator, billing, or control-plane product into local Vault. Exact file subsets
remain blocked until the connectivity phase.

Source: `/home/christian/Documents/Projects/ReSono-Labs-Link/`.

## Tailscale — later optional transport

Tailscale is a routing/transport choice used with Link where explicitly enabled.
It does not own Vault identity, authorization, memory, management or product
logic. No core release dependency is authorized.

## Hermes and OpenClaw — future integration clients

Hermes and OpenClaw are not core donor architectures. They are future optional
clients of Vault's canonical memory/service boundary. They receive distinct,
revocable integration identities and cannot access the datastore directly.

## New Vault-only work

New work is limited to the glue that existing donors do not contain:

- detaching Voice Vault from ReSono-hosted authentication/control authority;
- making existing account/session behavior locally authoritative;
- packaging the existing Vault runtime and Browser Voice together;
- portable OS path/service/secret-store adapters where donors lack them; and
- later, permissioned shared-memory adapters for external agents.

Anything else requires a material-decision record before entering the index.

External AI, social posting, recipes, local events, markets, workouts, weather,
news and every other unadmitted signal/tool family are explicitly not borrowed
for the standalone core. Recipes/local events may only return through a later
Plugin phase explicitly approved by the owner.

## Explicitly not borrowed

Do not copy Voice `app/vault_runtime/agent_packages/` wholesale. Exclude Agent
Foundry, Agent Hub, package runners, specialist/first-party package agents,
generated/private/public agents, graph templates, agent publication, build
lifecycles and package-agent delegation. There is no Build Agent. A helper from
those paths may be copied only if inspection proves it is identity-neutral and
required by one of the two fixed system agents.
