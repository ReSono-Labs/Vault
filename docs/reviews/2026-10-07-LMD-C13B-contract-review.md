# C13B/r1 internal source/necessity and candidate attack review

Same-context self-review. PASS bounded epoch/state contract, not full live build.
Observed same-content branch in reconcile_memory updates metadata/recency without
version. Memory DTO/query columns and fixed positional version offset remain
unchanged when a new column is appended. Existing C13A authority locks and scope
helpers are reused, not another grants/auth implementation.

Scoped counters are NEW necessary invalidation metadata, not a memory store.
Per-record-only validation misses new relevant facts/empty-cache changes. Entire
corpus hashing duplicates expensive work; scoped shared/private counters solve
this independently demonstrated counterexample. Current-context completeness still
needs session, preference, capability and procedural generation checks, not claimed.

Reviewed erasure against owner_remove_user: it retains a deleted user tombstone,
so FK CASCADE alone is insufficient. Existing optional cleanup must include private
epoch rows AFTER canonical records. Shared counters remain to invalidate surviving
members' context. Workspace FK cascade removes scope rows when workspace erased.
Record delete trigger checks parents before attempting any counter insertion.

Reviewed lock concern: missing legacy scope rows or private->workspace transitions
could require new parent FK locks while another transaction removes that parent.
Seed from identity metadata (not fact/embedding scan) and initialize shared scope
on first insert. Existing parent references stay stable for normal updates.
Prove identity deletion/cascade and transaction rollback in actual PG tests.

No new user policy/default or provider dependency. Owner full-build instruction
authorizes continuing reviewed deltas, not calling this completed production.
Targeted tests only. Freeze this review, exact contract and current source before
runtime edits; later evidence must distinguish original sources deliberately changed.
