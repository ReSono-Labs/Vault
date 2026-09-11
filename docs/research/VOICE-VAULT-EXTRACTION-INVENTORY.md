# Existing Voice Vault Extraction Inventory

Date: 2026-08-29  
Status: source-observed orientation; file dependency closure still required

Primary source:
`/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/`

## Preserve as existing Vault product behavior

| Capability | Voice donor area | Notes |
|---|---|---|
| Local Vault API | `app/vault_runtime/local_api/` | Preserve local contracts/authentication boundary; detach hosted grants |
| Local datastore and scope | `app/vault_runtime/datastore/`, `local_store.py`, `storage_binding.py`, `runtime_paths.py` | Preserve architecture; make paths/operation portable |
| Voice sessions | `session_broker.py`, `session_startup.py`, `session_context_builder.py`, `session_provider_*`, `session_realtime_forwarder.py`, `session_transcript_capture.py` | Becomes the one Voice system agent session path |
| Tools | `session_tools/`, `session_tool_runtime.py`, `tool_registry.py` | Preserve tools; remove adapters whose only purpose is another agent identity |
| Memory | `runtime_memory/`, memory session-tool brokers/adapters, `app/modules/runtime_memory/` | Preserve Voice scope/datastore; merge complete updated R1 taxonomy/lifecycle |
| Workspace/private data | datastore/private-data, workspace/document session-tool adapters and direct Browser Voice file flow | Preserve user/workspace authorization |
| Optional providers | email, calendar, web/search, embeddings, X and other provider adapters | Retain only as owner-configured tools/services; never as required ReSono cloud dependencies |
| Browser Voice | `frontend/src/browser-voice/` plus Browser Voice build entry/config and required shared utilities | Exact visual/interaction port; local API/auth rewiring only |

## Replace the cloud attachment, not the feature

| Cloud attachment | Observed source | Local result |
|---|---|---|
| Required platform base URL/service key | `app/vault_runtime/config.py` | Local startup cannot require `RESONO_API_BASE_URL` or ReSono service key |
| Presence, hosted workload and route-grant polling | `app/vault_runtime/client.py`, `worker.py` | Replace with local services/queues/direct calls where the existing feature needs them |
| Platform provider brokers | `platform_provider.py`, handlers using `VaultRuntimeClient` | Bind to local authority or an optional owner-selected provider |
| Hosted Browser Voice login/session bootstrap | `frontend/src/browser-voice/api.ts`, `BrowserVoiceApp.tsx`, Voice identity/realtime API modules | Preserve UI; use local Vault account/session endpoints |
| Cloud route/tunnel choice | Browser Voice route hints, relay/tunnel code | Prefer direct local path; defer Link/Tailscale/remote routes |
| Hosted registration/device/operator authority | config/client/edge connector and Voice Vault platform modules | Remove as a prerequisite; local owner is authority |

### Observed dependency-cut finding

Voice `app/vault_runtime/local_api/app.py`, `local_api/server.py` and
`local_api/stores.py` directly import Agent Foundry/package-runner code and
hosted `VaultRuntimeClient` platform brokers. Therefore these files require a
bounded extraction: preserve their request validation, local session, provider,
tool, datastore and Browser Voice behavior; remove package-agent/foundry routes
and replace platform broker construction with locally authoritative adapters.
Copying the files unchanged would violate both cloud-detachment and the
two-system-agent boundary; rewriting the entire API would violate donor-first.

## Exactly two retained system agents

| System agent | Retained behavior | Exclusions |
|---|---|---|
| Voice Agent | Voice session/context/realtime/tool runtime | No delegation to packaged agents; no extra Voice identities |
| Background Agent | R1 fixed generic `runtime/resono_runtime/background_agent/` service, run contract and tool-supply model, adapted into Voice Vault storage/tool boundaries | No specialist package, planner identity, coordinator, Build Agent or generated agent |

### Classification rule and donor cut boundary

`system agent` means a fixed runtime role required by the standalone product;
it does not mean every agent authored, bundled, privileged, or labelled
first-party by ReSono Labs. Donor code is retained as agent code only when it is
the single interactive Voice runtime or the single generic Background runtime.
A reusable capability from any other agent may be ported only as an
identity-neutral tool or service with exact provenance.

The following donor trees are excluded as agent identities:

- `app/vault_runtime/agent_packages/`
- `app/modules/agent_foundry/`
- `app/modules/agent_hub_signal/`
- `app/modules/agent_packages/`
- Voice package-agent adapters under `app/vault_runtime/session_tools/`

References from retained modules into these trees are extraction cut points,
not permission to copy them. The same rule excludes onboarding-build and
runtime-capability code when it creates, provisions, validates, publishes, or
repairs agent packages. There is no Build Agent. Repository compilation,
packaging, testing, and release remain ordinary developer/CI operations.

`first_party`, `built_in`, or `system-only` in donor code is not sufficient
evidence that an item is one of these two system agents.

## Remove from the distribution

- `app/vault_runtime/agent_packages/` package-agent execution architecture,
  except an individually proven identity-neutral helper required by a system
  agent;
- Agent Foundry build, artifact, publication, validation and dependency-
  environment workflows;
- Agent Hub coordinator and package delegation;
- first-party specialist/package agents such as research, communications,
  contacts, daily brief and social-post agent identities;
- autonomy/build planners when represented as separate agent identities;
- private/public developer agents, graph templates and marketplace/package
  catalogs that install agents; and
- every Build Agent path or UI.

The underlying feature may remain as a direct tool or service used by Voice or
Background Agent. Removing a specialist agent does not authorize removing the
email, contacts, research, daily-brief or other existing Vault capability.

## Deferred adapters

- `a2a/`, Link and Tailscale connectivity;
- `remote_management.py` and SSH remote management;
- R1 tunnel and hosted opaque relay paths where local direct routing suffices;
- Hermes/OpenClaw canonical-memory access; and
- Windows/macOS packaging after Linux.

## Required next evidence

1. Generate the import closure for each retained Voice Vault module.
2. Label every dependency `PRESERVE`, `LOCALIZE_CLOUD_EDGE`, `REMOVE_AGENT`, or
   `DEFER_ADAPTER`.
3. Map the R1 Background Agent's direct storage, delegation, tool and SDK
   dependencies into existing Voice Vault boundaries without another identity.
4. Map every R1 memory field/state/table operation to the existing Voice memory
   schema and repositories.
5. Map Browser Voice API calls to local endpoints and identify cloud-only calls
   for removal.
6. Carry the applicable donor tests and record source hashes before copying.

The first read-only AST closure and observed cut points are recorded in
`docs/evidence/VOICE-VAULT-IMPORT-CLOSURE-v1.md`.
