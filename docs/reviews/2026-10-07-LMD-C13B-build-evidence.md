# C13B/r1 — canonical retrieval-state evidence

2026-10-07; feature/live-memory-decisions, uncommitted. Bounded internal
verification, not full live-context integration or owner release acceptance.
Contract and source frozen before runtime edits; original grounding unchanged.

## Implemented delta

Canonical records gain an appended positive retrieval_epoch. Owned invoker
triggers increment it on actual returned-field changes (including recency),
preserve it on no-ops and prevent explicit resets. Existing MemoryRecord fields,
version offsets, reconciliation, evidence and vector authority remain unchanged.
Scoped shared/private counters advance transactionally for additions, updates,
deletions and scope/visibility moves. Identity-only seeding preserves existing
counters; account tombstone cleanup removes private counters after records.
Workspace cascade cannot recreate removed parents.

New immutable state DTOs wrap existing records. retrieval_snapshot reuses
membership/shared authority locks and canonical scope predicate; one SQL
statement reads counters and requested active records in a coherent snapshot.
Maximum 25 distinct IDs; invalid batches fail before connection and generators
consume at most 26 entries. No vectors, model calls, writes or corpus scans on
this read path. Fingerprint contains scope/counters, not content or another
user's private activity. No new current-session predicate or production mount.

## Targeted actual tests

- python3 scripts/test_env.py test -q tests/unit/test_memory_retrieval_state.py
  tests/integration/test_memory_retrieval_state_postgres.py
  tests/integration/test_vector_write_postgres.py
  tests/integration/test_memory_postgres.py: 41 passed, 53.81s.
- Added logical account-erasure proof: 1 passed, 2.60s.
- Added recency/content ABA/workspace-move proof: 1 passed, 2.63s.
- Final state units, including bounded generator/string rejection: 18 passed,
  0.07s. Total distinct coverage: 18 units and 28 real PostgreSQL tests (7 new
  state tests plus 21 existing memory/vector-write regressions). No skips/failures.
- Additive legacy-record migration preserves record identity/version/fields,
  evidence rows and real synthetic vector/fingerprint. Repeated ensure_schema
  preserves live epochs. Same-version confirmation metadata changes invalidate;
  no-op reset does not. Empty/add/delete, privacy isolation, shared visibility
  transition, rollback, concurrent increments, revocation and erasure pass.
- Test-only database/user/loopback port, image
  sha256:9b05db12a35460fff0587e009f9326e414a53e9484555547f96d214a2ba98ef7
  and resono-vault-test-postgres-data mount verified. Harness stopped, volume
  retained. No installed DB, paid providers, donor changes or dependency upgrade.
- git diff --check clean. No repeated broad suite; prior four unrelated failures
  remain previously recorded, not claimed fixed.

## Remaining boundaries

C06 still needs actual current session/conversation/preference/generation/tool
eligibility validation and semantic relevance. Scope epochs only establish corpus
freshness. C13 maintenance/cutover remains unbuilt. No live memory setting, Chat,
procedural activation or forgetting-suppression implementation is claimed here.
Removing metadata requires consumers disabled first; never reset epochs under
active prepared caches. Prior manifests remain historical: this reviewed delta
intentionally evolves memory/schema.py, models.py, repository.py and the existing
identity erasure hook; the new implementation manifest records current sources.
