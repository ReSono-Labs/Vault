# C13C — owned indexed startup migration and bounded maintenance

Original R06/R07/R28/R31/R33 and BP-R04. REUSE exact existing Vault root
/home/christian/Documents/Projects/ReSono-Labs-Vault/app/vault_runtime/:
composition.py backfill_memory_vectors, memory/service.py ensure_vectors,
memory_search/{indexes,indexed,legacy}.py, local_identity/repository.py
active_storage_identities. NEW memory_search/maintenance.py lifecycle adapter only.
Replace the existing unowned one-shot 1000-row backfill thread, not a second repair
worker or vector store. Existing indexed query/ranker/current snapshot writes remain.

Run exact owned concurrent index migration on a dedicated autocommit connection
outside ensure_schema and request handlers. Preserve original data/JSON vectors;
conflicting owned index fails closed, never overwrite another index. Default indexed
mode activates existing SQL backend after migration; operator environment rollback
restores legacy backend. Live preparation stays unavailable until actual indexes
are validated; no claim HNSW exists merely from column/query code.

Maintenance polls current active scopes, bounded 32 missing vectors per scope per
60-second cycle, using current configured factory and existing atomic producer
snapshot checks. Restart resumes from canonical missing-vector rows; no separate
job payload or cursor table needed for this idempotent missing-current-vector task.
Provider failures keep facts and truthful missing state; no interactive repair on
indexed path. Existing successful ingestion still embeds immediately. Scope removal
and correction/deletion win through existing repository checks. No per-draft writes.

Material gate: reuse canonical missing-vector query as durable retry worklist,
instead of duplicate durable vector-job ledger. Counterexample: failed head batch
starves later rows indefinitely; record bounded failures/rotation needed before
claiming complete corpus recovery. CONTINUE mount/migration; no general multi-model
reindex contract or numeric release SLA. Normal request can remain legacy until
index ready; Live Off does not change normal lookup/review. Shutdown signals worker
and waits boundedly; underlying provider timeout remains counted by this one thread.

Tests: actual installed-format isolated PG migration/idempotency/index identity,
default SQL routing after readiness, retained data/rollback, no query repair;
synthetic worker/provider for retry/stop; existing C02/C13A/B proof reused, not rerun
broadly. Production installed DB is never a test target. No live paid provider calls.
