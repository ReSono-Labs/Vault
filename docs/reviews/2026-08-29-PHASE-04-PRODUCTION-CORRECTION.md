# Phase 4 Production Composition Correction

Date: 2026-08-29  
Decision: correction verified; Phase 4 production claim restored

## Finding

The completion audit contradicted one statement in the earlier Phase 4 exit
review: test composition proved the Background Agent with a fake executor, but
`build_local_app()` did not construct `BackgroundRunRepository`, a production
executor or the worker. The API therefore reported the Background Agent in its
fixed inventory while production submissions were unavailable.

## Correction

- copied R1 `runtime/resono_runtime/agents/sdk_runner.py` from hash
  `16db1c1ba4e87397623780a23be0c4e987d6a95a270afb12f448817993061a04`;
- added only an in-process function-tool parameter so the existing immutable
  `BackgroundToolSupply` can be used without an MCP/network bypass;
- added `OpenAIBackgroundExecutor`, using the existing encrypted workspace
  credential and owner-selected text model;
- composed and started the one fixed durable Background service in
  `build_local_app()` and stop it during server shutdown;
- pinned the R1 donor’s `openai-agents==0.18.3` dependency; and
- added production composition and executor tests.

The adapter never exposes the provider key, disables SDK tracing, validates
the final JSON against the run’s existing result schema, preserves model/tool
budgets and creates no additional identity.

## Evidence

- targeted identity/composition/executor suite: `12 passed`;
- complete PostgreSQL suite: `189 passed` in 96.07 seconds;
- frontend tests: `6 passed`; production build passed;
- Voice and R1 tracked diff fingerprints remain exactly at their frozen values.

The original exit review remains in history; this correction supersedes its
unsupported production-composition assertion.
