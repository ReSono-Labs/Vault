# LMD-C03A — scoped conversation identity and immutable submitted turns

Revision r1. Lifecycle VERIFIED (internal same-context review; not owner acceptance). Outcome: authenticated callers can
create one private conversation, submit a finalized text turn exactly once and
load it without model/tool/learning effects. This removes C03/C08 identity cycle.
Authority original r11 R01/R12/R19/R24/R35 plus DA-R04/05/07/10/11, October7 review.
Not a functional Chat UI, new agent or active production feature. No draft storage,
models, events streaming, provider/voice session, learning, attachments or shared
conversation policy. New schema/adapter is NEW owner-directed work; source pattern
reuse current local_identity/schema.py/repository.py and voice/repository.py authority.

Owner conversation module for header/segment/turn identity; conversation_evidence
consumes these later. New exact files app/vault_runtime/conversation/{__init__,
contracts,schema,repository}.py. New tests tests/unit/test_conversation_identity.py
and tests/integration/test_conversation_identity_postgres.py. One existing runtime
edit allowed: local_identity/repository.py:_erase_user_data_cursor add only
('vault_conversations','user_id') to existing _delete_if_exists list. It is a
safe no-op when table absent and cascades only that user's conversation rows.
No composition or API mounting, no lock/dependency changes. New directory
only conversation. No imports from optional live/routing/learner packages. Evidence
destination docs/reviews/2026-10-07-LMD-C03A-build-evidence.md. Documentation status
updates allowed only current contract/review/checkpoint/change index/changelog.

## Exact database boundary

Same PostgreSQL, vault_private. Types below are mandatory for this slice; indexes/
keys/checks translated literally to parameterized schema statements, with usual
CREATE TABLE/INDEX IF NOT EXISTS and schema fingerprint in local_schema_metadata.
ensure_schema is explicit repository method, NOT mounted in production composition.
Existing local identity must exist first. No migration/backfill/drop of old records.

All three tables: user_id text NOT NULL FK local_users ON DELETE CASCADE;
workspace_id text NOT NULL FK local_workspaces ON DELETE CASCADE;
created_at/updated_at timestamptz NOT NULL DEFAULT now(). All relationships include
user/workspace/conversation scope, never ID-only cross-scope joins.

vault_conversations:
- conversation_id text PK (server uuid4 string); create_key text NOT NULL;
  history_version bigint NOT NULL DEFAULT0 CHECK>=0; next_turn_ordinal bigint
  NOT NULL DEFAULT0 CHECK>=0; state text NOT NULL DEFAULT'open' CHECK open/sealed;
  title text NOT NULL DEFAULT'' CHECK length<=256.
- UNIQUE(user_id,workspace_id,conversation_id); UNIQUE(user_id,workspace_id,create_key).
- Index(user_id,workspace_id,updated_at DESC,conversation_id).

vault_conversation_segments:
- segment_id text PK (server uuid4); conversation_id text NOT NULL; ordinal bigint
  NOT NULL CHECK>=0; state text NOT NULL DEFAULT'open' CHECK open/sealed/incomplete.
- UNIQUE(user_id,workspace_id,conversation_id,segment_id);
  UNIQUE(user_id,workspace_id,conversation_id,ordinal).
- Composite FK(user_id,workspace_id,conversation_id) -> conversations same columns
  ON DELETE CASCADE; partial UNIQUE(user_id,workspace_id,conversation_id) WHERE
  state='open'. No close/resume workflow built now: one segment ordinal0 at create.

vault_conversation_turns:
- turn_id text PK (server uuid4); conversation_id/segment_id text NOT NULL;
  ordinal bigint NOT NULL CHECK>=0; submission_key text NOT NULL;
  input_text text NOT NULL; input_fingerprint text NOT NULL CHECK length=64;
  submitted_history_version bigint NOT NULL CHECK>=0;
  state text NOT NULL DEFAULT'submitted' CHECK submitted/running/completed/interrupted/failed.
- CHECK octet_length(input_text)<=65536 and length(input_text)>0; whitespace-only
  input rejected in typed validation, text otherwise byte-for-byte preserved.
- UNIQUE(user_id,workspace_id,conversation_id,turn_id);
  UNIQUE(user_id,workspace_id,conversation_id,submission_key);
  UNIQUE(user_id,workspace_id,conversation_id,ordinal).
- Composite FK(user_id,workspace_id,conversation_id,segment_id) -> segments matching
  columns ON DELETE CASCADE. No FK to login session: history survives ordinary login
  expiry, but every operation validates current session. No relation to decisions.

Text bound65536 UTF8 bytes is a fail-explicit bounded internal foundation contract,
not model context/production composer limit or silent truncation. Later large-input
contract may raise it; this slice rejects oversize before writes. IDs/keys trimmed,
nonempty, <=256 UTF8 bytes; exact title<=256 characters. No permissive JSON blob
for scope/content. Submitted text never updated; state transitions aren't exposed
in this slice. Fingerprint sha256(input_text UTF8) and input contract version1.
Future attachment-bearing submission requires revised contract/fingerprint shape.

## Interfaces and transactions

ConversationRepository(database_url, connector=None) follows existing connection
injection convention. ensure_schema()->None, create(principal:LocalPrincipal,
create_key:str)->Conversation, load(principal,conversation_id)->Conversation,
submit_text(principal,conversation_id,submission_key,input_text,
expected_history_version:int)->SubmittedTurn, turn(principal,conversation_id,
turn_id)->SubmittedTurn. Immutable dataclass fields mirror required columns;
returned Submit includes duplicate:bool and committed history_version.
Explicit domain errors AuthorizationError, NotFoundError, ConflictError,
InputError; no raw SQL/secrets in browser-facing messages. No routes mounted now.

Auth SQL follows inspected VoiceSessionRepository._require_authority predicate:
current local session user/workspace, active/unexpired session, active user,
membership and workspace. Copy only that neutral predicate into owned adapter,
not import Voice runtime or rely on old login identity from conversation row.
load/turn also require row owned by exact current user/workspace. Shared workspace
membership does not share another user's conversation. Revoked session/membership
denied; owner role does not give implicit access to another private conversation.

create transaction: validate auth; lock/create by(scope,create_key) with conflict
retry through INSERT ON CONFLICT then SELECT; exactly one header and segment0
committed atomically. Duplicate create returns existing header/segment, no new
identity. No source_voice_session or reopen/copy old history in this slice.

submit transaction: validate auth; lock owned header FOR UPDATE; look up same scoped
submission_key BEFORE expected-history-version comparison. Equal exact text and
fingerprint returns original turn/current committed submit version (stored version
plus1), even if later turns exist; changed text ->Conflict. For new key require
open header/open segment and expected_history_version equals current version.
Assign header.next_turn_ordinal, insert submitted turn, increment history_version
and next_turn_ordinal once, update updated_at. Commit before acknowledgment.
Rollback/crash creates no partially advanced header; duplicate retry cannot duplicate
turns. Concurrent different submits at same expected version: one wins, one conflict.
No active-running model restriction yet because no model runs in this slice.

## Verification, prerequisite and reversal

Dependency-ready inputs: current identity schema/principal, psycopg in existing
environment, Docker Compose test definition, global DSN allowlist inspected. Test
DB is presently stopped; starting EXISTING isolated harness during Phase03 is
allowed by this contract, no new infra files/production migration. Validate resolved
DB name resono_vault_test, loopback port55436 and test volume
resono-vault-test-postgres-data before destructive fixture. If configured override
differs, STOP; never redirect pytest to installed Vault. No reset/down --volumes.
New fixture refuses unsafe DSN itself before any DROP (global gate alone insufficient).
Reference current destructive memory fixture only after this verification.

Commands during build: .venv/bin/python -m pytest -q tests/unit/test_conversation_identity.py;
then .venv/bin/python scripts/test_env.py test -q tests/integration/test_conversation_identity_postgres.py
(existing helper starts isolated container); git diff --check. Integration skip
is NOT a pass; missing Docker/unsafe fixture ->STOP, never relax gate. No model calls.

Tests: repeat create10 times one header/segment; repeat submit equal key one turn
and one version increment; changed same-key content conflicts; retry old key after
new turn returns original; concurrent submit conflict; rollback before/after insert;
65536-byte accepted/65537 rejected, multibyte boundary; exact text including spaces;
cross-user/shared-workspace/membership-revocation/login-expiry denial; cross-scope
FK rejected; migration twice preserves rows/schema fingerprint; user/workspace
deletion cascades owned rows; no model/tool/memory calls/imports; no Voice sessions
created. Real DB evidence plus independent expected SQL constraints, not fake-only.

Stop on authority drift, migration loss, unsafe DSN or broader path needs; return
review, no speculative widening. Rollback remove unmounted module if no consumers;
never delete pre-existing user data. Test cleanup confined verified test schema.
No production installation, erasure scheduler or external blobs exist in slice.
Completion: actual scoped/idempotent persistence tests+reviewed full diff and hashes;
VERIFIED not owner-accepted by default. Later C03/C08 must consume this exact parent
contract and be re-reviewed after implementation identity exists.
## Review correction clarifications (before readiness)

Auth predicate holds FOR SHARE OF session/user/membership/workspace rows through
transaction commit; membership/session revocation cannot pass between authorization
and append. Use consistent lock order auth rows then header; database deadlock error
propagates for idempotent caller retry, no hidden transaction/model retry. Validate
nonnegative integers with exact int type (not bool), well-formed UTF8, no NUL bytes;
Postgres text cannot store NUL. Header/segment typed results expose server IDs only.

Account removal source uses tombstone, so physical user FK cascade is not proof.
Test LocalIdentityService.remove_user through actual erasure list: conversations
in shared workspaces erased; other member's conversation retained. Workspace delete
cascade also tested separately. No live caches/workers/blobs exist in this slice;
later modules must still register stop/erase before mounting. Rollback of erasure
list entry allowed only after all owned rows gone/unmounted; never leak retained
content by disabling cleanup with rows present.

## Build checkpoint — 2026-10-07

Bounded unmounted repository/schema implemented. 26 validation/dependency units,
51 real isolated-Postgres conversation tests and 14 existing identity integration
tests PASS; combined focused units/regressions 74 PASS. Exact implementation
identity and scope review in [build evidence](../reviews/2026-10-07-LMD-C03A-build-evidence.md).
No production migration/API/UI/model/capture mounting. VERIFIED, not CLOSED.
Historical next-stage instruction is superseded: C17A is already verified and
C03B's extra user-final row withdrawn. Current register owns next review; C08 and
source capture must consume these actual identities, not recreate them.

## October8 completion amendment — existing C11 submitted inputs

The immutable submission now optionally includes up to four private attachment IDs.
The original text fingerprint stays the text identity; exact sorted attachment IDs
are checked separately on every same-key retry, including lost acknowledgments.
Binding occurs inside the existing submit/header transaction. Missing, expired,
foreign, duplicate or already-bound inputs roll the entire submission back.
No fake Voice source or workspace publication is introduced.

The existing managed filesystem gains a private user namespace; conversation-owned
metadata holds content hash, actual MIME, extraction coverage and final turn FK.
Five MiB/file, four files/turn,100MiB/private workspace and24-hour unsubmitted
retention are explicit limits. PNG/JPEG/WebP are real image parts; UTF-8 text,
text PDFs and DOCX body extraction are real text parts, never filenames alone.
PDF visual coverage and DOCX body-only coverage are declared; unsupported/scanned,
encrypted, embedded-visual or oversized extraction is rejected before submission.
Decoding runs in a short-lived512MiB/10CPU-second process with a15-second wall
limit. Submitted originals rehydrate within the active segment, with explicit total
context limits. Private-history display returns metadata only. Retention cleanup
uses the existing dispatcher and managed filesystem. Account erasure removes the
existing private user root and cascades the conversation metadata.

Original attachments are not yet qualified for procedural activation; metadata
alone is insufficient. Attachment-dependent factual review is deferred rather than presenting external
document text as verified tool facts or omitting visual input. Current
staging uses local previews; full persisted preview/channel acceptance remains
subject to the single register, not implied by this implementation amendment.


### Completion continuation — qualified original attachment inputs

Both existing Chat learners now reread the owned submitted bytes, verify their
original hash/size and rerun the same bounded decoder under the source fence.
Extraction MIME/text/coverage must still match. Evidence IDs include the original
attachment ID and byte hash; documents use an explicit document role, never a fake
user statement or verified tool result. Candidates citing document evidence must
use model_derived authority, validated before publication/checkpoint acceptance.
Original images are supplied as typed image inputs to the SAME configured factual
and procedural reviewer, including window/reconciliation calls. Gemini uses its
native inline image parts; SDK-backed providers use the existing typed input path.
No visual content is inferred from metadata, and declared text-only PDF/DOCX
coverage cannot prove omitted visuals/layout. Changed files invalidate qualification.

The procedural source gate compares the exact submitted turn-by-turn attachment
manifest against original capture and links actual attachment context sources to
its decision points. Metadata-only or unmatched capture stays unknown. Bound16
inputs/20MiB per review, private scope and existing source/permission gates remain.
Mounted isolated-DB checks demonstrate text learning, both reviewers reading the
same original image bytes, canonical document provenance and rejection after byte
mutation. These are synthetic-provider integration checks, not real-model accuracy
acceptance or an unsupported claim that extraction captures all document semantics.
This amendment supersedes the earlier blanket learning deferral for attachments.
