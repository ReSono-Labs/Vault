# C06B/r1 — coherent validity and scoped stream lifecycle evidence

2026-10-07; feature/live-memory-decisions, uncommitted. Internal bounded proof,
not full C06/Chat/Voice adoption. Original grounding unchanged; contract, source
and same-context attack review frozen before runtime edits.

## Actual delta and reuse

Extracted C13B memory snapshot cursor/ID validation and C07A preference cursor
read, preserving public behavior. Canonical ConversationRepository now owns the
minimal scoped header/segment/final identity read. Final validates actual turn
scope/segment/fingerprint/state and header==submitted_history_version+1; pre-submit
history version permits exact draft/final rebind, competing turn invalidates it.
No new schema, source payload, auth predicate or fabricated LocalPrincipal.

LiveStateLoader uses one short REPEATABLE READ transaction and existing neutral
session-scope shared locks for conversation, preference and memory snapshot.
Repository cursor helpers stay on that single connection even when an injected
repository's configured URL differs. No provider/relevance/model work while locked.
CurrentStateGuard requires external source/procedural currentness callback; no
permissive default. Callback runs before the fresh canonical capture so changes
during it are not hidden by an earlier memory read. Off, epoch/history mismatch,
wrong prepared identity, missing/changed canonical records and errors reject.
This is freshness, not semantic relevance or complete procedural eligibility.

ScopedStreamRegistry owns bounded handles only to already-bound VoiceMemStream
instances. Scope/utterance/loop binding, duplicate/capacity constraints enforced;
thread-safe preference notification removes affected old handles and schedules
invalidate on their existing loop. Other user's stream is untouched. No second
draft buffer, scheduler or cancellation/worker implementation. Owners still drain
actual work; closed loop error is explicit. Fresh guard rejects Off independently
of when queued loop callback executes. Stale registration cannot publish because
every guard checks actual preference; production callers must capture freshly.

Optional API invalidation callback runs after committed POST, before response;
conflict does not notify. Callback failure reports503 with safe error and committed
enabled/epoch, not rollback fiction or raw exception. Composition does not mount
a live registry/controller yet; C08/C12 consumers must inject this existing hook.

## Targeted evidence

- Existing state/preference/conversation/live component unit groups: 95 passed,
  1.14s. No complete suite rerun.
- scripts/test_env.py test -q new current-state unit/integration files plus
  C13B state and C07A preference integration files: 23 passed, 40.45s.
- Actual Off API to registered guarded VoiceMemStream plus then-current four
  registry units: 5 passed, 3.11s.
- Final five new units including foreign/closed owning-loop proof: 5 passed,
  0.48s. Total distinct tested coverage: 100 units, 20 real PostgreSQL tests.
  No skips/failures. Existing unrelated four full-suite failures remain historical.
- Real concurrent mutation between preference and memory reads proves coherent
  old snapshot (not mixed old/new); subsequent capture sees both committed changes.
  Exact final rebind, wrong final fingerprint/segment, newer submitted turn,
  metadata at same version, deleted record, Off/On ABA, scope and revocation pass.
- Actual existing stream pending debounce is invalidated by committed API POST;
  no retrieval port starts. Blocked underlying recall cannot publish after Off;
  wait_closed remains pending until worker releases. Scoped other-user handle
  survives. Explicit capacity/duplicate/owner/loop/error behavior tested.
- Callback-after-commit, conflict-no-notification and committed failure semantics
  pass actual database-backed API checks. Synthetic external guard/recall only;
  no provider, tool, historical review or learned-rule activation performed.
- Exact test database/user/loopback55436, pinned PG image and test-only volume
  checked; harness stopped, volume retained. No installed DB/donor/dependency changes.
  git diff --check clean. Older C13B/C07A manifests deliberately evolve only
  reviewed cursor/existing API/conversation seams; originals remain historical.

## Remaining / removal

Actual factual indexed recall/relevance adapters, complete context-source guards,
procedural/capability/generation guards, production registry enrollment, Chat/
transcription and final executor composition remain. This does not satisfy full
live recall merely by adding a guard. Off is preparation-only: normal final
retrieval/review code unchanged. Remove injection/consumers, invalidate/drain
handles first; no durable migration/source data loss.
