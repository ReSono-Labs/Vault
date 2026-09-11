# Voice Vault Import Closure v1

Date: 2026-08-29  
Method: read-only Python AST import inventory  
Donor: `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/`

The inventory script is `scripts/research/analyze_voice_vault_imports.py`. It
reads donor Python files and emits JSON to stdout; it never writes to the donor.

## Initial measured result

| Classification | Module count |
|---|---:|
| `PRESERVE` | 168 |
| `REMOVE_AGENT` | 171 |
| `DEFER_ADAPTER` | 24 |
| `LOCALIZE_CLOUD_EDGE` | 5 |

The tightened pass found 56 imports from a presumptively preserved module into
a removed, deferred, or cloud-edge module. Foundry/package handlers and
package-agent brokers are removed; the required-cloud runtime config is a cloud
edge. Counts must be regenerated at the frozen Phase 1 inventory checkpoint.

## Required cut points observed in source

| Preserved area | Coupling that must be cut or adapted |
|---|---|
| `local_api.app` | Agent-package validation/router/store/task-response imports |
| `local_api.server` | Hosted `VaultRuntimeClient`, platform provider brokers, deferred R1 tunnel |
| `local_store` | Foundry, package runtime, sandbox, package sync and package workload imports/methods |
| `session_startup` | Package-agent session startup |
| `session_tools.runtime` | A2A plus package-agent/daily-brief/delegated-task package authorities |
| `session_tools.brokers.agent_hub` and `agent_package_router` | Entire brokers removed |
| `datastore.private_data` | Hosted route-grant validation must become local session authorization |
| `session_provider_session` | Hosted runtime client dependency |
| `handlers.runtime_memory_model` | Package inference execution; must bind to retained provider/background boundary |
| `handlers.platform_learning_classifier` | Package inference execution; retain capability only through a system-agent/provider boundary |
| `autonomy.resume/workflow` | Package tracing/approval brokers; preserve background capability without a planner agent identity |

## Interpretation

These edges are not permission to redesign modules. For each cut point, copy
the donor file only in the phase that needs it, delete the prohibited branch in
the Vault copy, and replace hosted/package collaborators with the smallest
locally authoritative interface already present in Voice or the fixed R1
Background Agent. Carry donor tests and add negative tests proving the removed
agent or cloud path cannot activate.

## Gate

Phase 1 can start only after its exact subset is selected from the local API,
datastore, config and direct contract dependencies, with package-agent routes
excluded. Later session/memory/tool cut points remain in their own phases.
