# C02/r1 — SQL/index grouping implementation evidence

2026-10-07. Bounded internal same-context review, not owner acceptance, production
cutover or independent assurance. Branch feature/live-memory-decisions, HEAD
ea39a6f9da89a2999c4f7e14f686428d2088f480; all work uncommitted, owner changes
preserved. [Contract](../contracts/2026-10-07-LMD-C02-indexed-query.md) and frozen
prebuild source/candidate review govern R01/R06/R07/R26/R31/R33/D18/D19.

## Actual implementation / no duplication

Existing MemoryService.search accepts PgvectorMemorySearchBackend through C01.
Real DB test injects that backend and asserts neither embeddings_for (JSON/Python
scan) nor ensure_vectors (interactive repair) is called. Existing default production
composition STILL selects legacy; production migration/cutover/epochs/maintenance
remain C13. Do not report the entire retrieval migration complete.

New memory_search/postgres.py owns scoped SQL lexical/semantic candidates; indexed.py
overrides only candidate hooks of existing MemoryRetriever. Existing retrieval.py
extracts those protected hooks, preserving one unchanged merge/rank/limits algorithm.
Existing store, embedder, auth predicates, DTOs and ingestion/reconciliation retained.
New indexes.py owns only explicit autocommit concurrent HNSW/GIN index migration;
no startup mount, schema table, provider implementation or dependency change.
Runtime source scope exactly three new modules plus retrieval.py hook extraction.
New tests only two contract-allowed files. Existing foundation/capture code unchanged.

SQL returns bounded canonical records/distance, never JSON vectors. Fixed model/
provider/dimension predicates, actual dimensions/nonzero norm and current content
fingerprint are required. Direct distance ORDER BY and compatible expression index;
strict iterative scans, injected local limits, materialized scoped exact underfill
fallback. Existing lexical fallback preserved. New statements have local timeouts;
legacy fallback retains existing behavior, no total-request deadline guarantee.
SQL/auth failures propagate; embedding failure returns lexical after authority check.

Index migration compares exact PostgreSQL definitions, retaining literal whitespace,
rejects conflicting objects, requires idle autocommit (including rejecting explicit
transactions), serializes with advisory lock, reports invalid matching vectors,
repairs only exact owned invalid indexes, and never deletes canonical data.
Initial PostgreSQL test exposed renderer parentheses; fixed expected rendering from
actual server evidence without loosening comparator. Review found literal-whitespace
normalization could hide changed model/provider; corrected and regression-tested.

## Final commands and results

| Check | Actual result |
|---|---|
| `.venv/bin/python -m pytest -q tests/unit/test_indexed_memory_search.py` | 25 passed, 0.08s |
| `.venv/bin/python -m pytest -q tests/unit` | 487 passed, four previously recorded failures, 13.80s |
| `.venv/bin/python scripts/test_env.py test -q -s tests/integration/test_indexed_memory_postgres.py tests/integration/test_memory_postgres.py tests/integration/test_voice_runtime_postgres.py` | Final: 39 passed, no skips, 98.71s |
| Existing C01/C03A/C17A/C03R implementation manifests | All unchanged files OK |
| C02 implementation manifest | Six source/test files OK |
| `git diff --check` | No whitespace errors |
| `scripts/test_env.py stop` / `status` | Empty running inventory; test volume retained |

Full-unit failures remain Mail tool audience, DocumentsPanel prohibited marker,
MCP migration workspace-source assessment, runtime workspace-files prohibited markers.
They precede C02/C03R; no unrelated fixes/test weakening in this grouping. Earlier
iterations: 7 new DB tests passed28.21s; extended regressions38 passed96.10s; final
adds independent provider/model/zero guards and advisory-lock denial to39. Earlier
full suites481/483 passes reflected fewer new unit cases, same four failures.

Real SQL proof: current private/shared scope, wrong scope and revoked membership;
inactive/deleted/missing/stale vectors; independent provider/model/dimension guards;
malformed declared dimensions safely excluded; zero vectors excluded/refused by
migration; lexical fallback; exact underfill branch; complete MemoryService path;
repeat migration/name conflict/concurrent operator denial; actual statement-timeout
interruption leaves invalid concurrent index then rebuild succeeds. Backup before
fixture migration uses pg_dump custom format, restores synthetic fixture schema via
pg_restore, and compares canonical records/versions/evidence/transcripts/embeddings
including original IDs/fingerprints. No fabricated provider vectors represented as
real inference: all test vectors deliberately synthetic and persisted in pgvector.

## Natural plan, recall and resource observation

4,000 synthetic1536-dimensional vectors. Natural EXPLAIN ANALYZE BUFFERS selected
ix_vault_memory_embedding_hnsw_1536; separate rare-term full-text query naturally
selected ix_vault_memory_content_fts_simple. No enable_seqscan/indexscan forcing.
Final HNSW planning1.331ms/execution3.789ms; root shared-hit1319/read0 blocks;
index32,776,192 bytes. Four ANN/exact SQL recall@10 values:1.0,1.0,1.0,1.0.
Separate20/4000 shared-visible filter:10 results, recall@10=1.0, no private results.
Final ANN/exact query elapsed pairs(ms):20.82/146.40,21.48/148.94,20.88/145.28,
23.20/149.09. Includes connection/query overhead, excludes provider embedding,
live scheduling, network/model responses and user answer quality. Not a product
latency/recall SLA, speed promise, production scale or live-turn evidence.

Installed test PostgreSQL16.15 / pgvector0.8.6, observed image ID
sha256:9b05db12a35460fff0587e009f9326e414a53e9484555547f96d214a2ba98ef7,
repo digest pgvector/pgvector@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b.
No floating-tag upgrade/image pull. Preflight exact loopback127.0.0.1:55436 DB
resono_vault_test; new autouse gate also binds host/port/user to the fixed Docker
backup/restore target. Global existing name gate retained. Only test volume mounted.
Disk preflight15564MiB available; later observed container126.4MiB/23.36GiB and
host11925MiB available (not peak sampling/capacity acceptance). Existing uv frozen
audit only, no new deps. No installed/manual Vault DB, private session history,
provider requests, donor edits or production package deployment. Linux Docker
harness tested; Windows/macOS and production deployment unverified.

## Exit / next grouping

Bounded contract gates PASS internally. [Implementation hash](2026-10-07-LMD-C02-implementation.sha256)
is final source identity; original source/review hashes stay historical, never
rewritten. C01/C03A/C17A/C03R remain intact. Original grounding unchanged.
Latest owner shared-context clarification retains C05 VoiceMem/C06 live-loop work:
next review binds one evolving context to parallel recall/decisions with retain/
drop/re-search and final validation. Neither VoiceMem nor live controller is
claimed built by SQL proof. C13 production cutover/maintenance remains outstanding.
Rollback is adapter removal to legacy without canonical data changes; no index or
source-table removal was exercised outside the isolated synthetic fixture.
