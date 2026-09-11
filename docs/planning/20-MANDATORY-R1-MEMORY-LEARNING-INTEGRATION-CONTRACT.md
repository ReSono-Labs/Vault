# Mandatory R1 Memory and Learning Integration Contract

**Status:** IMPLEMENTED; M0–M4 evidence and anti-drift exit passed  
**Authority:** `GROUNDING.md`, `INDEX.MD`, Phase 3 contract, Phase 4 contract  
**Agents:** exactly Voice Agent and Background Agent

## Decision

The entire updated R1 memory and learning system is mandatory for standalone
Vault. Existing Phase 3 work proves much of the storage contract, but the build
is not complete until the production paths use it end to end. Learning remains
a service/pipeline used by the two fixed system agents. It is not a Memory
Agent, Learning Agent, reviewer agent identity, generated agent, or plugin.

The updated R1 memory/learning implementation is authoritative for functional
behavior because it is more advanced. The Voice Vault runtime remains
authoritative for storage ownership, local identity, users, workspaces, and the
surrounding product runtime. Port R1 behavior into those boundaries without
reducing it to the older Voice implementation. A conflict is resolved as:

1. preserve the complete updated R1 memory/learning behavior;
2. preserve Voice Vault's local datastore and authorization ownership; and
3. make only the smallest compatibility adaptation needed to join them.

## Exact donor responsibilities

| Required behavior | Donor source | Vault adaptation |
|---|---|---|
| Voice transcript capture and finalize-on-close | `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/modules/device_runtime/realtime_proxy_service.py` | Keep event capture and close semantics; replace cloud authority with local user/workspace authority. |
| Structured reviewer and taxonomy enforcement | `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/agents/memory_reviewer.py` | Port the structured review capability and local credential selection; it is not registered as a system agent. |
| Citation-required, idempotent finalization | `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/memory/pipeline.py` | Retain the existing PostgreSQL adaptation in `app/vault_runtime/memory/pipeline.py` and wire it into production. |
| Domains, types, authority, confidence, sensitivity, intent | `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/memory/contracts.py` | Preserve contract v2 exactly plus private/workspace visibility. |
| Startup context and lookup | `/home/christian/Documents/Projects/ReSono-Labs-R1-Voice/runtime/resono_runtime/memory/service.py` and `memory/tools.py` | Supply bounded scoped context and the lookup tool to both system agents. |
| Voice Vault relational memory and workspace ownership | `/home/christian/Documents/Projects/ReSono-Labs-Voice/project-3d3354dadcad/workspace/app/vault_runtime/` | Remains the primary datastore and authorization architecture. |

Donors are read-only. Copy only bounded files/functions when necessary; never
edit, reorganize, or "improve" donor code in place.

## Required production chain

### Voice Agent

1. Resolve the local principal and workspace.
2. Retrieve a small authorized profile/relevance set.
3. Put the bounded memory data into the actual Realtime session instructions;
   constructing an unused `memory_items` field does not satisfy this gate.
4. Capture final user/assistant transcript events and bounded tool evidence.
5. On close, failure, loss, or UI teardown, finalize every non-empty transcript.
6. Run the R1 reviewer, validate exact citations, reconcile, version, and embed.
7. Surface a truthful finalization failure without falsely reporting learning.

### Background Agent

1. Resolve the same local user/workspace scope as the submitted run.
2. Retrieve only bounded memory relevant to the request and include it as
   untrusted context, while retaining the scoped `memory_lookup` tool.
3. Persist objective, material tool results, memory references, phase evidence,
   and completed output as bounded, attributable run evidence.
4. Do not automatically convert Background output into canonical memory unless
   an inspected donor path proves that behavior. R1 currently proves memory
   context/tools and durable run evidence, not automatic memory ingestion.
5. Never gain correction/forget authority without the existing user
   confirmation boundary.

## Required labels and lifecycle

- Domains: `identity`, `personal`, `relationship`, `environment`, `project`,
  `device`, `platform`.
- Types: `fact`, `preference`, `decision`, `episode`, `constraint`,
  `correction`.
- Source authority: `user_asserted`, `tool_verified`, `model_derived`.
- Confidence: `low`, `medium`, `high`.
- Sensitivity: `normal`, `sensitive`.
- Reconciliation intent: `create`, `confirm`, `correct`, `conflict`.
- Visibility: `private`, `workspace`.
- Preserve evidence citations, immutable versions, lifecycle status,
  idempotent fingerprints, real embeddings when available, and confirmed
  correction/forgetting.

## Build order and gates

### Slice M0 — Documentation and donor freeze

- Re-read Grounding, Index, Skills, anti-drift, borrowing matrix, donor map,
  Phase 3/4 research, and this contract.
- Record exact donor functions, tests, dependencies, hashes, and cut points for
  the R1 reviewer, Voice capture/finalize, session-start context, embeddings,
  and Background evidence flow.
- Classify every copied `agent` symbol as one of the two system agents or a
  capability-only model invocation.
- Exit only when the correction entry review records `CONTINUE`.

### Slice M1 — Structured reviewer capability

- Port the bounded R1 structured reviewer through the already admitted SDK
  runner and local workspace provider credential boundary.
- Preserve limits, secret rejection, structured output, contract version,
  candidate normalization, citations, and truthful provider failures.
- Do not register a reviewer or learning agent identity.
- Tests: exact contract output, malformed output, empty result, wrong version,
  candidate limits, secret rejection, provider absence/failure, credential
  isolation, and no third agent.

### Slice M2 — Voice context, evidence, and finalization

- Inject serialized scoped memory into the actual Realtime instructions.
- Port authenticated Voice transcript capture and finalize-on-close behavior.
- Cover normal close, provider failure, connection loss, and UI teardown when a
  non-empty transcript exists; empty transcripts do not claim learning.
- Tests: user/assistant/tool capture, replay conflict, bounded evidence,
  successful learning, idempotent retry, surfaced failure, and next-session
  retrieval under the same user/workspace only.

### Slice M3 — Background memory and durable evidence

- Supply bounded relevant authorized memory plus the existing lookup tool.
- Persist the objective, material bounded tool evidence, and final result under
  the run's user/workspace authority.
- Preserve the R1 `memoryReferences` and phase-evidence behavior. Automatic
  conversion of Background results to canonical memory is `BLOCKED/REOPEN`
  because no admitted donor implementation currently proves it.
- Tests: relevance context, private/workspace isolation, secret redaction,
  durable phase evidence, failure/cancel behavior, and no correction/forget
  bypass.

### Slice M4 — Integration proof and exit

- Run real PostgreSQL positive, negative, cross-user, cross-workspace,
  revocation, replay, and recovery tests for both system agents.
- Prove every R1 label and lifecycle transition remains available.
- Prove real embeddings only when configured and lexical fallback otherwise.
- Re-run the complete backend and frontend regressions and donor fingerprints.
- Update evidence, progress, Index, and record a fresh anti-drift exit review.

No slice may begin by assuming the previous Phase 3 or Phase 4 exit proves this
production integration. Each slice begins and ends by rereading Grounding and
Index. A missed behavior first enters this contract and Index before code.

## Traceability and acceptance

| Requirement | Slice | Required evidence |
|---|---|---|
| R1 reviewer behavior is complete and capability-only | M0–M1 | Donor cut-point inventory, unit/adversarial tests, two-agent scan |
| Voice receives and learns from scoped memory | M2 | Realtime payload proof, close-path tests, PostgreSQL next-session proof |
| Background receives scoped memory and records run evidence | M3 | R1 memory-reference/phase-evidence parity, isolation and authority proof |
| Taxonomy/lifecycle are not reduced | M1–M4 | exhaustive label validation and reconciliation/version tests |
| No cloud auth/control dependency | M1–M4 | credential-boundary tests and forbidden endpoint/source scan |
| No unapproved feature or third agent | every slice | Index comparison, exclusion scan, anti-drift review |

## Stop and rollback conditions

Stop the dependent slice if a donor path is missing, donor behavior is
ambiguous, a license decision becomes necessary for distribution, another
agent identity appears, scope reaches an excluded feature, private/workspace
isolation cannot be enforced below the UI, or tests require fabricated
semantic behavior. Revert only the bounded Vault correction slice; never touch
the donor. Preserve a failing status and evidence rather than claiming partial
integration as complete.

## Explicit exclusions

This correction does not admit external AI, social posting, recipes, local
events, weather, news, markets, document memory, shared external memory,
Hermes/OpenClaw access, remote routing, another agent, or a build agent.
