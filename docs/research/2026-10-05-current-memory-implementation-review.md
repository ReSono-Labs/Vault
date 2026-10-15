# Current Vault memory implementation and VoiceMem overlap

Date: 2026-10-05. Revision: LMD-CURRENT-MEMORY-REVIEW-r1.
Branch: `feature/live-memory-decisions`. Runtime baseline:
`ea39a6f9da89a2999c4f7e14f686428d2088f480`; documentation edits are uncommitted.
Type: internal source review, not owner acceptance or live deployment proof.
Authority: change grounding r7. This evidence record owns the current-memory
inventory and integration findings; feature plans link here instead of copying
changeable findings. No runtime, database, dependency or provider changes made.

## Result and role correction

Retain Vault's memory agent/reviewer, embedding model, canonical PostgreSQL
store, analysis/reconciliation pipeline and normal retrieval. Investigate only
VoiceMem's live-input scheduling and factual retrieval organization as separate
components over that authority. Do not import a second full memory system.
The owner explicitly excludes the separate Background Agent from this work.

Owner calls the autonomous session-analysis component the **memory agent**.
Its implementation is `OpenAIMemoryReviewer` plus `MemoryPipeline` and
`VoiceMemoryLearning`, not the separate Background goal executor. Existing
source calls review a capability and does not register another system identity.
The shared SDK helper physically lives under `background_agent/sdk_runner.py`
and credential lookup is named `background_access`; those names do not mean
Background Agent runs the memory workflow. They are existing dependencies,
not permission to change Background Agent behavior or create a new identity.

## Actual end-to-end path

1. Browser Voice captures final user/assistant transcripts. Provider events
   pass through the authenticated Voice events route into
   `VoiceMemoryLearning.capture` → `VoiceProviderEventCapture`. Accepted provider
   events append scoped transcript entries; duplicate events are not new input.
2. Actual Voice tool calls append bounded, recursively redacted result evidence
   through `VoiceToolEvidenceObserver`, including error status. Explicit remember
   requests append a user transcript marker rather than bypass analysis.
3. Browser `closeVoice` waits for pending transcript writes with
   `Promise.allSettled`, then requests close. The close API closes the session
   and directly calls `VoiceMemoryLearning.finalize`; an explicit finalize API
   uses the same path. Empty sessions skip analysis.
4. `MemoryPipeline` reads stored entries in entry-index order, fingerprints the
   history, checks completed ingestion and formats source-indexed evidence.
5. The memory agent invokes the selected scoped text provider/model and returns
   a structured session summary and cited durable memory candidates. It is
   autonomous; no manual approval is required for every ordinary candidate.
6. Code validates contract v2, taxonomy, bounds and source citations. Repository
   reconciliation performs canonical matching, writes versions/evidence and
   handles confirmation/correction/conflict. Active accepted records are embedded.
7. Real vectors and content fingerprints persist alongside canonical records.
   Session summaries and ingestion completion persist separately.
8. Later Voice startup injects bounded profile memories and the previous
   summary; normal `memory_lookup` performs authorized lexical/semantic search.
   External adapters/plugins use the same canonical service.

Review on close is synchronous in the inspected API, although it performs
non-interactive memory work. It is not shown as a durable job queued to the
separate Background Agent. Preserve autonomous analysis; do not reinterpret
this implementation as a Background goal.

## Storage and semantics to preserve

| Concern | Current implementation |
|---|---|
| Canonical records | `memory/schema.py` / `repository.py`: PostgreSQL `vault_private.vault_memory_records`, stable memory ID/key, subject, owner/workspace, content, visibility and current version |
| Taxonomy | Domains: identity, personal, relationship, environment, project, device, platform. Types: fact, preference, decision, episode, constraint, correction |
| Evidence authority | user_asserted, tool_verified, model_derived; confidence low/medium/high; sensitivity normal/sensitive |
| Reconciliation | create, confirm, correct, conflict; active/conflicted/superseded schema states. Conflicted records excluded from normal search |
| Canonical key | Private uniqueness includes user; shared uniqueness is workspace-wide. Advisory transaction lock serializes a canonical key |
| Version/provenance | Record versions, actor, source session and reviewer contract; evidence references transcript entries and excerpts |
| Transcript/history | Ordered user/assistant/tool records; summaries keyed by contract and transcript fingerprint; ingestion status running/completed/failed |
| Embeddings | Dedicated table with real pgvector column plus JSON vector, provider/model/dimensions and content fingerprint; record content changes delete stale embeddings |
| Scope | Every repository entry checks active user/workspace membership; result predicates permit current user's private and current workspace shared records |
| Corrections/forgetting | Voice prepares an exact action and requires a later same-session user entry before consuming it. Forget deletes record and cascades versions/evidence/embedding. Original transcript history is separate |
| External writes | External integration operations have separately enabled permissions; proposals use canonical review. Explicitly authorized external correct/forget operations have their own path, not Voice's two-turn confirmation path |
| Deletion | Local-user deletion removes owned memory/transcripts/summaries/ingestions and associated workspace state; derived live caches/index metadata must follow deletion/revocation |

Do not reinterpret knowledge type `decision` as an executable learned rule.
Do not drop private/workspace or source-authority distinctions to fit VoiceMem.
Do not silently keep deleted records in a derived retrieval index.

## Memory agent: actual analysis contract

Sources: `memory/openai_reviewer.py`, `contracts.py`, `pipeline.py`.
The model instructions prioritize explicit user statements and verified tools,
require indexed citations, reject unsupported inference and transient/tool-owned
state, and allow an empty candidate list. Parser rejects uncited candidates,
filters listed secret markers and normalizes stable keys. Model-created session
candidates are private, attributed to the authenticated user.

Important current behavior:

- The input is session transcript evidence, not just a session summary.
- Reviewer currently receives no separate retrieved canonical-memory comparison
  set in this call; reconciliation occurs afterward by canonical key.
- `comparedMemoryId`, `validFrom` and `validTo` exist in model output but are
  not mapped into the persisted `MemoryCandidate`. Do not claim a complete
  temporal-validity or semantic merge system from these output field names.
- Default reasoning effort is medium; the memory reviewer uses selected provider
  access/model, not a fixed assumed reviewer model. It requests no conversation
  reasoning observation sink. Its own reasoning is not conversation reasoning.
- Maximum transcript sent is currently 100,000 characters; candidates are
  sliced to 32, summary bounded to 20,000 and content to 4,096 characters.
  These are real truncation/coverage boundaries, not proof of complete history.

**Owner-required change:** replace silent transcript truncation with complete
session analysis. This does not mean infinite model context. A separate reviewed
analysis coordinator must account for every retained final entry, split oversized
entries safely, review bounded windows with stable citations, consolidate across
windows, and preserve cross-window corrections, tool outcomes and ordering.
Track processed ranges/fingerprints, failures and retries; mark the session
complete only when all required ranges and consolidation succeed. The 32-candidate
cap also needs coverage/pagination rather than silently discarding durable facts.
Do not merely increase the character constant or truncate the final consolidation
input again. Keep existing taxonomy/validation/reconciliation as the authority.

## Embedding pipeline

Sources: `memory/openai_embeddings.py`, `service.py`, `composition.py`.
Default real provider is OpenAI `text-embedding-3-small`, 1,536 dimensions.
Scoped credential resolution supplies access; vector validation rejects wrong
dimensions and non-finite values. HTTP timeout is currently 30 seconds.
Finalization embeds active accepted records and tolerates embedding failure so
canonical knowledge still persists. Startup launches a bounded vector backfill
thread (up to 1,000 per storage identity); ordinary factory-backed search also
repairs up to 256 missing vectors before searching.

The new live path must not repeat that repair on each partial input. Separate
maintenance from interactive queries while preserving normal retrieval behavior
until its own reviewed indexed-search contract changes it. Local embedding is
not selected by adopting VoiceMem's published measurements; changing model or
dimensions needs explicit compatibility/reindex handling. Current embedding
schema stores one vector row per memory, not simultaneous multi-model vectors.

## Normal retrieval today and required HNSW change

Sources: `memory/retrieval.py`, `repository.py`, `voice/context.py`.
Startup takes eight active normal-sensitivity medium/high-confidence profile
memories with domain priority and recency, plus the previous summary (up to
4,096 characters in instructions). On-demand lookup returns eight by default,
maximum 25. Lexical query extracts up to eight ASCII terms, matches content via
SQL LIKE and orders by recency. Exact score enhancement is applied only among
those lexical hits. This is not multilingual full-text or entity-index search.

Semantic retrieval generates the query vector, fetches scoped stored vectors
from JSON, computes cosine in Python and reads individual hit records. Lexical
and semantic scores are merged by maximum with method labels; current similarity
floor is 0.20. Failure retains lexical results. No inspected HNSW index or SQL
nearest-neighbor query exists. True vectors are present; index execution is not.

**Owner-required change:** add index-compatible pgvector HNSW search in PostgreSQL,
with authorization/lifecycle/model/dimension predicates and validated scoped
recall. Preserve lexical/exact fallback, version/evidence payloads and deletion.
Add a separate query component with narrow repository/composition adapters;
do not put live logic into existing memory files. Index creation alone is
insufficient. Verify representative SQL plans and recall against exact search.
The live Off switch must preserve normal retrieval and autonomous learning.

## Reliability findings relevant to integration

These are source concerns, not reproduced production incidents or runtime fixes:

- Review occurs before the ingestion claim; concurrent finalizations may spend
  duplicate model work. Claim, summary and memory writes span transactions.
  A post-claim failure can leave partial state. The losing path accepts an
  existing summary without checking completed status. Durable recovery needs
  review before adding a second learning publisher.
- Provider-event acceptance and transcript append are separate operations.
  Recovery of accepted-event/failed-transcript-write is not established here.
- Browser transcript indexes and server `append_transcript_next` share the
  session index space; server appends have an advisory lock but browser uses
  its own counter. Concurrent tool evidence/final transcripts need an ordering
  and collision test before claiming the full history is captured losslessly.
- `Promise.allSettled` waits for writes but does not guarantee all succeeded.
  Closing must not equate drained promises with complete captured history.
- Confirmed-action consumption and application are separate transactions;
  interrupted apply/retry behavior needs a bounded contract if touched.
- Forgetting a record does not remove its source transcript automatically;
  future derived rebuilds need deletion policy to prevent resurrection.
- Metadata/confidence changes can occur without a content-version increment;
  prepared-result validity cannot rely only on content version.

Keep these visible for planning and tests. They are not grounds to replace the
existing canonical system or silently expand this review into an audit of the
separate Background Agent.

## VoiceMem overlap and integration disposition

Inspected VoiceMem commit: `6cacb3c1e7fca2679f3bf95451f6b480efd9a783`.
Detailed research: [live retrieval review](2026-10-05-live-memory-retrieval-research.md).

| VoiceMem responsibility | Vault overlap / disposition |
|---|---|
| Partial transcript ingestion and speculative search | Missing in Vault; candidate pattern behind independent live-input adapter |
| Slot/entity candidate organization | Potential retrieval enhancement; derive rebuildable metadata from existing records, never authoritative hard filters without recall fallback |
| Query embedding and rank | Existing embeddings and canonical vectors; adapt retrieval to selected HNSW store rather than add another vector authority |
| Mem0-backed store / graph metadata | Inspected backend uses local Qdrant and SQLite history/graph paths; not the same storage/schema or workspace policy. Exclude as replacement |
| Fact extraction/ingestion/consolidation | Existing memory agent already owns this; exclude VoiceMem ingestion from normal learning |
| Right-brain persona/emotion/audio | Outside requested scope; exclude emotion inference, voiceprints, new ASR and audio-memory store |
| Reply models and full voice loop | Exclude; OpenAI live transcription is selected, existing conversation authority retained |
| Final result reuse | `_confirm` may pair changed final text with old results; must replace with final-input validation |
| Task cancellation and empty partial | Cancellation of thread await does not prove worker stopped; empty text ignored and older memory can linger. Require revision/epoch rejection and bounded workers |

Proposed wiring: OpenAI live transcript or text edit → independent revision
controller → optional factual/entity interpretation + authorized indexed search
→ revision-bound prepared context → final validator → existing conversation
model/tool authority. Completed final evidence → existing memory agent/analysis
coordinator → canonical reconciliation → existing embeddings. Live components
read memory; they do not write unsent drafts into durable learning.

Store enhancement remains conditional on measurable benefit. No evidence from
this review establishes that VoiceMem's full store improves Vault's citations,
workspace authority or lifecycle. Component dependency direction must prevent
canonical ingestion importing the optional live engine. Switch Off invalidates
partial work/caches immediately while final retrieval/analysis remain available.

## Supplied benchmark image: interpretation and limits

Owner-supplied image shows LoCoMo 91.2%, PersonaMem 69.44%, K=5, 302 mean memory
tokens and 134 ms latency. These are reported benchmark claims, not a guarantee
of near-perfect retrieval or end-of-speech to useful audio in Vault.

The inspected [paper](https://arxiv.org/html/2608.26005v1) reports 91.2 and 134 ms
but describes 430 memory tokens at one operating point. Image-versus-paper
configuration/version differences remain unresolved; do not silently choose
302 as our token budget. PersonaMem/persona behavior is excluded from this
retrieval-only integration and cannot be counted as an inherited gain.

Inspected `evaluation/run.py` ingests conversations then searches **complete
questions**, times `vm.search`, generates an answer and scores it with a model.
It estimates memory tokens by text length divided by two. That harness does not
validate evolving prefixes, late corrections, cross-workspace isolation or
end-to-end voice timing. A retrieval-only adaptation over existing Vault facts
cannot claim results from VoiceMem's own ingestion/index-building pipeline.
Require the same corpus/labels and paired Live On/Off tests, plus final-answer
quality and actual played-audio timing. No paid benchmark was executed.

## Verification and completeness boundary

Current pass: `.venv/bin/python -m pytest -q` for memory retrieval, contracts,
reviewer, evidence, adapter-package contract, voice schema and scoped catalog:
**25 passed in 1.10 s**. Earlier frontend baseline: **11 passed**. PostgreSQL
integration tests were inspected, not run: their fixture drops `vault_private`
and requires an isolated test database. No production DB inspection, live
provider calls, migration or deployment occurred.

Inventory inspected every file under `app/vault_runtime/memory/`, Voice
capture/context/evidence/tool and API close/finalize paths, composition,
credential/model selection, external-memory service/repository/schema,
plugin-memory boundary, local-user erasure and relevant tests. Separate
Background Agent was inspected only to resolve mistaken role attribution;
it is not an implementation owner or feature dependency for this work.

This covers the source implementation, not proof that the installed service
has identical data/configuration or that every capture/failure edge works live.
Required next planning inputs: complete-session coverage/retry, indexed lookup,
VoiceMem subset experiment, revision/final validation, and independent removal.
Phase 01 remains in progress; no frozen reviewed plan or READY build contract.
