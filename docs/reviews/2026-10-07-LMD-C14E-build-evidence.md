# C14E/r1 — additive catalog activation evidence

Implemented CatalogActivator over the existing rule repository. Transactional
scope lock/expected epoch; prior unchanged definitions/examples/vectors retained;
revision predecessor/version fencing; example-only behavior immutable and original
evidence retained. Mandatory current qualification/capability callbacks, active
read-only definitions only, complete compatible vectors/observed evidence, double
capability check. Atomic pointer/state update, exact retry, rollback on exceptions.
No tools/model calls in transaction, no production mount.

New nullable scoped activation pointer/member FK and before-delete source/catalog
invalidation preserve erasure and advance epoch without stale pointer resurrection.
Old plan RESTRICT changed deliberately by the reviewed C14E contract, not an
unrecorded schema assumption. Deleting any retained source review invalidates the
dependent active catalog, even if its generation came from another review.

Seven distinct new actual DB tests cover additive activation/revision/source
erasure; rollback/old-rule requalification; missing vectors/write-only denial/
foreign scope/capability change; concurrent CAS one winner; active reads (C15B);
stale/orphan revision/account erasure; example-only behavior/evidence preservation.
Combined final targeted evidence: 16 distinct actual PostgreSQL tests across these
seven plus existing rules/service/checkpoints, synthetic gates/provider vectors.
Final run had 15 passes and one test-fixture placement error; corrected two affected
tests then passed 2 in 6.58s (not additive test count). Earlier 11 passed in 28.09s
and 15 in 36.84s are intermediate, not final additional tests. 159 targeted unit
regressions passed in 1.42s after final reviewer additions. No broad suite rerun.

Qualification callbacks must actually pin current sources/suppression/quality in
production; synthetic True callbacks are tests, not delivered production logic.
External in-memory catalog/grant changes are checked twice, not transactionally
locked by PostgreSQL; actual final runtime still revalidates. Large catalog bounded
compilation rejects rather than silently dropping data; scale/performance unproved.
Exact acknowledged activation retry reports stored pointer only, never a fresh
grant. Full auto-learning/worker/final execution acceptance remains unimplemented.
