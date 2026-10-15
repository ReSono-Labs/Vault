# C02/r1 — indexed SQL query and additive index migration

Lifecycle VERIFIED for bounded SQL/index grouping after
[build evidence](../reviews/2026-10-07-LMD-C02-build-evidence.md); internal only,
not owner acceptance or production cutover. Prior candidate review remains dated.
Original R01/R06/R07/R26/R31/R33 and D18/D19 control;
register owns readiness. Owner authorizes aligned reviewed contracts/build on
feature/live-memory-decisions. This grouping is isolated SQL/index proof, not
production cutover, maintenance, epochs or live scheduling (C13/C06).

## Observed necessity / preserve existing code

composition.py -> MemoryService -> existing C01 LegacyMemorySearchBackend ->
MemoryRetriever -> embeddings_for reads vector_json and Python cosine scores.
memory/schema.py has unconstrained vector plus JSON; no memory HNSW or GIN index.
Reuse canonical memory tables/DTOs, scoped embedding factory, repository membership/
scope checks, reconciliation/delete behavior, existing C01 interface and ranking.
No migration applied to installed Vault; no provider call or new dependency.

Exact source paths under /home/christian/Documents/Projects/ReSono-Labs-Vault/:
app/vault_runtime/memory/repository.py, schema.py, models.py, retrieval.py,
openai_embeddings.py, memory_search/contracts.py, legacy.py, memory/service.py,
composition.py, tests/integration/test_memory_postgres.py, scripts/test_env.py,
tests/conftest.py, compose.test.yml. Existing sources stay canonical.
NEW is only adapter/query/index migration absent from the inspected path.
Primary mechanism reference: https://github.com/pgvector/pgvector (2026-10-07),
expression/partial HNSW, cosine operator, iterative filtering, concurrent creation.
No external donor code copied or license claim widened.

## Exact build boundary

- NEW memory_search/postgres.py: read-only queries over MemoryRepository's existing
  internal connection/auth/scope adapters. Scoped active-member/user/workspace checks
  before every read; private/shared/active predicates inside SQL, including active
  membership join. SQL returns bounded canonical MemoryRecord and distance, never
  vector_json/all vectors. Only fixed openai/text-embedding-3-small/1536 index contract.
  Actual dimensions/nonzero vectors and current SHA256(content) required.
  SQL ORDER BY the index expression <=> bound vector LIMIT, not transformed score.
  Query vector numeric, finite, 1536 and nonzero; no silent shortening/model guessing.
  Explicit operator-injected timeout/ef_search/max_scan_tuples (test settings only,
  no production numeric SLA/default). Require pgvector >=0.8 for iterative scans.
  SET LOCAL strict_order and limits. Underfilled ANN uses MATERIALIZED authorized
  exact SQL candidates and same distance/rank; output remains bounded. Exact mode
  is test/shadow reference, not Python scan. DB/auth errors propagate.
  Indexed simple full-text query plus existing lexical fallback, bounded union.
  Local timeout applies to new statements; existing lexical fallback timeout
  behavior is unchanged. This is not an overall request deadline guarantee.
- NEW memory_search/indexes.py: fixed concurrent HNSW1536 and lexical GIN index
  definitions over existing tables, no startup mount. Autocommit connection only;
  caller supplies explicit administrative migration connection. Inspect extension,
  eligible/invalid row counts; reject incompatible matching rows. Advisory lock
  serializes migration. Valid same-definition index is no-op; wrong-definition/name
  collision fails; exact invalid owned index can be dropped concurrently/rebuilt.
  No canonical data deletion or automatic schema/backfill. Index expression and
  predicates shared with query so mismatched-dimensional rows cannot cast unsafely.
- NEW memory_search/indexed.py: C01-compatible removable backend. Reuse existing
  lexical/exact/semantic merge/ranking. Embedding failure/unsupported model yields
  truthful lexical only, rechecking authority; SQL error does not become empty match.
  repairs_vectors_during_query=False. No provider or memory write in query.
- Existing memory/retrieval.py: extract current lexical candidate and semantic
  candidate methods as protected hooks; identical old algorithm/default behavior.
  New SQL retriever overrides hooks, not a second ranking or Python semantic scorer.
- NEW tests/unit/test_indexed_memory_search.py and
  tests/integration/test_indexed_memory_postgres.py; no other runtime/test changes.
  Documentation/evidence/status updates allowed. No composition, API, schema,
  service, provider, dependencies or donor changes. General Chat/learning excluded.

## Material choices / counterexamples / dependents

Question: replace store, add unused index, or new C01 SQL backend? Authority owner
HNSW direction and positively traced Python path. Choose additive backend/query
and explicit migration, preserving one rank policy/store. Counterexample: backend
calls embeddings_for/cosine, queries unscoped data, or test forces index plan and
claims natural planner adoption. Dependents C13/C06. CONDITIONAL until real proof.

Question: ANN filtering/extension differences? Isolated test extension0.8.6,
PG16.15; exact image ID sha256:9b05db12a35460fff0587e009f9326e414a53e9484555547f96d214a2ba98ef7,
repo digest pgvector/pgvector@sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b.
Choose explicit minimum0.8 plus iterative bounded scans and underfill exact SQL,
not global planner-disable mutation or assumption of perfect ANN recall. Query/
index guards exclude incompatible rows; migration reports/refuses corrupted
matching rows. Counterexample same model different dimensions reaches cast or
stale fingerprint ranks. Larger adoption/resource budgets remain C13, not selected.

Question: current ready-to-serve production route? Keep existing composition until
C13 migration/maintenance/cutover review. Inject SQL backend into existing service
in real DB tests to prove complete adapter path. Counterexample report calls this
production HNSW despite legacy composition. CONTINUE for isolated building only.

## Required evidence / safety / reversal

Test target exactly resono_vault_test loopback55436/test volume; global gate reused.
Never installed/manual Vault DB. Synthetic dataset: scope/private/shared/revocation,
inactive/deleted/stale fingerprints, provider/model/dimension mismatch, missing
vectors, embedding outage/malformed query, full text/exact/legacy lexical parity,
limits, underfill exact fallback. At representative synthetic scale record natural
EXPLAIN ANALYZE BUFFERS with actual HNSW (no enable_seqscan-off proxy), exact-vs-ANN
top-k overlap/timing/filtered recall, actual extension/index/resource inventory.
No synthetic vectors represented as provider-generated or answer-quality proof.

Before applying indexes: consistent pg_dump of isolated synthetic fixture to
temporary artifact; restore into exact test DB (fixture schema only) and verify
canonical IDs/evidence/versions/embedding fingerprints unchanged. Test repeat
migration, wrong-definition collision, simulated interrupted invalid concurrent
index/rebuild, outside-transaction requirement, existing schemas unaffected.
Bound test scale/resources; disk preflight showed15564MiB available, no production
capacity claim. Restore stopped harness state retaining volume; no volume reset.

Run focused new unit, original retrieval/caller contracts, existing memory/Voice
PostgreSQL regressions. Freeze original reviewed source and contract; review
internally against original request before READY. Final proof must be no-skip SQL,
not mocks alone. Existing C01/C03A/C17A/C03R manifests stay unchanged.
Rollback: remove injected adapter to legacy with unchanged canonical data. No
production default changed; retain JSON/legacy. Index cleanup only explicit owned
indexes under separately approved operator scope, never drop source tables.
Stop/reopen if natural HNSW proof fails, schema/collision unsafe, new auth/ranking
authority, unexpected edit/dependency or unsafe DSN. C13 remains unbuilt.
