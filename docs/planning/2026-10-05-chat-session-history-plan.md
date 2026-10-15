# Chat history, continuation and ingestion coverage

October8 C04H mounts automatic continuous-activity segmentation at completed-turn
boundaries (32 turns or48000 input/captured-event bytes), reusing normal sealing,
durable review intent and C04F handoff. No history compaction service is added.
Oversized individual turns and large display pagination remain separate gaps.
[Contract](../contracts/2026-10-08-LMD-C04H-active-segment-boundary.md).

October8 owner correction/C04F: reuse existing Voice session handoff, not a new
compaction service. Current Chat model context is its actual segment, latest
already-completed earlier same-conversation summary bounded exactly like Voice,
and existing selected canonical memory. Retained display/analysis sources remain
unchanged. This supersedes the speculative new context-checkpoint table/model
allocation below; that proposed DDL was never approved by its presence here.
[Actual contract/evidence](../contracts/2026-10-08-LMD-C04F-chat-session-context.md).
Large active segments and display-history pagination remain separate gaps.

Current document set: [authority map](2026-10-07-live-memory-document-authority.md).
This plan owns its design concern only; original grounding controls requirements,
register controls build status, and historical reviews/manifests are not work orders.

2026-10-07 applicability: [Decisions/evidence grounding amendment](2026-10-07-decisions-api-evidence-grounding.md)
requires Phase01 revalidation of this plan's applicable draft, final-turn, causal
evidence, history coverage, evaluation and provider assumptions. GPT-Live is not
in scope. This notice is not a replacement design or renewed review approval.

Revision LMD-HISTORY-r1. Phase01 candidate, grounding r11 R35/R12/R13/R32.
Ownership: new `conversation_history/` module (list/load/context/continuation),
existing evidence store authority and memory_analysis publication authority.
Source evidence: [research](../research/2026-10-05-chat-history-attachments-and-tools-research.md).

## Separate operations and placement

Add Chat to existing desktop/mobile navigation; history lives inside Chat as a
collapsible Sessions rail on wide layouts, drawer/button on narrow layouts.
Compact New Chat and recent sessions ordered by last activity; title/date/status,
selected indicator, cursor pagination, empty/loading/error retry. Suggested title
from first submitted text (bounded), optional rename; title generation not required
before chat works. Screenshot placement remains candidate pending visual review.
Don't clutter global navigation with sessions. Keep current Voice mode on when
switching Chat/Sessions/other pages. History selection doesn't close Voice.

List and load are scoped read operations: no reviewer/model, transcripts append,
tool effects or ingestion triggered. Reopen loads same stable conversation ID and
references original final events; no copy into a fresh transcript. New Chat creates
new ID only when needed. Proposed one selected session per view; many stored
sessions. Resume completed chat creates new activity segment/epoch on same history.
Never reopen old provider/live microphone transport or old authentication session.

Historical Voice items may be listed through READ-ONLY projection of existing
owner/workspace evidence after explicit migration/access contract. Starting a text
continuation from an old Voice item creates a Chat conversation with parent/source
reference, not a reopened Voice session or copied transcript. This supports old
history without changing existing Voice behavior/authentication.

## Proposed schema delta

| Object | Fields / constraints |
|---|---|
| `vault_conversations` additions | title, origin text/voice-reference, parent_conversation_id/source_session_ref nullable, history_version bigint, last_activity_at, archived_at, resume_epoch bigint; existing user/workspace scope |
| `vault_conversation_segments` | segment_id PK, conversation_id FK, ordinal unique per conversation, start/end event watermark, state open/sealed/incomplete, source snapshot fingerprint, timestamps |
| `vault_conversation_source_links` | conversation_id, original source entry/event ID, source scope/ref, link purpose context-only; unique pair; no payload copy |
| `vault_evidence_ingestion_coverage` | scope, source_entry_id, content_revision/fingerprint, consumer memory/procedure, reviewer_contract_version, disposition published/rejected/conflicted, publication_ref, job_id, completed_at; UNIQUE(scope,source revision,consumer,contract,contribution fingerprint) |
| `vault_review_contributions` | contribution_id PK, consumer, source set fingerprint, semantic candidate fingerprint, originating job, publication memory/version or proposal ref, disposition; source entry join table for multi-entry facts/corrections |
| `vault_conversation_context_checkpoints` | scope/conversation, covered event watermark and source fingerprint, compaction/model contract, summary text bounded, references/excluded-source state, status; derived, never substitutes source evidence |

Coverage is per evidence revision AND contribution/consumer, not boolean per
session. Candidate needs multiple entries: publication dedupe uses source set and
candidate identity too. Successfully reviewed evidence with zero memories still
gets terminal disposition/coverage. Failed/incomplete job doesn't advance success
watermark. Ingest status UI is derived pending/partial/completed/failed for actual
snapshot, not a stale flag. Content/hash mismatch with existing event ID is409,
not successful duplicate. Deletion/contract-change invalidates appropriate coverage.

## Context loading versus new learning

Display history paginated from canonical final evidence. Model context assembled
server-side: selected conversation source references, bounded recent final turns,
validated context checkpoint, relevant older-turn retrieval when needed, current
canonical memories. Preserve paired tool call/result structure, source order,
corrections and provenance; summaries aren't original reasoning. Never trust a
client's submitted history as replacement for server records. If history is larger
than model context, bounded compaction plus retrievable cited source is explicit;
full-session memory analysis still reviews all retained source via its coordinator.
Current tool/grants/model are resolved now, never restored from historical snapshots.

New submitted event is stored once with stable ID. Reviewing new segment can READ
older covered entries for interpretation/comparison, but publishes only newly
supported contributions or explicit changed/corrected canonical knowledge. It must
not publish every candidate from complete history again. A correction in new turn
can legitimately update old memory; coverage of the old statement does not suppress
that new correction. Context checkpoints may be rebuilt without re-ingestion.
Publication+contribution marker+coverage transaction makes duplicate jobs safe.

Prior ingestion backfill: map identical completed ingestion fingerprint+contract
to reviewed snapshot/source set; don't assume all existing history was fully covered
because current reviewer truncated input/candidates. Record legacy coverage unknown
where source window accounting absent. Controlled catch-up may review missing ranges
with canonical comparison/contribution dedupe; owner-aware scope/budget/deletion
policy needed. Do not mark entire old session complete from presence of a summary.
Keep compatibility reviewer_contract versions; re-review on contract change is an
explicit job, not a side effect of opening history.

## Streams, concurrency and actions

GET list with cursor; GET events before/after cursor; POST resume/select returns
history version/active turn/segment and no learning; POST new turn has idempotency
key and expected history version; POST stop requests server cancellation; GET turn
events after sequence reconnects active response. Names are candidate local APIs.
One running submitted turn per conversation initially; typing a new draft allowed.
Concurrent tab submits require version/lease conflict, not duplicate tools. Session
switch stops displaying prior stream but doesn't falsely report job cancellation.
Show running session indicator and explicit Stop; navigation is not confirmation to
rerun tools. Reconnect replays acknowledged response events only, never executes
stored function calls. Interrupted/unknown writes remain unknown and need existing
recovery policy, not blanket Retry.

Draft text and scroll anchor may be saved per scoped conversation in transient
app state across navigation; no durable model/memory ingestion of unsent draft.
Re-login reauthorizes history. Workspace/logout clears scoped caches, protects
against late replies and cannot expose another user's list/previews.

## Tests, phases and rollback

Before build: current scope/auth/store integration reviewed; source retention and
forgotten-fact policy settled for replay. Prove list/load10times makes zero model/
ingestion/tool calls; resume reviewed session and add fact once; late correction
updates once; zero-memory review gets coverage; >100k legacy session not falsely
fully covered; same ID changed data rejected; concurrent tabs/restart no duplicate
versions/effects; scoped list/shared refs; expired old login can read owned retained
history via NEW authorization without reopening provider. Scroll anchor survives
older-page prepend/session switch; deleted source isn't reconstructed.

Implement after evidence/canonical idempotency and Chat final-turn ports; independent
of unavailable Decisions API. Rollback hides history navigation/continuation,
retains canonical records/evidence, disables new publication consumer safely. Never
roll back coverage in a way that republishes already accepted contributions.
## October7 historical coverage boundary

DA-R08 audit procedure and eligibility classes are owned by the decision-learning
plan. This history module exposes authorized original evidence and truthful legacy
coverage; it does not guess missing original decisions or replay tools. A resumed
segment can correct older outcomes; procedural contribution identity and invalidation
must follow cited sources rather than count the same session again. Before any
historical review publication, retained-source and forget/replay policy must be
settled. Reading history alone does not trigger inference, learning or activation.
