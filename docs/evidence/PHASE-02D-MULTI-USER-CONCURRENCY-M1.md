# Phase 2D M1 Multi-User Concurrency Evidence

Date: 2026-08-29  
Status: M1 and M2 passed; broker/load closure remains open

A real PostgreSQL test started four users in parallel. Each independently
logged in, resolved a distinct active session/workspace, appended a private
transcript and reconciled a private R1 memory record. All four retained valid
sessions. Each read its own memory; all twelve cross-user memory probes failed.

Command:

`VAULT_TEST_DATABASE_URL=... uv run --frozen pytest tests/integration/test_memory_postgres.py::test_four_users_hold_sessions_and_write_private_memory_concurrently -q`

Result: `1 passed in 4.19s`.

M2 adapted the Voice Bubblewrap enforcement primitives into
`app/vault_runtime/sandbox/` without Agent Packages. Linux tests prove hidden
host paths, cleared environment, network namespace denial, private writable
run roots, timeout containment and continued healthy execution. Background
Agent service now has four concurrent workers; a real PostgreSQL test releases
four users through one barrier, deliberately fails one run, completes the other
three and confirms account sessions remain valid.

Commands and results:

- `.venv/bin/pytest -q tests/unit/test_sandbox.py` — `3 passed`;
- `python3 scripts/test_env.py test -q tests/integration/test_background_agent_postgres.py`
  — `7 passed`.
- `python3 scripts/test_env.py test-all -q` — `203 passed` backend,
  `6 passed` frontend, production Browser Voice build passed.

This does not yet prove broker integration for an executable imported
capability, concurrent Voice transport, or Mail/Calendar load. Those remain
open and must not be represented as complete.
