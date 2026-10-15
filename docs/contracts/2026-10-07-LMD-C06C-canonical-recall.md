# C06C/r1 — canonical factual recall preparation adapter

Original R02–07/R09/R18/R28/R31/R33 and LC-R01–04 control. Bounded C06 child;
not full source qualification, semantic-quality acceptance, procedural store or
production Chat/Voice adoption.

## Actual reuse and missing delta

Absolute root /home/christian/Documents/Projects/ReSono-Labs-Vault/. Existing
memory_search/indexed.py PgvectorMemorySearchBackend owns actual indexed SQL and
R1 ranking. memory_search/contracts.py already owns MemorySearchBackend;
memory/service.py already resolves scoped embedding factory with honest lexical
fallback. C06B owns CurrentStateGuard; C05A/C06A owns the one VoiceMem stream/
parallel lifecycle; C17A selector.py owns candidate_set_fingerprint validation.
Missing is a PreparationPorts implementation joining these, not another ranker,
provider client, store, scheduler or selector interface.

NEW live_memory/canonical_ports.py CanonicalPreparationPorts receives required
guard, read-only search_backend, explicit limit1..existing MAX_RETRIEVAL_LIMIT,
query_builder(snapshot), decision_retriever(snapshot,memories,retained), and scoped
embedder_factory (explicit None permits honest lexical-only availability). Require
backend.repairs_vectors_during_query is False; reject legacy repair-capable search
instead of backfilling memory during drafts. Query builder and decision retriever
must be callable, never fabricated context interpretation or stored rules.
Production query builder must use qualified shared context, not a separate buffer;
C03C/context interpretation remains necessary. Existing embedding factory may be
injected unchanged; no new credential/transport implementation.

is_current delegates to required actual guard. reuse retains complete factual and
procedural output only when exact text, context sources/fingerprint, validity,
scope, conversation/segment/utterance match AND guard validates rebound output.
Revision and final turn identity are rebound after validation, never ignored by
controller. Any changed text/context drops prior candidates and runs current
retrieval; no cosine/substring inference of negation/entity/amount equivalence.
Fresh retrieval can return the same still-relevant canonical ID, binding it anew.
This safe baseline does not claim optimized changed-meaning reuse or near-perfect
quality. Those remain comparative C05/source interpretation and release evidence.

recall builds one current-context query, validates through existing final-text
UTF8/nonblank/64KiB bound, resolves existing scoped embedder with same availability
fallback as MemoryService, calls backend.retrieve. It never calls ensure_vectors,
reconcile or another vector scan. Validate immutable bounded RetrievalMatch tuple;
rank/score/evidence semantics stay backend-owned. decisions forwards same snapshot
and recalled memory to required callback; validate immutable choices with existing
C17A mapping validator. No transport/action/permission inference. Empty choices
are legitimate explicit callback output, not a claim procedural learning exists.

Use adapter ONLY through existing ParallelPreparation: its before-work/current
and final checks guard provider calls/publication and reuse. No duplicate inner
guard around every method; this avoids repeated identical current-state lookups.
Parallel memory/decision jobs and the one memory-dependent reconsideration remain
owned by existing controller. Wrong/stale work is rejected by that controller,
not exposed as final context. No new standalone callable API is mounted.

## Scope and acceptance

Only new canonical_ports.py, tests/unit/test_canonical_live_recall.py and tests/
integration/test_canonical_live_recall_postgres.py; documentation allowed. No
existing runtime/schema/composition/UI/dependency/model code changes.
Exact source/candidate freeze and internal necessity/attack review before READY.

Targeted tests: repair-capable backend denied; invalid configuration/query/result
or duplicate candidate rejected; exact current reuse avoids another query;
changed person/negation/context discards and searches; same snapshot/memory reaches
parallel decisions and reconsideration; stale guard prevents work/publication.
Real isolated PostgreSQL: existing HNSW migration and canonical synthetic1536
vectors; feed evolving drafts through actual VoiceMem + canonical ports + C06B
guard + indexed backend, demonstrate retain/re-search/drop, exact immutable final
rebind, Off invalidation and private isolation. Explicit synthetic embedder/
decision callbacks only, no provider paid tests or factual quality claim. No
Python embeddings_for scan or memory write permitted during draft retrieval.

Removal replaces existing PreparationPorts with no-op/alternative; no source data
or learned store removal. C13 maintenance/cutover, actual C03C context source
interpretation, C14/C15 eligibility and C08/C12 enrollment remain prerequisites
for full production live behavior. Do not call this adapter a completed module.
