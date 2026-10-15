# Feature 01 — indexed retrieval/storage migration validation

2026-10-07. Internal source-to-plan validation, not implementation/owner acceptance.
Read the COMPLETE 2026-10-05-pgvector-storage-and-embedding-plan.md r1 before
disposition, plus grounding R07/R31/R33 and D18. Do not substitute contract status
or an absence-of-name search for tracing the actual retrieval execution path.

## Verdict

The planned migration from Python-scored retrieval to PostgreSQL/pgvector HNSW
retrieval is NOT IMPLEMENTED in this working tree. Existing storage/embedding
components and a replaceable legacy search boundary ARE IMPLEMENTED and must
be reused. This verdict does not claim deployed database rows/indexes were inspected.

Runtime trace: composition.py creates MemoryRepository and ensures its schema,
creates ScopedOpenAIEmbeddingFactory, creates MemoryService WITHOUT a search_backend.
MemoryService defaults to LegacyMemorySearchBackend -> MemoryRetriever.retrieve ->
MemoryRepository.embeddings_for SELECTs vector_json -> Python cosine_similarity.
Thus actual current query path positively demonstrates Python scanning, not HNSW.
No alternate indexed backend is registered in composition or present in memory_search.

## Every substantive storage-plan deliverable

| Planned obligation | Actual code/test evidence | Verdict and precise delta |
|---|---|---|
| Preserve canonical records, keys, taxonomy, versions, evidence/transcripts/summaries/ingestion/actions | memory/schema.py and repository.py implement those owners; no new canonical replacement in built slices | DONE existing foundation; preserve, do not rebuild |
| Keep existing embedding provider/model/dimensions initially | openai_embeddings.py constants text-embedding-3-small/1536; scoped factory in composition | DONE provider wiring; no live entitlement/provider call tested here |
| Existing vector representation and fingerprint persistence | schema declares embedding vector plus vector_json; store_embedding writes both with content fingerprint | IMPLEMENTED source storage; not proof of applied production schema/data or indexed retrieval |
| SQL HNSW partial expression index over compatible1536 rows | No HNSW/vector_cosine_ops/index statement in memory schema or runtime migrations | NOT DONE; additive reviewed index/migration required |
| PostgreSQL nearest-neighbor distance query | embeddings_for loads JSON; retrieve loops and computes cosine in Python; no memory <=> query | NOT DONE; new scoped indexed-query adapter over existing table |
| Indexed lexical expression matching planned query | lexical_memories uses terms/LIKE; no memory to_tsvector GIN/query. Other product areas' text indexes do not satisfy this | NOT DONE; extend memory lexical query/index while preserving fallback |
| Active membership/private/shared/lifecycle filters | repository _require_membership/_scope_sql, current embeddings_for predicates | DONE existing enforcement; must be retained INSIDE new SQL and retested |
| Provider/model/dimension compatibility of indexed candidates | current query filters model only when supplied; Python checks vector length | PARTIAL; SQL index predicates/current embedding identity consistency missing |
| Retrieval epoch and metadata invalidation | MemoryRecord/schema have current_version but no retrieval_epoch/hook | NOT DONE; precise epoch/version solution must be contracted, not added blindly |
| Remove stale vectors on content change | reconcile_memory DELETE embeddings on changed content; integration test_content_change_removes_stale_embedding | DONE existing cleanup; reuse |
| Maintenance rejects stale snapshot/correction/deletion writes | store_embedding verifies current content before write; ensure_vectors regenerates missing | PARTIAL; new epoch-safe scheduling and metadata-race guarantees not present |
| Durable bounded reindex job/cursor/lease/resume | composition daemon backfill and service.ensure_vectors exist; no vault_memory_reindex_jobs/worker | NOT DONE as planned; reuse generator/upsert, add only required orchestration |
| Move repairs off interactive indexed path | MemoryService calls ensure_vectors when backend flag true; actual default legacy flag true | PARTIAL seam built C01; NOT cut over. New indexed backend/maintenance not wired |
| Isolated extension/schema/model/data/resource preflight | no C02/C13 build-evidence outcome; old test fixtures define safe DB but not migration inventory | NOT VERIFIED; required before applying migration |
| Consistent migration backup and isolated restore | no indexed-migration restore evidence found | NOT VERIFIED; test harness/schema tests are not backup/restore proof |
| Concurrent-index invalid/resume handling outside transaction | no concurrent memory index migration runner | NOT DONE; reviewed migration duty |
| ANN filtered underfill/widening/exact fallback | no ANN query exists; lexical fallback is existing behavior only | NOT DONE; version-aware bounded ANN/exact strategy and tests |
| Exact-versus-ANN scoped recall/EXPLAIN/ANALYZE/shadow | no indexed search runtime/tests or representative query-plan/recall result | NOT DONE; mocks cannot satisfy |
| New search backend across normal/external/plugin callers | built protocol/legacy adapter and caller tests exist; composition remains legacy | PARTIAL foundation only; indexed adapter/current caller wiring still missing |
| Operator cutover/rollback and monitored indexed errors/latency | no indexed flag or active indexed adapter | NOT DONE; preserve legacy rollback and canonical data |
| Query-vector cache identity/TTL/bounds/deadline-cancel | current embedder 30s HTTP timeout; no scoped live query cache/controller | NOT DONE; bounded live/adapter work, not a second embedding model |
| Token-safe input rather than silent shortening | embedder rejects >16384 characters; no model-token-budget adapter | PARTIAL explicit reject; reviewed capacity/token-bound handling still required |
| Conditional factual hints/embedding contract-version change/dual-model storage | storage plan explicitly says conditional, do not add by habit | NOT unconditional missing tasks; only build if independently justified |
| Full scope/model/deletion/race/outage/restore/resource tests | baseline tests cover some scoping/deletion/cosine/caller parity, not indexed migration | PARTIAL baseline tests; planned actual SQL/index suite absent |

## Tests and evidence actually checked

Read test_memory_retrieval.py: it validates Python cosine, not database retrieval.
Read memory PostgreSQL integration tests including
test_pipeline_persists_real_pgvector_for_scoped_memory: verifies vector_dims for a
2-dimensional fake embedder, not1536 HNSW, ANN recall or provider availability.
Read C01 build evidence: explicitly records PostgreSQL/HNSW unperformed.
Executed .venv/bin/python -m pytest -q tests/unit/test_memory_search_boundary.py
tests/unit/test_memory_search_boundary_callers.py tests/unit/test_memory_retrieval.py
tests/unit/test_memory_contracts.py tests/unit/test_memory_evidence.py
tests/unit/test_memory_adapter_package_contract.py: 38 PASS in0.32s.
No integration fixture, production DB or paid provider executed this audit.
Runtime-wide index/query searches also checked tests/scripts/evidence: unrelated
Mail/personal-data full-text indexes do not count toward memory migration.

## Reuse/new-build split and no-duplication conclusion

Reuse canonical schema/repository, scoped embedder, content verification/cleanup,
MemoryService and built MemorySearchBackend, existing caller contracts. Missing
build is indexed SQL/query+compatible index/migration, bounded maintenance/cutover
and required validation. Do not implement another embedding store/model or call
the existing Python path the required completed vector retrieval. C01 is completed
foundation, not evidence that C02/C13 migration happened. No runtime edits made.
