# Phase 4 Voice, Background Agent and Tool Inventory

Date: 2026-08-29  
Method: read-only donor source/import inspection

## Architectural result

Phase 4 is primarily a bounded extraction from Voice Vault. It retains one
fixed interactive Voice Agent session path and its provider/tool behavior. The
single generic R1 Background Agent is the only secondary agent donor. Both are
fixed runtime roles; neither is installed, selected, generated, published or
delegated to as a package identity.

The Voice `session_tools/runtime.py` file is 5,268 lines and directly imports
Agent Foundry, package-agent task routing and unrelated feature adapters. It
cannot be copied unchanged. Its identity-neutral validation, authorization,
idempotency and dispatch behaviors must be extracted into small donor-traceable
modules. Prohibited handlers and registry entries are subtraction boundaries.

## Primary Voice donor findings

Root:
`/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/`

| Donor | SHA-256 | Phase 4 use |
|---|---|---|
| `app/vault_runtime/session_capabilities.py` | `ef252d68858f75870286b77d4eae7fc22ff6701caf6d2b847d8cdc3fa19bda66` | HMAC, canonical payload, expiry and replay validation patterns; hosted account/route-grant/device fields are replaced by the authenticated local session principal |
| `app/vault_runtime/session_context_builder.py` | `949adbcafd7fc35363f60f7a8d75897497bc0a4529837bfa43b61969baf91648` | bounded Voice context assembly, adapted to Phase 3 memory/profile and local workspace |
| `app/vault_runtime/session_startup.py` | `a7a6d8bb10f9727d3a0789759639ca7165b6c36196d2bfba79ece3531f12b12f` | Voice session startup/order/error behavior only; package-agent startup and hosted broker dependencies removed |
| `app/vault_runtime/realtime_runtime_source.py` | `7f4a45ad0e1c45f1adcb3fb0a42df4e0c03dc4a873038087d40ec28968b10293` | canonical Voice instruction/tool projection; Skills/signals enter only through their later phase gates |
| `app/vault_runtime/session_provider_events.py` | `5f0a755c12e1daa96cdf631125bd7b13eb7973609809b6dad4d5376b5870d79b` | provider event idempotency and transcript-safe capture |
| `app/vault_runtime/session_transcript_capture.py` | `6b5f6987080d4db93a3a41ed5d97c38c91b2bda732bb05e976d679dfdba8a7be` | already merged into Phase 3 bounded transcript storage; provider event mapping remains |
| `app/vault_runtime/session_tools/strict_json.py` | `4ca70b52182ea782b2b994b036a9fc06ed71c24ffc4c45b32c8d47e2551e518e` | bounded JSON, duplicate-key, depth/node and non-finite rejection |
| `app/vault_runtime/session_tools/invocation_journal.py` | `4ba81b2274839ca3f49f45aa18d0ffa9c2f5803bd9664f077b596cded9a6331a` | exact-once/effect-unknown behavior, but only for admitted tools |
| `app/vault_runtime/session_tools/descriptor.py` | `5fa6dc9c0e2c873ec26413d3c66c3d4edbfe324a50f88cb42005c8d8dca4fb7e` | canonical tool descriptor/schema validation |
| `app/vault_runtime/session_tools/auth.py` | `c56fc2da5d97d325112838abc9677fd3bb117658f1fb95c829200367573baf7d` | pre-effect authorization shape, replaced with Phase 2 principal/membership and explicit local grants |
| `app/vault_runtime/session_tools/router.py` | `1d70c31601b7a62379ccb7758d53f80dbd7f35ed789ad4f8ee1db39f2ccfdd1d` | handler routing shape with agent-package and Agent Hub handlers removed |
| `app/vault_runtime/session_tools/runtime.py` | `93c6e8c1a1510461bd76a8da5fdd6ee3c6d5eebb40a855797bddd950adb190a5` | orchestration semantics only through bounded extraction; never copied whole |
| `app/vault_runtime/tool_registry.py` | `c1f898e8b53731b5a547b93cc11f211b07f7a05624aba6be3a98dd7ba193d629` | target/name/domain/effect registry behavior with prohibited identities and deferred features removed |
| `app/modules/voice_realtime/assistant_runtime.py` | `526f87ec44ffc825de9b625e8968f9984d2795edbac966fc3a7f616e4de33649` | one Voice Agent realtime request shape; hosted account overrides removed |
| `app/modules/voice_realtime/runtime_authority.py` | `8a93119cc67e87b1830f3b8b622591d72433147dcc5f63f9ddd439634d20e75a` | authority behavior replaced by local onboarding/session authority |
| `app/modules/voice_realtime/transport_service.py` | `b670317c6caef2806c6dae21f0ab305d9a40addb8bee82b3a3cf7170cae57739` | transport/session lifecycle patterns; hosted identity repository removed |
| `app/modules/inference_runtime/realtime_session_builder.py` | `badaf1ca20a4ed2abd32c41cf38b11e9c403cb8ff76e76fd5ba81b8f727459b4` | provider-neutral realtime session request construction; cloud runtime source removed |
| `app/providers/ai/models.py` | `11bf75c0bd80be63d42f903d008a0ad9e51a85f3b9165b5e74d6dcb92f4fb897` | provider-neutral realtime request/result contracts |
| `app/providers/ai/openai_realtime.py` | `34576e9f04f5d7fa5d3a28295e4d47cde50ed1ba56e9003cee7184450ee3cd9b` | owner-key WebRTC client-secret transport; subscription/backend routes excluded |
| `app/contracts/internal/openai_realtime_session.py` | `ccb21727b74aab651039451f39122c95b9bd90a1da9626e314b16ad4092657dc` | OpenAI Realtime session/audio/function-tool payload shapes |

Provider access may use an owner-configured provider key/base URL. It must not
require a ReSono-issued account, subscription, service key, ephemeral token or
hosted selection/control-plane call. Provider absence must leave Vault
management, identity, workspaces and memory operational; it may make live model
inference unavailable with a clear local status.

## Required Background Agent donor findings

Root: `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/`

| Donor | SHA-256 | Phase 4 use |
|---|---|---|
| `runtime/resono_runtime/background_agent/run_contract.py` | `ebd167b78ea3c6e4a40a74265c7b7f927af35fd7fc34638d3f89ca0e66f08b7a` | run state, limits, recipes and fixed generic request contract |
| `runtime/resono_runtime/background_agent/run_state.py` | `9689e18d107cac4db432f3ab8b64c635f51673bef98450c2486d03e3c7b904a1` | durable lifecycle transitions |
| `runtime/resono_runtime/background_agent/rules.py` | `257d8232ee9ac25eee505fa6cf95127de4938f5b75f32a1a9bef0b4f514ddc63` | anti-drift/rules loading from the project workspace |
| `runtime/resono_runtime/background_agent/instructions.py` | `42d29324e3051086412c9ecb9b013283adcb984dba7a97ae7dd02bc5a5027edf` | bounded worker instruction composition; remove R1 device identity |
| `runtime/resono_runtime/background_agent/output_contract.py` | `44b77365356ab0f0ba7ff70aa648511f06a18aed17926ac2334a5f042054ff8b` | strict final output contract |
| `runtime/resono_runtime/background_agent/progress.py` | `b834b564444804fa211b2cddfb5bf58aad3655c15101ce33799cb464b3639b4c` | tool-budget and progress accounting |
| `runtime/resono_runtime/background_agent/tool_supply.py` | `2a765fa541b0dca6d1c46cc512ccc54cec126610510128979831d286889431ab` | immutable per-run intersection of catalog, grants and limits |
| `runtime/resono_runtime/background_agent/service.py` | `8fb1280b6ebce517bc4c785035908d2b777b2445d17a21d80c9c085123211e6e` | one fixed queue/service lifecycle, adapted away from delegation-agent identities |
| `runtime/resono_runtime/background_agent/execution.py` | `993fd77928d80eb7d0ad255a4f4a42817993f44fa59a821bb527850bd9a2edc7` | executor boundary and durable result transitions |
| `runtime/resono_runtime/agents/sdk_runner.py` | `16db1c1ba4e87397623780a23be0c4e987d6a95a270afb12f448817993061a04` | canonical single-agent OpenAI Agents SDK runner; locally adapted to accept the already-bounded in-process function-tool supply |
| `runtime/resono_runtime/storage/agent_runs.py` | `2173c1e822ad1ff01236e01fa39fcd6385fecc00cc7ec071f3d36a04e55379e1` | translate SQLite run persistence to locally scoped PostgreSQL |
| `runtime/resono_runtime/storage/background_agent_settings.py` | `0ee5fe77f90cf5db163b20e587123dbe560af2706ef904223e178352ff05eaad` | per-user/workspace settings and allowed-tool policy |

R1 `agents/delegation.py`, `GoalTask`, `PrimaryAgentContext`, MCP gateway and
Agents SDK composition are dependencies to inspect, not automatic permissions.
The user may submit work to the one Background Agent, and the Voice Agent may
request that fixed service where grounded; neither path creates a delegated or
specialist identity. The Background Agent executor is provider-neutral and
receives only the authorized run context and immutable tool subset.

## Tool admission boundary

Phase 4 requires the canonical built-in tool mechanism and the memory tools
already proved in Phase 3. Feature-specific tools are admitted only when their
underlying feature is already grounded and its donor dependency closure is
ported. Plugin, Skill and MCP import/lifecycle belongs to Phase 5. A Phase 5
extension may add definitions to the same catalog but cannot create an agent.

Prohibited registry targets and handlers include all of:

- `agent_packages.*`, `agent_tasks.*`, `agent_foundry.*`, `agent_hub.*`;
- `delegate_task`, package selection/handoff/resume/cancel;
- agent building, revision, clarification, validation or publication;
- any target that installs, selects or invokes another agent identity.

`a2a.*`, Link and remote-routing targets are deferred. Ordinary memory,
workspace, provider and public-read capabilities remain tools/services, not
specialist agents, but each feature still needs its admitted phase slice.

## Fixed inventory result

The runtime identity inventory must be data, not inferred from installed
packages:

```text
voice
background
```

## Production-composition correction

The Phase 6 completion audit found that the original Phase 4 composition had
proved Background lifecycle behavior only with test executors and did not
construct the production executor. The target now carries the R1 SDK runner
and a bounded local adapter in
`app/vault_runtime/background_agent/openai_executor.py`. It reuses the owner’s
encrypted workspace OpenAI credential, requires a separately selected text
model, exposes only the immutable `BackgroundToolSupply`, disables tracing and
returns an object validated against the submitted result schema. This is the
same fixed Background Agent; no agent registry or delegation path was added.

There is no registry mutation API for agent identities. Plugins, Skills, MCP
servers and tools can change capability supply only.
