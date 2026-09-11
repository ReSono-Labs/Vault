# Phase 4C M3 Background Memory and Evidence

Date: 2026-08-29  
Status: PASS for exact R1 parity

## Implemented donor behavior

- The production Background executor retrieves at most eight authorized
  relevant memories under the run's local user/workspace scope.
- Memory is supplied as untrusted JSON context and the canonical scoped
  `memory_lookup` tool remains available through normal grants.
- `context_frozen` persists exact `memoryReferences` before model execution.
- The direct R1 `BackgroundAgentOutput` contract replaces loose arbitrary model
  JSON and bounds summary, artifacts, outcomes, unresolved issues, verification,
  and phase evidence.
- Every returned phase-evidence item becomes a durable `agent_evidence` event.
- `blocked` and `needs_attention` outputs fail truthfully as
  `agent_incomplete`; only checked `complete` output completes a run.
- Cancellation, model/tool budgets, workspace authority, output validation,
  and recovery remain in the one fixed Background Agent service.

## Donor boundary

Direct behavior comes from R1:

- `runtime/resono_runtime/background_agent/output_contract.py`;
- `background_agent/execution.py`;
- `background_agent/composition.py`;
- `background_agent/instructions.py`; and
- the already admitted memory context/tool paths.

No automatic Background-to-canonical-memory writeback was added because R1
does not implement it. Background durable evidence is not silently promoted to
memory authority.

## Verification

Real PostgreSQL targeted result:

```text
10 passed in 15.64s
```

The tests cover strict typed output, memory-reference freezing, scoped memory
content, durable phase evidence, legal lifecycle, cancellation, invalid output,
cross-user probing, revocation, worker execution, and tool/model bounds.

The disposable PostgreSQL container was removed after verification.
