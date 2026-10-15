# LMD-C03R — existing Voice source-capture transaction repair

Revision r1. Lifecycle VERIFIED after bounded internal build verification;
[build evidence](../reviews/2026-10-07-LMD-C03R-build-evidence.md) records final code/tests.
Owner authorizes aligned reviewed contracts/build on
existing feature branch, not a production deployment or blanket feature build.
Grounding: R01/R12/R22/R26/R31/R32; DA-R04–07/11. Register owns current status.

## Outcome / necessity / observed code

Current mounted chain: composition.py -> VoiceMemoryLearning ->
VoiceProviderEventCapture.capture; local_api/app.py POST /voice/sessions/{id}/events
returns201 for new event and200 for duplicate. capture invokes
VoiceSessionRepository.record_provider_event (one connection/commit), then
MemoryRepository.append_transcript (another), and skips append on duplicate.
Failure between commits loses transcript; duplicate cannot repair it. Provider
repo already compares payload hash/type/role/index on replay: DO NOT reimplement
that logic. Transcript append currently keeps prior row on index conflict without
checking text/metadata. Existing sources, grants, model/reviewer remain canonical.

Positive outcome: provider event and its final transcript commit together; exact
retry stays one event/entry, and retry can repair an old missing projection in an
authorized still-open session without executing tools. Conflicting transcript
retry fails instead of claiming success. This does not implement full evidence,
summary capture, live drafts, HNSW, learning or complete-session review.

## Exact scope, reuse and interfaces

Existing runtime allowlist ONLY:

- app/vault_runtime/voice/repository.py: expose transaction() returning existing
  _connect context; existing record_provider_event delegates to additive
  record_provider_event_in_transaction(connection, *, same existing arguments).
  Keep the one existing validation/auth/hash/insert/conflict implementation.
  Lock the existing scoped open Voice session row FOR UPDATE through event/capture
  commit, reusing _session_cursor's existing for_update switch, so close cannot
  interleave between source writes. No new authority predicate.
- app/vault_runtime/memory/repository.py: existing append_transcript delegates to
  additive append_transcript_in_transaction(connection, *, same args,
  reject_conflicting_duplicate:bool=False). Preserve public append signature and
  legacy duplicate behavior for unrelated callers. Keep one validation/membership/
  canonical insert implementation. RETURNING includes existing metadata_json for
  strict comparison, but public TranscriptEntry shape remains unchanged.
  Strict capture compares returned role, stripped event_type/text and metadata
  with requested values; a mismatch raises new MemoryTranscriptConflictError
  (MemoryRepositoryError subclass). Entry UUID is not compared on exact retry.
- app/vault_runtime/voice/events.py: existing capture uses sessions.transaction
  and both in-transaction primitives; append even when accepted=False if transcript
  supplied, strict comparison enabled. Translate MemoryTranscriptConflictError
  to existing VoiceSessionConflictError; preserve API payload/accepted semantics,
  no transcript branch and bounds. Exceptions propagate so connection rolls back.

Existing test edit allowed: tests/integration/test_voice_runtime_postgres.py,
new focused unit file tests/unit/test_voice_capture_transaction.py. No other
runtime/test edit unless review reopens. Documentation/evidence/register changes
allowed. No schemas, tables, event-store modules, migrations, dependencies,
composition/API/frontend/provider/Background/tool handler changes or donor writes.

Current production composition uses the same configured PostgreSQL DB for both
repositories. One supplied connection is the unit of work; primitives neither
open nested connections nor commit/close caller's transaction. Existing repository
public wrappers own their normal connection lifecycle. No generic transaction
framework or second transcript implementation.

## Failure, scope and concurrency contract

Validation/authorization failure, provider conflict, transcript conflict or DB
exception rolls back both source writes. Repeat exact provider id/type/role/hash/
index returns accepted=False; existing matching transcript is retained, missing
legacy projection inserted. Changed provider content uses existing conflict
check. Changed transcript text/metadata at occupied scoped index is conflict;
no overwrite, silent success or tool replay. Capture with no transcript records
provider event only, under existing role validation.

Current local session/member/user/workspace and originating Voice session scope
are checked by existing authorities inside transaction. Closed, wrong-login,
wrong-scope and revoked-before-call sessions remain denied. This slice does NOT
claim new mid-transaction membership/credential-revocation locking or historical
closed-session repair. Session-row lock serializes close and capture, and concurrent
same-event captures return one accepted result and one duplicate, one source entry.
No external side effect is retried or introduced by DB recovery.

## Required proof / operating safety

Unit tests: shared connection, no nested repository connect, wrappers delegate;
exact duplicate versus changed text/metadata; no-transcript; exception translation;
rollback propagated; source/module scope remains bounded. Fake ports alone do
not certify transaction behavior.

Real isolated PostgreSQL tests: rollback after event/before transcript and after
transcript/before commit; exact retry; legacy missing-projection repair; changed
text with same provider payload; occupied index of another event rolls back new
event; changed provider hash; wrong scope/revoked/closed existing regressions;
concurrent duplicate capture. Existing Voice and memory integration regressions
plus all197 focused foundation tests. No test weakening or production fixture.

Only existing compose.test.yml resono-vault-test-postgres container and
resono-vault-test-postgres-data volume, loopback port55436, exact DB resono_vault_test.
Verify resolved settings and container mount/port before fixture schema drop;
global tests/conftest.py rejects every other DB name. No production DB access,
provider calls, volume reset/deletion, export or installed package deployment.
Restore the initially stopped test harness after tests, preserving its volume.

Rollback: disable caller capture via existing feature unavailable boundary if
necessary; revert only this reviewed code delta under a separate approved repair,
not Git reset or a source-table drop. Existing rows remain readable. Removing
new transaction orchestration restores old behavior but reopens known loss risk;
never call that rollback complete-capture success.

## Review and exit

Material gate: separate commits/outbox/new ledger/shared existing connection?
Authority: original lossless evidence and no-duplicate requirements, actual source
methods above. Select shared existing connection for this bounded pair; no new
outbox/ledger needed. Counterexample: append opens another connection, a failed
capture leaves either source committed, duplicate repair skips missing transcript,
or strict guard changes unrelated public append behavior. Dependents C03C/C04/C08.
CONDITIONAL until review and real fault/concurrency regression proof.

Before build: record same-context internal contract review, source manifest, branch
and unchanged dirty-owner baseline; register READY only for this slice. Exit
VERIFIED only after required no-skip DB/fault proof; update source audit/status
without claiming any later feature complete. Stop/reopen on mismatch, scope leak,
unexpected schema/dependency/edit, unsafe DB target or lost source. Owner acceptance
and integrated feature/release remain unclaimed.
