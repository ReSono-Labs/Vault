# C07A/r1 — scoped setting/API and shared authority evidence

2026-10-07; feature/live-memory-decisions, uncommitted. Contract/source/internal
review frozen before runtime edits. No blanket C07/C06 or full-build completion.

## Actual wiring

Existing Voice/Conversation current-session SQL extracted into local_identity/
authority.py. Both wrappers retain original errors; Voice remains unlocked,
Conversation holds shared session/user/membership/workspace locks. No third
predicate, new grant system or manufactured Voice session.

live_memory preference schema/repository owns only per-user/workspace setting
and monotonically increasing change epoch. Missing rows read On/0 without writes;
explicit set persists with optimistic epoch checking. Same-value current retry
keeps epoch; ABA changes it. Atomic first insertion and existing row lock avoid
lost concurrent changes. Membership composite FK cascades on actual account
cleanup, including retained deleted-user tombstone. Repeated ensure preserves it.

Composition initializes/injects this one repository; VaultLocalApiApp mounts
GET/POST /live-memory. Scope derives from authenticated current local session;
POST reuses existing matching cookie/header CSRF plus identity proof. Strict
two-field payload rejects user/workspace injection. Typed conflict409; invalid400;
auth401/403; missing module503; unsupported method404; no-store. No providers,
draft capture, retrieval mount, learning, UI or Background execution added.

## Targeted verification

python3 scripts/test_env.py test -q tests/unit/test_live_memory_preferences.py
tests/unit/test_conversation_identity.py tests/unit/test_voice_capture_transaction.py
tests/integration/test_live_memory_preferences_postgres.py
tests/integration/test_conversation_identity_postgres.py::test_live_authority_denies_reads_writes_and_duplicate_retries
tests/integration/test_conversation_identity_postgres.py::test_authority_shared_locks_hold_until_append_commit
tests/integration/test_voice_runtime_postgres.py::test_voice_lifecycle_is_bound_to_local_session_and_scope
passed 68 tests, 29.34s. Strict input/query/locks/dependency/error compatibility;
actual default, scope switching/isolation, persistence/no-op/ABA/CAS, concurrent
first writers, expiry/revocation, erasure, API authentication/CSRF/conflicts pass.

Additional actual HTTP socket/server test passed, 3.34s: authenticated cookie GET
On/0, database remains empty after GET, POST without CSRF denied, valid POST Off/1.
First HTTP attempt failed only on test expecting a single Cache-Control field:
existing server and app both emit no-store, combined legally as no-store,no-store.
Corrected assertion checks every combined directive is no-store; no runtime or
security weakening. Final coverage 69 distinct tests: 55 units, 14 real DB tests.
No skips or remaining new failures; broad suite not rerun per owner instruction.

Test-only database/user/127.0.0.1:55436/image and retained test volume verified;
same pinned PG image as C13B. Harness stopped, volume retained. No donor changes,
installed DB, provider call or dependency upgrade. git diff --check clean.
C13B implementation manifest still passes unchanged. Older C03A conversation
repository/dependency test and C03R Voice repository hashes deliberately evolve
in this reviewed extraction; originals remain historical, not rewritten.

## Outstanding integration

C06 must consume actual preference epochs/current session in publication/final
guards and invalidate queued preparation on Off. UI toggle is C09. Normal final
memory retrieval and factual review are untouched. Thus this delivered metadata
endpoint does not claim working live recall, cancellation or Chat UI. Optional
API injection remains removable; no facts/history are children of preferences.
