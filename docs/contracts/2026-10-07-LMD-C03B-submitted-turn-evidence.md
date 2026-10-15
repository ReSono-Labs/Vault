# LMD-C03B — atomic submitted-turn evidence

HISTORICAL WITHDRAWN DESIGN. Body below records the rejected candidate, not
current capture architecture, allowlist or a prerequisite. No implementation.
Use current register/analysis plan via the document authority map. Required
finalized causal capture remains in C03 repair/C03C; source turns are reused.

Revision r1. Lifecycle BLOCKED — READY withdrawn by owner-requested duplication audit.
The prior review did not establish necessity of a separate user-final event row
when the immutable submitted turn already contains its source and fingerprint.
Historical READY manifest/review is not current build authority. Resolve existing
transcript/Voice ledger reuse and minimal new metadata before re-review/build.
Not independent review or owner acceptance. NEW owner-directed work.
Governing inputs: original grounding r11; Decisions amendment r2 DA-R04–07/10/11;
master r9, modules r6, analysis r5; verified C03A/r1 and C17A/r1 implementation
manifests. This is a bounded split of C03, not permission to implement its parent.

## Outcome and exclusions

Commit immutable finalized text and one source-linked user-final evidence event
in the same PostgreSQL transaction. Retry returns original identities. An explicit
repair operation may index a previously persisted turn without replaying actions.
No draft capture, complete-session claim, historical review, models, tools,
reasoning-summary adapter, Voice change, selector observation, worker, route or UI.
Full capture remains required before procedural learning; this foundation is
deliberately unmounted. No activation or new retention policy is established.

## Ownership and exact paths

conversation owns identity, submitted text and current authorization.
conversation_evidence owns the canonical event ledger and capture orchestration.
Use the existing conversation/local_identity PostgreSQL patterns, not a second
identity store or generic event framework. No donor modification or copied new
product behavior. Inspected sources: app/vault_runtime/conversation/{repository,
schema,contracts}.py; voice/{events,evidence,repository,tools}.py; tools/catalog.py.
Legacy Voice capture commits provider records and transcript separately; do not
borrow that crash window. Tool success is not proof of user-request success.

Allowed existing runtime edits ONLY:
- conversation/repository.py: expose transaction(), submit_text_in_transaction(),
  turn_in_transaction(); existing public submit_text/turn delegate to those same
  canonical implementations. Preserve existing signatures, validation and auth.
- conversation/schema.py: additive named UNIQUE(user_id,workspace_id,
  conversation_id,segment_id,turn_id) on turns, including existing-table upgrade.

Allowed new files: app/vault_runtime/conversation_evidence/{__init__,contracts,
schema,repository,capture}.py; tests/unit/test_conversation_evidence.py;
tests/integration/test_conversation_evidence_postgres.py. Only new runtime directory
conversation_evidence. Documentation lifecycle/evidence/checkpoint updates allowed.
Forbidden: production composition/migrations, API/frontend, identity erase logic,
Voice/tool/memory/learning/decision_routing changes, SDK/dependencies, paid calls,
new connections authority, automatic backfill or third agent.

## Database definition

Explicit ensure_schema only, after local_identity and C03A; vault_private in the
same database. CREATE IF NOT EXISTS plus existing schema fingerprint convention.
No production installation. Upgrade adds named turn constraint idempotently and
preserves all rows; do not hide incompatible existing schema errors.

vault_conversation_events columns:
- event_id text PRIMARY KEY, server uuid4; user_id/workspace_id text NOT NULL with
  existing local-user/workspace FK ON DELETE CASCADE;
- conversation_id/segment_id/turn_id text NOT NULL;
- sequence bigint NOT NULL CHECK >0;
- producer_key text NOT NULL CHECK ='conversation.submit_text.v1';
  producer_event_id text NOT NULL CHECK =turn_id;
- kind text NOT NULL CHECK ='user_final'; origin text NOT NULL CHECK ='user_submission';
  capture_state text NOT NULL CHECK ='complete'; schema_version integer NOT NULL CHECK =1;
- payload_json jsonb NOT NULL CHECK object and octet_length(payload_json::text)<=4096;
  payload_fingerprint text NOT NULL CHECK length=64;
  created_at timestamptz NOT NULL DEFAULT now(). No updated_at or update method.
- UNIQUE(user_id,workspace_id,conversation_id,event_id);
  UNIQUE(user_id,workspace_id,conversation_id,sequence);
  UNIQUE(user_id,workspace_id,conversation_id,producer_key,producer_event_id).
- Composite FK(user_id,workspace_id,conversation_id,segment_id,turn_id) -> turns
  identical columns ON DELETE CASCADE. This enforces actual segment/turn scope,
  not two independently valid but mismatched foreign keys.

Payload exactly: input_contract_version=1, input_fingerprint (SHA256 actual stored
text UTF8), submitted_history_version and committed_history_version=previous+1.
No copied raw text, user-provided payload, causal parent, speculative selection,
confidence or invented summary. Future kinds require a reviewed schema revision.
Source text is loaded only through current scoped turn authority. Existing private
conversation deletion cascades this ledger, including tombstoned account erasure.

Fingerprint: SHA256 deterministic UTF8 JSON (sorted keys, compact separators,
ensure_ascii=False, no NaN) of schema_version, scope user/workspace, conversation,
segment, turn, producer key/id, kind, origin, capture_state and payload. Exclude
event_id, sequence, timestamp and retry duplicate flag. Typed payload validation
must reject booleans as integers and malformed persisted rows; verify stored text
checksum before append. No silent coercion, truncation or corruption repair.

## Interfaces and atomicity

ConversationRepository.transaction() returns its existing connection context.
submit_text_in_transaction(cursor, principal, conversation_id, submission_key,
input_text, expected_history_version)->SubmittedTurn; turn_in_transaction(cursor,
principal,conversation_id,turn_id)->SubmittedTurn. These never commit/open a
connection; same validation/auth as existing operations, no bypass caller option.

ConversationEvidenceRepository(conversations:ConversationRepository): ensure_schema;
append_submitted_turn(principal,conversation_id,turn_id)->AppendAck;
append_submitted_turn_in_transaction(cursor,principal,conversation_id,turn_id)
->AppendAck; read_page(principal,conversation_id,through_sequence,after_sequence=0,
limit=100)->EvidencePage. Repository uses injected conversations' transaction port,
not a second DSN/connector. Append reloads actual persisted turn, never trusts a
caller-created SubmittedTurn as evidence. Existing InputError/AuthorizationError/
NotFoundError/ConflictError retained rather than competing error definitions.

ConversationCapture(*,conversations,evidence) requires evidence.conversations is
conversations (reject mismatched wiring before writes). submit_text with existing
final submission arguments -> CapturedSubmission(turn:SubmittedTurn,evidence:AppendAck).
It opens one connection/transaction/cursor, submits turn, appends evidence, and
returns only after commit. No after-commit best-effort logging.

Current authority is checked within the transaction using existing local-session,
user, workspace and membership predicates/locks. Lock conversation header FOR
UPDATE for append and submit. Duplicate producer identity is checked before
allocating sequence; exact canonical envelope/fingerprint returns original event
and duplicate=True, disagreement raises ConflictError without overwriting.
New event sequence = COALESCE(MAX(sequence),0)+1 under header lock. No independent
counter or history-version bump for evidence. New Ack has duplicate=False.
AppendAck immutable fields: event_id, conversation_id, segment_id, turn_id,
sequence, payload_fingerprint, duplicate. Event immutable fields mirror schema.

Fail before commit rolls back turn, header and event together. Lost acknowledgement
after commit retries original submission key and event identity. Existing C03A
submit without capture remains supported; explicit append repairs only its missing
event. Never replay provider/tool effects to recover evidence.

## Bounded reads, not complete-session seals

read_page validates exact ints (not bool): 0<=after_sequence<=through_sequence;
1<=limit<=100. Scope/current authority required even for empty pages. Ordered
sequence query <=through_sequence, fetch limit+1 to expose more, never hide a tail.
EvidencePage: events tuple, through_sequence, after_sequence,
checked_through_sequence, next_after_sequence (last returned if more else None),
missing_ranges tuple of inclusive SequenceRange(start,end),
source_coverage='not_established'. Checked range ends at last returned if more,
else requested through_sequence. Compute gaps as intervals, not enormous lists;
request above ledger end reports missing tail. New append above frozen watermark
does not enter page. Empty range reports no gaps, not complete source coverage.
No whole-session completeness boolean, seal, reviewer input or review trigger.
Contiguous stored user events do NOT prove assistant/tool/reasoning coverage.

## Required checks and failure criteria

New units: typed envelopes/fingerprints, invalid inputs, same-connection wiring,
duplicate equality/conflict, rollback injection, explicit no-model/no-tool/import
boundary. Run previous C01/C03A/C17A focused units and existing identity regressions.
Real PostgreSQL tests (skips are not passing):
- atomic first submit, repeat retries incl old key after later turns;
- failure after turn and after event rolls all state back; committed lost-ack retry;
- independent concurrent same/different-key submissions and appends, one identity;
- append existing immutable turn once; absent turn/draft rejected;
- expired session, inactive user/membership/workspace and cross-user/shared-workspace
  denial; wrong segment/turn FK and corrupted checksum/payload failure;
- >100 events explicit pagination, frozen upper watermark, internal/tail gaps,
  source_coverage never promoted to complete;
- upgrade actual C03A schema without new constraint preserves data; repeat ensure;
  account erasure in shared workspace removes only owned evidence, others survive.

Use existing scripts/test_env.py, independently require database resono_vault_test
at 127.0.0.1:55436 before fixture schema removal. No DSN override/production DB.
Test-only vault_private fixture cleanup permitted after guard. Preserve volume;
restore initially stopped test harness state. No inspection of historical user DB.

Evidence destination docs/reviews/2026-10-07-LMD-C03B-build-evidence.md and exact
implementation SHA256 manifest. Record actual commands/counts/skips/failures;
existing four unrelated unit failures do not become a green-suite claim.

## Stop, rollback and completion

Recheck frozen inputs and parent implementation hashes before build. Unexpected
source drift, unauthorized path, schema incompatibility or failed required check
stops dependent work; report instead of expanding scope. Reversal removes unmounted
capture/evidence package and additive seam/constraint using reviewed migration,
not destructive production SQL or reset of dirty owner changes. Existing public
conversation operations remain usable without optional capture. Preserve saved
turns/events until explicit erasure/migration authority; no automatic DROP.
Completion is VERIFIED bounded internal build evidence, not owner acceptance,
complete session capture, learning readiness or production feature release.
Stop after Phase03; next capture expansion requires Phase02 C03C review.
