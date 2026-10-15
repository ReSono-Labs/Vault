# C04H internal evidence

Branch `feature/live-memory-decisions`. Reuse reviewed in the C04H contract;
no new schema, transcript store, model or scheduler. Runtime calls the existing
scoped sealing transaction after releasing the finished turn's slot, queues
configured consumers durably and starts the same review worker when available.
No active response can be sealed; history_version changes only for submissions.

Mounted isolated-Postgres proof (synthetic text runner; no paid calls):
`test_chat_segment_size_postgres.py` plus existing
`test_chat_session_context_postgres.py`: **2 passed in23.36s** before expanding
the first test with turn-count and active-response counterexamples. The original
49000-byte input survives untouched, first segment seals, next actual provider
request contains only the new turn, same conversation/version continues, and
below-threshold rotation returns no-op. Existing completed-summary source
qualification and >275k retained-history continuation remain passing.

Final expanded mounted checks: **2 passed in14.05s**. Parameterized actual
runtime verifies byte threshold and turn-count threshold independently, restores
normal limits for continuation, and verifies a submitted active response blocks
size-triggered sealing. The turn-count branch uses a test-local lower constant
to avoid32 redundant provider/worker cycles; production default remains32.
`git diff --check` and Python compilation pass. No installed database accessed.

This is bounded turn-boundary accumulation handling. A single input/tool/result
can still exceed procedural source limits; arbitrary-length source windows,
Voice qualification/recovery, display pagination and other register gaps are
not closed. Internal self-review, not owner/provider/release acceptance.
