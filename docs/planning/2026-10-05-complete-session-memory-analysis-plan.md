# Complete-session memory analysis

October8 C04H adds continuous completed-turn segmentation through existing
sealing/review dispatch at32 turns or48000 input/captured-event bytes. This
prevents never-idle accumulation; it does not replace full oversized-source
review or claim a huge individual tool/result is supported. See
[C04H](../contracts/2026-10-08-LMD-C04H-active-segment-boundary.md).

October8 C04G supersedes the procedural output-window/continuation absence only:
existing shared reviewer now resumes validated observation groups/pages while
retaining ALL captured source in each input. Existing stages/model/reconciliation/
publication stay authoritative. This does not permit silently dropping source
that exceeds the source-input guard; large-source windows remain open.
[Contract](../contracts/2026-10-08-LMD-C04G-procedural-assessment-windows.md).

October8 C04F owner correction: model-context handoff reuses the existing Voice
pattern and completed Chat reviewer summary. No separate context-compaction
model/store is required by this plan. Full-source analysis still uses original
evidence, never that summary. See [C04F](../contracts/2026-10-08-LMD-C04F-chat-session-context.md).

October8 C04D2 supersedes factual Chat window/continuation absence below: complete
sealed sources are losslessly partitioned, model pages/checkpointed corrections
resume under source/model fences, and canonical publication remains atomic.
Same configured model/worker/pipeline, not another analysis subsystem. See
[contract](../contracts/2026-10-08-LMD-C04D2-chat-window-review.md) and
[evidence](../reviews/2026-10-08-C04D2-chat-window-evidence.md).
Conversational context compaction, procedural/Voice windows and cross-key semantic
quality remain separate open work; original evidence is never replaced by summaries.

October8 C04E adds idle-triggered segment review through the SAME recovery
dispatcher and workers, with exact turn boundaries, independent memory/decision
completion and retained source dispositions. Chat need not close. This supersedes
idle-trigger/coverage absence below, not full windowing/compaction requirements.
[Contract and measured boundaries](../contracts/2026-10-08-LMD-C04E-idle-review.md).

October8 C04D1 implements exact source-span partition/coverage validation and
optional original-source metadata on canonical evidence, mounted through existing
bounded Chat publication. This supersedes the source-span absence below, not the
remaining windowed coordinator/overflow/consolidation work. Existing oversized
review guards remain. [Contract](../contracts/2026-10-08-LMD-C04D1-exact-source-spans.md)
and [bounded evidence](../reviews/2026-10-08-C04D1-source-span-evidence.md).

October8 C04C supersedes the earlier Chat autonomous-recovery absence below:
sealed segments now durably queue and restart through existing bounded workers,
session advisory locks, current local authority, and existing analysis/publication
checkpoints. Three attempts; explicit retry can resume exhausted work. Historical
segments are not automatically queued. Voice recovery, windowing, pagination and
consolidation remain open. See `../contracts/2026-10-08-LMD-C04C-chat-review-recovery.md`.

October8 C08B mounts existing bounded factual review for sealed Chat segments,
independently from procedural review. It reuses the actual canonical reviewer and
memory repository, with source revalidation and atomic checkpoint/publication.
No copied Voice transcript or fake Voice session is introduced. This is NOT C04
complete-window delivery: existing 100k/32 limits still fail explicitly; autonomous
recovery, cross-window consolidation and dense candidate pagination remain open.
[Exact contract](../contracts/2026-10-08-LMD-C08B-chat-factual-learning.md).

C04B retains successful factual Chat analysis in the existing segment checkpoint
across publication retry. Shared candidate/vector loops are extracted into the
existing MemoryPipeline; no separate factual publication implementation. Full
windows/consolidation/autonomous recovery remain absent, not inferred from this
bounded checkpoint. [C04B](../contracts/2026-10-08-LMD-C04B-chat-review-checkpoint.md).

2026-10-07 applicability: [Decisions/evidence grounding amendment](2026-10-07-decisions-api-evidence-grounding.md)
requires Phase01 revalidation of this plan's applicable draft, final-turn, causal
evidence, history coverage, evaluation and provider assumptions. GPT-Live is not
in scope. This notice is not a replacement design or renewed review approval.

Revision: LMD-ANALYSIS-PLAN-r7. Source-first capture and complete-analysis candidate.
Current document set: [authority map](2026-10-07-live-memory-document-authority.md).

Current allocation correction: C03B's proposed extra user-final row is withdrawn,
not built or required to unlock later work. C03A already owns immutable final text.
The event/table proposals below require necessity/reuse review against existing
source owners; they are NOT approved DDL. [Feature 06 validation](../reviews/2026-10-07-feature-06-session-evidence-analysis-validation.md)
and [reconciled scope](2026-10-07-live-memory-reconciled-build-scope.md) supersede
conflicting source-ledger prerequisites below. C03C is planned follow-on work for trusted
Voice/model/tool/reasoning producers, causal attribution, durable recovery and
coverage. Contiguous user events do not establish source completeness. Existing
Voice provider-event and transcript commits are separate and cannot prove atomic
capture; denied/failed tool observer coverage also needs explicit follow-on wiring.
Missing reasoning summaries remain missing, not reconstructed thoughts. Neither
reviewer may learn procedural rules from this foundation alone. See exact
[C03B contract](../contracts/2026-10-07-LMD-C03B-submitted-turn-evidence.md).
Authority: grounding r11 R31/R32. Evidence and preserved responsibilities:
[current implementation review](../research/2026-10-05-current-memory-implementation-review.md).

## Required outcome

The existing autonomous memory agent must analyze all retained completed
session evidence, with no silent tail truncation or candidate dropping. Preserve
its structured taxonomy, citations, evidence authority, reconciliation and
embedding model. The separate Background Agent is not involved.

## Proposed modular extension

A separate analysis coordinator calls the current reviewer in bounded windows
and consolidates validated results against ordered cited evidence. Existing
Voice finalization delegates through a narrow adapter; it must not acquire
inline windowing/retry logic. Keep the canonical repository authoritative.
Proposed ownership and narrow existing-code adapters are defined in
[modular integration](2026-10-05-modular-codebase-integration-plan.md).

Track a session snapshot and its fingerprint; partition by evidence entries
with stable IDs and explicit spans for oversized entries. Process every range;
retain source-order corrections, tool outcomes and cross-window references.
Consolidation itself must be bounded and hierarchical where necessary, without
truncating accumulated candidates. Every accepted candidate must preserve exact
citations back to the original evidence. Candidate limits paginate rather than
silently drop facts. Record coverage and incomplete/failed status explicitly.

Before claiming complete coverage, address provider-event/transcript dual-write
recovery, browser/server entry indexing and failed pending writes identified in
the source review. A larger review context cannot restore uncaptured evidence.
Use durable retry/checkpoints and independently idempotent publication; accepted
canonical memories survive failed procedural learning. Privacy/deletion/retention
policy still governs which source history may be retained or replayed.

## Delivery and evidence

Entry: reviewed current inventory, settled evidence/capture ownership and READY
contract. Positive scenarios: session exceeding 100,000 characters with a
required fact at the end; more than 32 durable facts; late correction of an early
fact; one oversized entry; restart between windows; identical finalization twice.
Negative scenarios: missing source range, fabricated citation, duplicate write,
truncated consolidation and forgotten information reconstructed from history.
Verify semantic review quality alongside complete coverage, not counters alone.

Stop on lost evidence, unauthorized writes or unresolved recovery semantics.
Rollback routes ordinary supported sessions to current review without claiming
long-session success; preserve source/accepted records. Exit requires full
coverage and truthful retry/failure evidence. No model calls, scaffolding,
implementation or production fixes are performed in Phase 01.

## Explicit evidence and job schema proposal

New coordinator-owned tables, under vault_private, proposed for reviewed contract:

| Table | Fields, identity and constraints |
|---|---|
| `vault_memory_analysis_jobs` | job_id text PK; user_id/workspace_id scoped FKs CASCADE; session_id; snapshot_fingerprint; source_contract_version; reviewer_contract_version; provider/model identity; state queued/running/retryable/failed/completed; lease_owner/lease_until; attempts; expected_entry_count; covered_entry_count; error_code; created/updated/completed_at. UNIQUE(scope,session,snapshot,reviewer contract) |
| `vault_memory_analysis_windows` | window_id PK; job_id FK CASCADE; ordinal; source_spans_json (entry ID,index,start/end offsets and source fingerprint); input_fingerprint; state; reviewer_model; output_json validated and bounded per page; output_fingerprint; attempts/error; timestamps. UNIQUE(job,ordinal,input_fingerprint) |
| `vault_memory_analysis_consolidations` | node_id PK; job_id FK CASCADE; level/ordinal; child_ids_json; input/output fingerprints; output_json; state; attempts/error/timestamps. UNIQUE(job,level,ordinal,input_fingerprint) |
| `vault_memory_analysis_publications` | publication_id PK; job_id FK CASCADE; candidate_fingerprint; canonical memory_id/version when accepted; disposition accepted/rejected/conflicted; evidence_ids_json; embedding_state pending/completed/failed; timestamps. UNIQUE(job,candidate_fingerprint) |

These are checkpoints/derived reviewer outputs, not another memory store. Scoped
FKs alone do not authorize access; repository methods enforce active membership.
No raw private history in global job metrics. Deletion removes/revokes jobs and
outputs; worker checks current scope/source policy before retry/publication.

Capture first projects C03A final turns and existing scoped Voice/provider/
transcript/tool sources. New persistence is only for demonstrated missing causal,
selection, model-call and coverage metadata under exact review, not copied source
payloads. `vault_conversation_events` is a conditional earlier representation,
NOT a mandatory ledger/C03B prerequisite. Illustrative fields were: event_id PK,
user/workspace FKs, conversation_id, turn_id, source/provider event identity,
event_kind, source_role, acknowledged sequence, finality/status, payload_json,
content_fingerprint, timestamp; UNIQUE(scope,conversation,source_event_identity).
Each event/transcript append is atomic through an adapter transaction or durable
outbox/recovery contract; don't claim both if only one committed. Server allocates
ordered transcript index under the existing session advisory lock for all new
producers. Browser carries producer sequence/idempotency, not canonical index.
Preserve tool/correction chronology and causal provider item IDs. Existing paths
must adopt this shared append seam before complete capture is claimed.

Genuine available summaries and truthful absence MUST be captured. Candidate
representation: `vault_conversation_reasoning_summaries`: summary_id PK, source-ref/FK,
turn_id, provider/model, response_id, summary text, availability present/unsupported/
absent/interrupted/truncated, original source_kind, timestamps. Original provider
summary is never replaced by inferred reviewer rationale. Encrypted opaque
reasoning is not readable summary content. Finalization waits for acknowledged
producer sequence; failed writes remain retryable/incomplete even after close.

## Complete-context algorithm and recovery

1. Close captures a watermark and snapshot of acknowledged final entries. Claim
   durable job BEFORE model work, using unique fingerprint and expiring lease.
   A closed UI may return analysis pending; memory analysis proceeds autonomously
   in its own coordinator worker, not the separate Background Agent. Existing
   external/plugin finalization delegates the same coordinator with compatibility
   result/pending status explicitly contracted. Don't silently change synchronous
   caller semantics without updating adapters and tests.
2. Tokenize according to selected reviewer model; reserve instruction/output and
   consolidation budgets. Partition all retained evidence into bounded windows;
   oversized entries split with stable offsets. Boundary overlap is permitted
   but coverage counts unique spans. No [:100000] or silent [:32] truncation.
3. Reviewer returns validated candidates plus explicit complete/overflow status.
   Split a too-dense input window or resume candidate pages; continuation must
   advance coverage and have bounded retry count. An overflow without recoverable
   progress is failed/incomplete, never successful with missing candidates.
4. Carry ordered correction/contradiction references and durable topic ledger into
   later windows; retrieve bounded existing canonical matches by key/scope for
   comparison. Citations retain original entry IDs/indexes/spans. Existing output
   temporal fields are not persisted unless a later approved schema supports them.
5. Hierarchical consolidation partitions by stable subject/key and preserves
   unmatched candidates. Each node uses bounded child batches; source-order
   corrections and tool authority survive merging. Cross-topic contradictions
   get a reconciliation pass. Coverage of tokens does not prove semantic accuracy:
   held-out late-fact and cross-window correction cases must pass separately.
6. Publication validates existing v2 taxonomy/evidence and applies canonical
   reconciliation through an atomic idempotency marker+write transaction per
   candidate. Crash after record write before marker cannot duplicate versions.
   Accepted record embeds asynchronously with checked fingerprint/epoch; embedding
   failure leaves canonical record valid and maintenance retryable.
7. Complete only after every source span is accounted for, every consolidation
   node succeeded, and every final candidate has accepted/rejected/conflicted
   disposition with reasons. Store bounded display summary separately; that summary
   is not the evidence used to review the entire session. Embedding completion is
   a separately truthful status, not a reason to discard facts.
8. Lease expiry resumes missing nodes only, with immutable input fingerprints.
   Source changes create new snapshot/superseding job, never mutate completed
   evidence. Existing running/failed ingestion rows map explicitly to job state;
   an existing summary alone is not proof of completed ingestion. Cap retries and
   expose exhausted status; operator can resume after cause is fixed.

Forget/rebuild policy needs explicit resolution: deleting canonical memory while
retaining historical transcript must not recreate it automatically. Proposed
minimal suppression ledger: scope, normalized canonical key, source coverage/
evidence fingerprint, deletion time/epoch, authorized reintroduction event.
It contains identifiers rather than forgotten content. Exact policy is owner-
reserved; until settled, historical rebuild of forgotten candidates is blocked.
Do not erase all session history silently to make rebuild safe.

## r3 history/attachment integration

[History coverage](2026-10-05-chat-session-history-plan.md) is authoritative for
resumed conversations: old evidence remains readable context, newly supported
contributions publish idempotently, and per-consumer coverage records disposition.
Never use session boolean or full-fingerprint uniqueness alone to prevent repeated
canonical writes after continuation. Publication transaction includes contribution
identity and new evidence coverage; later correction remains eligible.
Legacy completed reviewer jobs may have silently truncated evidence and therefore
have unknown complete coverage, requiring explicit catch-up rather than trusting
summary presence. Snapshot fingerprint includes submitted attachment hashes and
extraction contract/coverage plus retained reasoning identity where applicable.
Window source spans reference file pages/derivatives alongside final transcript,
with authority distinctions, supported capability and retention controls.

## Phase02 pipeline compatibility corrections

Reviewer output today indexes citations by entry_index; actual TranscriptEntry
projection has no metadata. Window review must preserve global citation identity
or supply reversible mapping; reset window0 indexes cannot cite unrelated source.
Define window-review typed adapter without silently changing existing review(str)
callers. Load scoped attachment/summary metadata explicitly. New durable jobs cannot
be active until process worker ownership/restart/shutdown and erased-source checks
are reviewed; model progress may outlive request but isn't a Background goal.
Publication idempotency must run in same transaction as canonical reconciliation;
separate marker AFTER existing reconcile is insufficient. Repository unit-of-work
adapter is a necessary narrow seam, not parallel canonical SQL implementation.
Unresolved forgot/replay policy blocks automatic historical reconstruction only,
not unchanged short-session learning or search foundation.
## October7 evidence consumer boundary

Canonical memory analysis still consumes authorized finalized evidence independently
of procedural learning. New causal/quality projections are owned by learning plan
and captured by conversation_evidence; do not duplicate definitions here. Speculative
drafts and rejected routes cannot enter canonical review as user assertions. Preserve
original tool outcomes even when reviewer assesses a call unnecessary. Model-derived
interpretation and original reasoning remain different source kinds. Completeness
means retained authorized source coverage, not recovery of uncaptured historical
reasoning. Procedural failure never blocks already accepted canonical memory.
## Candidate source-linked capture contract — review before DDL

This plan owns capture/coverage and necessary missing metadata; learning owns
derived procedures. Existing turns/transcripts/provider/tool ledgers retain source
authority. A scoped evidence adapter unifies references without another copy of
their payloads. vault_decision_execution_evidence is a read-only projection.
The table/column/port shapes below are conditional candidates, not approved DDL.
C03 repair/C03C must bind actual source identities and prove each new persisted
field necessary before selecting a representation. Withdrawn C03B extra user-final
row is required by neither C08 nor either reviewer. Required causal/summary/tool/
selection/coverage capture is NOT withdrawn with that redundant representation.
Provisional jobs stay transient; only preparation validated against submitted text
can be linked to final evidence. Do not retain raw superseded input/context prompts.

Illustrative event/metadata representation only if justified: event_id text PK; scope; conversation_id/segment_id
text; turn_id nullable text; canonical_sequence bigint>0; producer_key text;
producer_event_id text; kind text; origin text; payload_json jsonb object;
payload_fingerprint text length64; source_context_fingerprint text nullable;
causal_parent_event_id text nullable; capture_state text complete/incomplete;
created_at timestamptz. UNIQUE(scope,conversation,producer_key,producer_event_id);
UNIQUE(scope,conversation,canonical_sequence). Composite scope/conversation/segment
FKs; parent FK includes scope/conversation and cannot link another user's event.
Kinds include user_final, assistant_final, model_proposal, selection_final,
tool_authorization, tool_started, tool_result, tool_effect_unknown, user_correction,
capture_gap. Kind-specific typed validator enforces legal origin/payload.

Conversation already owns verified C03A vault_conversations/vault_conversation_turns,
immutable submitted text, idempotency and history version. Reuse actual C03A DDL/
types; attachment references and running-state orchestration are future deltas,
not already built identity fields. New metadata binds actual parent identities
or reviewed existing-Voice source refs, never fake Voice session FKs. Historical sources
link existing IDs; no manufactured turn grouping. Voice session auth remains current.

vault_conversation_selections: selection_id text PK; scope; final event/turn
composite FK CASCADE; selector_request_id text; original_revision bigint>=0;
definition/generation/version identities nullable text/integer (snapshotted values,
not cascading FK to derived generation); candidate_mapping_json jsonb array;
candidate_set_fingerprint text; input/context fingerprints text;
memory_refs_json jsonb array; capability_snapshot_fingerprint text;
selector_contract_version integer>0; provider/model text; result_json jsonb object;
disposition text reused/rejected/fallback; created_at. UNIQUE(scope,selector_request,
turn). Rejected observations retain only final-compatible identifiers/status, not
obsolete draft content. If rejected record contains no lawful final evidence, omit
it and count only transient aggregate waste. No durable unsent-session selections.

vault_conversation_reasoning_summaries retains proposal from prior section plus
response_id nullable and model_call_event_id composite FK, source_contract_version,
redaction/truncation status. One availability record per(scope,model_call,summary
source identity); original summary cannot be replaced with reviewer inference.
Decision summaries unsupported; missing original summaries don't imply tool success.

Candidate port, not a built interface or mandate for a new ledger:
CapturePort.append_final_event(scope, conversation_id, producer_key,
producer_event_id, payload, causal_refs) -> AppendAck(event_id,sequence,fingerprint,
duplicate). Server authenticates scope/session; transaction locks scoped conversation
row, checks duplicate with canonical bounded hash, allocates next sequence and
persists only approved source append/missing metadata. Equal duplicate returns original Ack; unequal duplicate ->409;
no ignored changed payload. Snapshot uses acknowledged watermark, sorted stable
IDs and source coverage. close waits acknowledgments or returns incomplete;
workers cannot claim complete on missing range. All repository operations scoped.

Existing VoiceProviderEventCapture currently commits provider ledger before separate
transcript write. C03 must use shared connection transaction for event + transcript
append + replay identity, or reviewed durable outbox with retry; current accepted=False
duplicate must NOT skip recovery of absent transcript. Prefer transaction adaptation,
not a third copied transcript. Contract must expose connection-aware repository
primitives instead of each opening another connection. Legacy client indexes remain
compatible projection while server canonical sequence becomes new producer authority.

Actual invocation is captured around VoiceToolRuntime.invoke/conversation_tools,
not solely ToolCatalog observer: authorization denial, schema rejection, replayed
cached call, invoking, exception/effect_unknown and result each get attributed
evidence. Preserve existing once-only ledger; atomic result+event append uses same
unit-of-work, with explicit capture-gap/recovery if external action completed before
DB acknowledgment. Never rerun external effects to repair capture. Observer only
supplements handler observations; no complete-capture guarantee from swallowed errors.

Source erasure unregisters event/payload/selection/summary caches and invalidates
derived coverage/examples; scope FK cascades don't prove running worker shutdown.
Evidence never cascades on decision generation deletion. Initial new events follow
existing final-session privacy boundary; no new indefinite-retention policy selected.
C03/C08 must define payload size/oversized source-reference handling with explicit
overflow/incomplete status rather than silent string slicing. No DB migrations built.
