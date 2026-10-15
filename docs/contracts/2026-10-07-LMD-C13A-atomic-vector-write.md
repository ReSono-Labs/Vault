# C13A/r1 — existing vector-write snapshot and transaction guard

[Build evidence](../reviews/2026-10-07-LMD-C13A-build-evidence.md); register owns lifecycle.
Original R06/07/R28/R31/R33, existing storage
plan correction/delete race requirements. Necessary prerequisite found during
C06/C13 loader/maintenance review, not production cutover or complete C13.

## Existing source / exact missing delta

Under /home/christian/Documents/Projects/ReSono-Labs-Vault/:
app/vault_runtime/memory/repository.py: store_embedding checks current content
via _memory_by_id_cursor, but holds no row lock between check and upsert.
_require_membership reads authority without holding it through the commit.
service.py: ensure_vectors and pipeline.py: MemoryPipeline.finalize produce vectors from
MemoryRecord snapshots; neither passes current_version to store_embedding.
Canonical content checks are reused, not recreated. Schema/FKs already prevent
orphan vectors after deletion, but do not prevent stale insertion after correction.
No retrieval_epoch exists: this bounded fix does NOT substitute for metadata epochs.

Allowed runtime edits only these three memory files. Add optional lock=False to
existing private membership/helper methods; ordinary callers/default query unchanged.
store_embedding takes shared locks on membership/user/workspace and FOR UPDATE
on the scoped memory record through upsert commit. Auth lock order precedes memory.
Add optional expected_version positive integer; check against locked canonical
current_version in addition to exact content. Both existing internal producers
pass the version they captured before embedding. Old direct API callers remain
compatible; future maintenance must pass version and later reviewed epoch guards.
No new copy of auth predicate, canonical store, embeddings, grant registry or model.

NEW tests/unit/test_vector_write_snapshot.py and
tests/integration/test_vector_write_postgres.py. Documentation/provenance/evidence
edits permitted. No schema, DTO, epochs, job table, maintenance worker, API,
composition, model credentials/dependencies, indexed ranking or live component edits.
No installed database or provider call. Only isolated harness resono_vault_test,
127.0.0.1:55436/vault_test, reused memory_context fixture/global safety gate.
Synthetic vectors explicitly test data, never represented as provider results.

## Material choice / review attack

Question: add another write adapter or repair canonical store_embedding? Choose
the latter: all producers already use this authority. Counterexample an old job
reads tea, correction changes to coffee, old job upserts tea vector after correction
removed it. Another case tea->coffee->tea has equal text but newer version: reject
old version instead of treating text equality as current-job identity.
Source-backed synchronization/negative test must reproduce baseline failure first;
then contract/source freeze and same-context internal review before runtime edits.

Locks linearize vector publication against correction/deletion/revocation; they
cannot stop provider work already underway or validate retired model generations.
Holding locks across the provider call is explicitly excluded: provider call
finishes BEFORE entering store_embedding. Wrong-model maintenance and actual
metadata epochs still require C13 remainder. CONTINUE bounded prerequisite only.

## Required proof and reversal

Real PostgreSQL tests: pause store after canonical read, observe correction and
revocation blocked until transaction finishes, release then confirm correction
removes vector/revocation denies subsequent writes. Reverse order rejects changed
content; ABA rejects version; deleted row cannot resurrect; private/shared/wrong
scope; invalid version; legacy no-version compatibility. Coordination releases
all events in finally and times out, never hangs indefinitely or uses sleep as
sole transaction-lock proof. Test caller forwarding on service and pipeline.
Run original memory/Voice/indexed DB regressions and relevant units/full units.
Schema unchanged; no migration or data rollback. Removing guard restores unsafe
race and is NOT a valid production safety rollback; keep indexed/live mounts off.
Record exact changed foundation hashes rather than claiming old C03R manifest
unchanged: its repository file is intentionally modified by this reviewed delta.
