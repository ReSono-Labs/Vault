# Indexed pgvector storage and embedding migration

Current document set: [authority map](2026-10-07-live-memory-document-authority.md).
This plan owns its design concern only; original grounding controls requirements,
register controls build status, and historical reviews/manifests are not work orders.

Revision: LMD-STORAGE-r1. Explicit Phase 01 schema proposal; not applied DDL.
The bounded [C02 contract](../contracts/2026-10-07-LMD-C02-indexed-query.md)
owns exact implemented SQL/index subset and its isolated verification. Remaining
epoch/maintenance/cutover proposals below are not delivered by that subset.
[C13A guard](../reviews/2026-10-07-LMD-C13A-build-evidence.md) subsequently fixes
canonical content-check/upsert atomicity and internal producer snapshot versions
using existing row/authority locks. This is not metadata epochs or maintenance.
Authority: grounding r11 R06/R07/R28/R31/R33. Existing store inventory:
[review](../research/2026-10-05-current-memory-implementation-review.md).
Module/wiring authority: [modular integration](2026-10-05-modular-codebase-integration-plan.md).

## What is migrating

Vault already uses PostgreSQL and stores an unconstrained `embedding vector`
alongside vector_json. Preserve records, canonical keys, versions, evidence,
transcripts, summaries, ingestion identities and pending actions. Upgrade retrieval
from Python scans to SQL HNSW. Do not export facts into a new VoiceMem store or
rename all tables. Keep `text-embedding-3-small` / 1536 initially; local embedding
is a separate measured option, not an implicit donor dependency.

The embedding model computes vectors, not database destinations. Keep its scoped
credential factory. Point the persistence/search adapters at the existing database
connection and canonical embedding table; do not give the embedding model a DB URL.
Query embedding and stored embedding must use identical provider/model/dimensions
and preprocessing identity. Changed identity requires explicit re-embedding.

## Proposed schema delta and ownership

All tables are under `vault_private`. Existing IDs are text; scoped FKs follow
existing local user/workspace conventions. All owned rows have timestamps and
bounded JSON validation in application contracts. Additive design first:

| Object | Proposed fields / key / constraints | Purpose |
|---|---|---|
| Existing `vault_memory_embeddings` | Preserve current memory_id PK/FK, provider, model, dimensions, embedding, vector_json, content_fingerprint. Add `embedding_contract_version integer NOT NULL DEFAULT 1` only if preprocessing differs; do not add by habit | Continue one current vector per canonical memory; no duplicate vector authority |
| Existing `vault_memory_records` | Add `retrieval_epoch bigint NOT NULL DEFAULT 1` with positive check; increment on content, lifecycle, visibility, confidence/sensitivity/authority changes affecting retrieval | Prepared validity despite metadata updates without content version |
| `vault_memory_scope_epochs` | Shared workspace/private-user change counters, FK erasure plus tombstone cleanup; no memory payload | C13B current-corpus validation catches additions/deletions and empty-result changes without a full corpus scan; [exact reviewed delta](../contracts/2026-10-07-LMD-C13B-retrieval-state.md) |
| Existing records lexical index | Expression GIN index on `to_tsvector('simple', content_text)`; query same expression; retain exact/LIKE fallback | Deterministic broad lexical candidates without assuming English stemming or multilingual quality |
| HNSW expression index | `(embedding::vector(1536)) vector_cosine_ops`, partial WHERE provider='openai' AND model='text-embedding-3-small' AND dimensions=1536 | Index existing unconstrained vector only for compatible rows |
| `vault_memory_search_hints` (conditional donor benefit) | memory_id FK CASCADE, retrieval_epoch, extractor_version, entities_json, slots_json, hint_fingerprint, status, updated_at; PK memory_id | Rebuildable factual hints, never canonical facts or security filters |
| `vault_feature_preferences` | user_id FK CASCADE, workspace_id FK CASCADE, preference_key, value_json, epoch positive, updated_at; PK(scope,key) | Candidate persistent Live Memory setting; exact scope/default remain owner-reserved |
| `vault_memory_reindex_jobs` | job_id PK, scoped user/workspace, target provider/model/dimensions/contract, cursor, status queued/running/failed/completed, lease_until, attempts, counts, error_code, timestamps; unique active target/scope contract | Resumable maintenance with bounded batches; no per-partial backfill |

Do not create hints table unless donor experiment proves need. For one current
model retain one-row-per-memory semantics. If later online dual-model migration
is required, review a separate versioned embedding table and active-model pointer;
current schema cannot hold two models simultaneously. Do not overwrite vectors
with incompatible dimensions and claim rollback works.

Candidate SQL shape (binding parameters supplied by service, not interpolated):

```sql
CREATE INDEX CONCURRENTLY ix_vault_memory_embedding_hnsw_1536
ON vault_private.vault_memory_embeddings
USING hnsw ((embedding::vector(1536)) vector_cosine_ops)
WHERE provider='openai' AND model='text-embedding-3-small' AND dimensions=1536;

SELECT m.*, e.embedding::vector(1536) <=> %(query_vector)s::vector(1536) AS distance
FROM vault_private.vault_memory_embeddings e
JOIN vault_private.vault_memory_records m ON m.memory_id=e.memory_id
WHERE e.provider='openai' AND e.model='text-embedding-3-small'
  AND e.dimensions=1536
  AND m.workspace_id=%(workspace_id)s
  AND (m.visibility='workspace' OR m.user_id=%(user_id)s)
  AND m.lifecycle_status='active'
ORDER BY e.embedding::vector(1536) <=> %(query_vector)s::vector(1536)
LIMIT %(candidate_limit)s;
```

This is a candidate shape, not proof of index execution. Membership is validated
before query; additional sensitivity/domain/type eligibility follows the existing
caller policy. Scoped predicates must be in SQL, not a Python post-filter over
leaked rows. Canonical content fingerprint/epoch must match embedding write
snapshot; reject stale vectors. Bind model identity safely using a reviewed
fixed query per supported index, not arbitrary client expression SQL.

[pgvector primary documentation](https://github.com/pgvector/pgvector) describes
expression/partial HNSW indexes, dimension limits and approximate filtering.
Inspect installed extension/version and EXPLAIN on representative scoped data;
no fixed ANN recall promise. Use compatible iterative scans where installed
version supports them, measured oversampling/widening, then bounded scoped exact
SQL fallback when required. Small datasets may correctly use exact SQL rather
than HNSW; representative production-scale plan must demonstrate HNSW. Hybrid
rank fusion/rerank remains a separate query policy, not a schema invariant.

C02 fixed index/query compatibility additionally checks actual vector_dims=1536
and nonzero norm; migration refuses invalid matching rows. Semantic reads require
the stored content fingerprint to equal SHA256 of current canonical content.
Query/model/vector validation does not invent another embedding provider. Legacy
LIKE fallback is reused with its existing timeout behavior; new SQL statements
use injected SET LOCAL timeouts, not a claim of an overall request deadline.

## Migration and cutover sequence

1. Isolated migration contract: read installed schema, extension version, row
   counts/model/dimensions, nulls/nonfinite/malformed vectors, content mismatch,
   active/scoped visibility. Do not print contents/secrets. Establish representative
   scale and disk/memory headroom; pin compatible pgvector image/version.
2. Take consistent backup and prove restoration into isolated DB. Preserve source
   IDs, evidence and all canonical uniqueness. Existing destructive DB fixture
   must never point at the running Vault database.
3. Add epoch/update hooks and required additive tables/indexes through owned
   migration runner. Concurrent index build runs outside transaction block;
   detect invalid index and resume/rebuild. Existing startup ensure_schema remains
   fast; no unbounded backfill/index build during startup requests.
4. Validate existing vector rows. Reuse compatible valid vectors; re-embed only
   missing/stale/invalid ones with scoped credential and bounded batches. Record
   job cursor and failures, current memory snapshot/fingerprint; before upsert
   compare epoch/fingerprint so an old job cannot overwrite a correction. Delete
   during work wins; no resurrection. Keep canonical facts on embedding failure.
5. ANALYZE and shadow new SQL lookup on identical authorized queries. Compare
   exact scoped SQL top-k, lexical fallback, old results, evidence payload and
   final-answer outcomes. Measure recall, query/embedding timing, filtered underfill,
   query plan/buffer use and operator resource impact.
6. Route `MemoryService` through injected search adapter; same contract serves
   normal lookup, external adapters and plugin callers. Live Off never routes
   normal search away. Move repair/backfill from interactive lookup to maintenance
   under this reviewed change, not silently through speculative adapter.
7. Enable new search via operator flag only after evidence; monitor errors,
   fallback and p95. Keep legacy path rollback during validation. Do not drop
   vector_json/old code in the additive cutover. Cleanup is a later reviewed task.

## Embedding and model wiring

Existing `ScopedOpenAIEmbeddingFactory` in composition remains provider authority.
Analysis publication reconciles candidate → gets current accepted record → embeds
its current content → fingerprint/epoch-checked upsert into existing table. Search
embeds query → validates finite length1536 → SQL distance candidates → canonical
payload/evidence. Live scheduler coalesces revisions before invoking factory.
Credential failure yields truthful lexical/final-model fallback, never synthetic
vectors. Add deadline/cancellation adapter without assuming current30s timeout is
suitable for live retrieval. Bound input by actual embedding model token capacity;
never silently cut a user's final query to fit a character heuristic.

Cache query vectors only under scoped provider/model/preprocessing identity and
input fingerprint, TTL/size limits; no raw draft persistence. Memory-derived
caches include retrieval_epoch. Content update removes old embedding as today;
maintenance restores it. Metadata/lifecycle/scope updates invalidate prepared
results even when embedding remains mathematically reusable.

## Evidence and reversal

Test migration repeat/resume, invalid concurrent index, missing vector, correction
race, delete race, wrong model/dimensions, cross-user/private/shared scoping,
ANN underfill, embedding outage and resource saturation. Restore backup in an
isolated DB and switch adapter back without changing canonical knowledge. Passing
unit mocks is insufficient: isolated PostgreSQL integration and actual EXPLAIN/
recall evidence are required. No migration, DB probe or provider call performed
in this planning phase. Numeric quality/latency budgets need owner acceptance.


## Approved local embedding replacement — 2026-10-09

The owner explicitly selected Google EmbeddingGemma 300M after real embedding
requests with the same shared ChatGPT OAuth credential returned
`credit_balance_exhausted`. The earlier OpenAI/1536 SQL and provider choice above
are historical. Current package composition uses Ollama `embeddinggemma:300m`,
provider `ollama`, 768 dimensions for factual memory and procedural examples.
Existing canonical tables, authority checks, forgetting and learning contracts
remain owners. Additive HNSW indexes use new `_768` names; old model vectors
never participate in local-model searches. Existing factual maintenance replaces
stale model vectors, two memories per batch; retained procedural generations
require the existing rebuild flow, not mixed-model activation.

The CPU-only Ollama runtime and pinned model blobs ship in the Docker image.
No provider credential or download is needed at runtime. Retrieval uses Google's
query prefix; stored facts/examples use the document prefix. Inputs above the
2048-token model context fail rather than silently truncating. Inference uses two
CPU threads, batch 32, one request at a time, lowered process priority, one loaded
model and a five-minute idle unload. The existing live preparation timeout remains
bounded. Model identity/dimensions and original-source publication checks remain
mandatory; memory meaning is never fabricated when inference fails.


### Embedding context/batch correction — 2026-10-09

Ollama embeddings require physical batch size at least the input token count.
The initial batch-32 setting was incorrect; the current batch is 2048 for the
2048-token context. This does not increase the two inference threads. Inputs
up to 32768 characters are tokenized by Ollama with `truncate=false`; only its
explicit token-context overflow triggers recursive source-preserving windows.
All windows must succeed within a shared deadline and 31-request ceiling. Their
token-weighted normalized mean occupies the existing one-vector record; no new
store or learning job is introduced. Input contents never enter error logs.
The lock wait and inference share one deadline, rather than doubling the budget.
Local live preparation may use the existing adapter's 30-second bound for long
inputs; the stream's finalization deadline still prevents delaying Chat for it.

The shared procedural reviewer now renews its existing owner/attempt-fenced lease
while model work is pending, rechecking canonical source and local authority on
each renewal and before completion. Renewal is bounded to ten minutes and writes
no analysis output. Revocation, changed source, reclaimed ownership or budget
exhaustion prevent publication. No new reviewer, scheduler or capture path.


The memory-limited verification refined the physical batch to **256**. A 2048
batch exhausted a 1.5 GB container's memory on long windows; smaller windows now
respond to explicit physical-batch/token-context overflow using the same complete
source-preserving split. Each accepted window is verified at no more than 256
model-tokenized tokens, including the prompt prefix. This supersedes the initial
2048-batch correction above, while retaining the 2048 model context, two threads,
shared request deadline and no truncation.
