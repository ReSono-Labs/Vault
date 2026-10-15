# Live Memory runtime and indexed retrieval

October8 C06F mounts supported OpenAI API-key Voice into the SAME Chat preparation
host through actual Voice source adapters. No second VoiceMem loop/search engine,
worker budget or synthetic Chat rows. Dedicated gpt-live-transcribe shares existing
microphone media with null sidecar turn detection and commits on conversation VAD
notifications. Conversational auto-response is disabled on this supported path
until final capture/context validation; preparation failure uses canonical final
lookup. OAuth entitlement and actual microphone/provider behavior remain unverified.
See [C06F](../contracts/2026-10-08-LMD-C06F-voice-live-host.md). Older unmounted
statements below are historical, not duplicate build tasks.

Current document set: [authority map](2026-10-07-live-memory-document-authority.md).
This plan owns its design concern only; original grounding controls requirements,
register controls build status, and historical reviews/manifests are not work orders.

2026-10-07 applicability: [Decisions/evidence grounding amendment](2026-10-07-decisions-api-evidence-grounding.md)
requires Phase01 revalidation of this plan's applicable draft, final-turn, causal
evidence, history coverage, evaluation and provider assumptions. GPT-Live is not
in scope. This notice is not a replacement design or renewed review approval.

Revision: LMD-LIVE-PLAN-r2. Phase 01 candidate, not reviewed or build-ready.
Bounded C05A/C06A/r2 extraction is now covered by its own
[actual contract](../contracts/2026-10-07-LMD-C05A-C06A-live-component.md) and
[component evidence](../reviews/2026-10-07-LMD-C05A-C06A-build-evidence.md).
Its actual VoiceMemStream/ParallelPreparation types precede proposed interfaces
below. C13B now supplies actual canonical memory epochs/state snapshots and C07A
supplies scoped preference/current-session authority. No full-plan readiness.
C06B now combines canonical session/conversation/preference/memory freshness and
scoped stream invalidation; required external source/procedural guards remain.
No complete relevance guard or live adoption claimed;
comparative C05 quality and production C06/C13 gates remain. Earlier statements
about copying during planning do not prohibit this subsequently reviewed build.
Authority: grounding r11 R01–R11/R18/R21/R25–R30. Evidence:
[research](../research/2026-10-05-live-memory-retrieval-research.md).
Ownership and shared delivery fields: [master](2026-10-05-live-memory-delivery-plan.md).

## Component boundary and proposed interfaces

New `live_memory/` owns revisions, preparation scheduling and final validation;
new `memory_search/` owns hybrid retrieval over canonical memory and indexed
read queries. Neither owns ingestion, reconciliation, grants or agent identity.
VoiceMem's external-text/factual narrowing pattern is the research candidate;
actual dependency versus licensed subset versus clean implementation remains
conditional on comparative experiments. Its finalization code is not reusable
unchanged. No installation/scaffold is authorized during planning.

Proposed input: authenticated scope + conversation/utterance ID + transport
item ID + increasing revision + accumulated text + partial/final/abandoned
marker. Server supplies scope; a client-supplied user/workspace is not authority.
Prepared result records exact input fingerprint, context version, memory IDs
and versions, retrieval/model identity, preference epoch and status. Procedural
rule candidates stay separate and reference their own generation/version.

Proposed ports: `revise`, `invalidate`, `prepare`, `finalize`, `cancel`; bounded
`search(query, scope, filters, deadline)` and optional `interpret`/`rerank`.
Interfaces must permit no-op preparation and alternative retrieval providers
without exposing canonical writes. Contracts will freeze signatures and errors.

## Every update versus every search

Controlling latest clarification: [LC-R01–04](2026-10-07-live-recall-context-grounding.md).
One evolving input/context owner feeds recall and decision retrieval in parallel.
Decisions piggyback on returned memory context; no independent draft interpretation
or scheduler. Retain relevant candidates only after current-revision/context and
authority validation; drop invalid ones and restart/widen retrieval as necessary.
This lifecycle continues through the turn, not one speculative classification.
VoiceMem subset review/adaptation remains explicit C05 scope alongside C06 controller.

Every text edit/transcript delta advances validity immediately. Empty text,
entity replacement, scope/session switch and Off revoke previous preparation.
Cheap state changes happen per event. Expensive embedding/search/model work is
coalesced at meaningful chunks/pauses, with a maximum-wait opportunity to prevent
endless debounce starvation. No arbitrary chunk/word-count limit is accepted
as semantic correctness. Tuning is an experiment, not a frozen default.

At most one current job and one coalesced pending revision per utterance is a
proposed starting point, with a per-user/global worker budget. Superseded work
is logically cancelled immediately; underlying threads/provider requests may
continue, so worker accounting persists until actual completion. Late results
are discarded regardless of cancellation success. Drafts are transient and
excluded from learning; operational metrics should avoid raw draft text.

Run lexical/entity lookup and embedding/HNSW retrieval concurrently where
independent. Optional interpretation can use recent conversation context;
returned memory can revise interpretation only for the matching current
revision/context version. Bound reconsideration rather than looping a model
until it likes its own result. Missing/ambiguous entities must not hard-filter
out the correct memory: use a bounded authorized widening path.

Hybrid candidate generation preserves R1 domain/type/lifecycle/evidence and
active membership. Test reciprocal rank fusion against the existing merge;
optional reranking remains replaceable. ANN approximate recall is not logical
certainty. Underfilled results require measured widening/exact fallback, not
an invented no-match. Index/query use compatible dimensions/model/version and
SQL distance order. Existing `ensure_vectors` backfill is excluded from each
interactive query; maintenance handles missing vectors separately.

## Finalization and speed

Send/end-of-turn freezes a separate immutable turn. Prepared context is usable
only if final text/context match and memory, preference and authority versions
remain current. Exact match needs cheap batched validity checks, not a second
embedding/model round trip. A changed final cannot reuse evidence blindly:
revalidate relevance against final meaning or perform current final retrieval.
Cosine closeness is not enough for changed names, negation, amounts or dates.

Short questions and late reversals may have no overlap benefit. If required
memory is not ready, await bounded remaining work or fall back truthfully;
never answer from invalid evidence to hit latency. Measure reuse coverage and
final-path delay; a system that repeatedly needs full searches is a failed
speed hypothesis. Research local embedding as a replaceable experiment only:
changing embedding identity requires reindex/version handling and hardware
measurement. Retain selected Postgres/pgvector direction.

## OpenAI voice adapter

Consume OpenAI live deltas into accumulated revision text. Final replaces
partial text and correlates by item/content identity; out-of-order finals do
not alter another utterance. Keep transcription, endpointing and conversation
response control separate. Selected live transcription requires application
turn commit, so isolate that control in `conversation/voice_adapter` rather
than add state logic to BrowserVoiceApp/provider.py. Do not add VoiceMem ASR.

Disable automatic response creation on the experimental path until final
context validation allows response. Route current tool authority through its
existing owner; no pre-final tool calls. Existing voice path remains the
fallback when live preparation is off/unsupported. Test barge-in, abandoned
turns, final transcript failure and teardown; supported voice summaries are a
separate evidence capability, not fabricated transcript reasoning.

## Live Memory preference — confirmed semantics and owner policy

User-facing label: **Live Memory**. Owner-confirmed Off disables live memory preparation only; normal final-input
retrieval and autonomous memory-agent analysis continue. Partial intent work
that solely supports live memory stops with it. Owner policy BP-R01 confirms
per-user/workspace persistence and an initially On default; see
[build-policy grounding](2026-10-07-live-memory-build-policy-grounding.md).
This resolves the earlier defaultOff proposal, not implementation or quality gates.
Turning Off cancels queued preparation, invalidates caches immediately and
blocks publication of late results. No provider draft processing after Off.
Essential voice transcription may continue for the conversation itself.

## Outcomes and verification

| Outcome | Deliverable / entry | Positive evidence | Negative evidence / reversal |
|---|---|---|---|
| O1 | Bounded comparative retrieval experiment after READY experiment contract | Same final corpus compares baseline, indexed hybrid and VoiceMem-inspired narrowing | Last-word reversal/deletion rejects stale hits; worker count stays bounded; remove experiment artifacts |
| O2 | Isolated indexed search after O1/storage review | Authorized SQL plan and exact-vs-ANN recall; lexical fallback | Cross-user/scope leakage, index underfill, mismatched embedding, missing vectors; route back to existing search |
| O3 | Revision controller and user preference after O1 and interface review | Current results only; Off stops partial work; exact-final fast validation | Empty/IME edits, ABA text, delayed job, preference race, revocation; disable component |
| O5 | OpenAI adapter after O2/O3/O4 and paid test scope/access established | Search begins from speech deltas; final context enters response before output | Continued speech, correction, interruption, unordered final, unavailable provider; restore current voice route |

Stop on an authorization bypass, unresolved final-input semantics, uncontrolled
workers or quality/speed regressions. O1 numeric production gates remain open;
no production enablement until benchmark and owner acceptance.

## VoiceMem adoption plan and specific cut points

Pinned source `xzf-thu/VoiceMem` commit
`6cacb3c1e7fca2679f3bf95451f6b480efd9a783`, Apache-2.0. Recommendation is a
retrieval-only adapted subset over Vault, conditional on paired evaluation.
Do not install/import its full package as a default: root dependencies and
constructors can instantiate excluded Mem0/local store, embedding and voice stack.
Build contract records exact copied files/functions, license/NOTICE attribution,
upstream SHA and local changes. No donor code is copied during planning.

Candidate seams: `stream.py` external text revision/preparation pattern;
`cognitive_graph/local_query_classifier.py` optional entity/slot hints;
`leftbrain/brain.py` candidate retrieval organization. All outputs translate to
Vault SearchPort candidates (canonical IDs/epochs), never donor memory IDs or
repository writes. Existing E5 classifier is a distinct model/dependency; evaluate
its hardware, installation, license and latency separately. Do not mix E5 query
vectors with existing OpenAI stored vectors. Optional classifier maps hints into
canonical domain/type/entity metadata; broad authorized retrieval remains fallback.
If classifier quality does not help, remove it and retain indexed hybrid engine.

Explicitly replace donor `_confirm` reuse of old results for changed final text,
empty-update ignoring, and unbounded underlying threaded speculation. Our revision
controller owns concurrency/cancellation/final validation. Donor timing/evaluation
cannot certify these replacements. Reproduce factual retrieval against our same
canonical corpus so ingestion improvements aren't credited to retrieval-only code.
Full donor memory ingestion, memory_repository/Mem0 backend, Qdrant/SQLite,
right-brain response/persona/voiceprint/audio and built-in ASR are excluded.

Detailed independent ownership: [modular wiring](2026-10-05-modular-codebase-integration-plan.md).
Storage/query/embedding cutover: [pgvector plan](2026-10-05-pgvector-storage-and-embedding-plan.md).
Provider/auth/commit lifecycle: [OpenAI transcription](2026-10-05-openai-live-transcription-and-oauth-plan.md).
## October7 selector/context dependency and final handoff

DA-R04/10: scheduling remains live_memory-owned. For each meaningful revision,
memory search and procedural retrieval may run concurrently; optional selector
waits for required context, not necessarily all retrieval. A new context fingerprint
invalidates dependent selection and coalesces reconsideration within worker budget.
No tool invocation, even read-only, before final input. Preparation may identify a
capability or construct a non-executable plan, not an invocation claim.

Send atomically captures text plus attachment/context identities into a submitted
turn. Later composer edits belong to a new utterance. Reuse requires current
input/context, memory versions, generation/candidate mapping and authority epochs.
If missing or changed, finish required final retrieval/selection within deadline or
use ordinary model/clarification. Record reused/rejected preparation separately;
do not call rejected predictions successful procedures. Raw obsolete drafts remain
transient. IME updates invalidate immediately but expensive analysis waits for
composition end/coalescing. Live Off stops speculation; final-only selection/search
remain optional independent ports. Tests include late memory changing route, rapid
Send, delete/negation, attachment removal, retired generation, missing context,
noncancellable provider work, and no-op adapter. See selector/learning owned plans.
