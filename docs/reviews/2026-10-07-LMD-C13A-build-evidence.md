# C13A/r1 — canonical vector-write safety evidence

2026-10-07, feature/live-memory-decisions; uncommitted, owner work retained.
Internal same-context verification only, not owner acceptance/full C13 cutover.
Original contract/source frozen before runtime edits; baseline failed on real PG
as recorded in contract review. Final contract corrects callable spelling to
MemoryPipeline.finalize; no added behavior or scope.

## Exact implemented delta

memory/repository.py existing _require_membership gains optional shared locks
on membership/user/workspace; _memory_by_id_cursor gains optional memory row
FOR UPDATE. Defaults unchanged; store_embedding opts in to both in one existing
transaction, with authority before memory. Content check and upsert now retain
those locks to commit; no provider call while locked. Optional expected_version
must be a positive integer and match current canonical version; content also
must match. No schema/DTO/memory/evidence store or alternate auth predicate added.

memory/service.py ensure_vectors and memory/pipeline.py finalize pass the version
captured before embedding. Existing failure counts/factual ingestion semantics
remain, tested through actual producer functions. Direct no-version calls remain
compatible; future maintenance must opt into snapshot/epoch requirements.

## Actual final evidence

- Before fix, synchronized real correction committed between read/upsert;
  baseline lock test failed as expected, 4.45s, before runtime modifications.
- .venv/bin/python scripts/test_env.py test -q
  tests/integration/test_vector_write_postgres.py tests/integration/test_memory_postgres.py
  tests/integration/test_voice_runtime_postgres.py: 41 passed/no skips, 87.07s.
  New tests observe actual pg_blocking_pids for correction and member revocation,
  release the write, then prove correction deleted vector and revoked member
  cannot write again. ABA/version, changed content, deletion, private/wrong scope,
  invalid version and legacy call compatibility pass. Synthetic vectors only.
- Separate scripts/test_env.py test -q tests/integration/test_indexed_memory_postgres.py:
  8 passed/no skips, 31.52s, including actual natural HNSW/GIN/index recovery and
  synthetic backup/restore/scoped recall tests. 49 distinct DB tests across both runs.
- Four new producer units passed, 0.06s. Focused eight-file unit command including
  new producer, live controller, search/caller/indexed, identity/selector/Voice
  transaction groups: 243 passed, 1.80s.
- Full .venv/bin/python -m pytest -q tests/unit: 532 passed, 4 failed, 14.46s.
  Same previously recorded Mail audience, DocumentsPanel forbidden marker, MCP
  migration workspace-source assessment and runtime workspace_files marker.
  Not a full green suite. No new failing tests.
- C02/C03A/C17A/C05A-C06A implementation manifests remain hash-identical.
  C01 changes ONLY memory/service.py; C03R changes ONLY memory/repository.py;
  their other manifest entries still pass. These deliberate reviewed deltas are
  tracked by C13A's new manifest, not overwritten historical manifests. C03R Voice
  transaction behavior reverified in actual units/DB consumers.
- memory/schema.py, uv.lock, test harness/compose/old tests unchanged relative
  to frozen source. git diff --check clean. No production DB/provider calls.

Harness exact resono_vault_test/vault_test/127.0.0.1:55436; image and test-only
mount verified in contract review. Existing frozen uv sync rebuilt only this
editable project for the prior license package-data change, no dependency/lock
upgrade. Harness stopped after runs; test data volume retained, no reset.

## Remaining, not duplicated

C13A fixes a concrete canonical publication race, not all vector-maintenance
correctness: metadata retrieval epochs, repair of stale/invalid compatible rows,
durable jobs/leases, model-generation eligibility, maintenance/cutover and C06
actual current/relevance loaders still require reviewed contracts and proof.
User/workspace deactivation lock behavior is supported by explicit shared table
locks but no separate synchronized deactivation test was run in this grouping.
No production live or indexed composition change. No schema rollback needed;
removing this guard reintroduces a demonstrated unsafe race and is not safe
production rollback. Next actual source review: metadata epoch/typed loader delta.
