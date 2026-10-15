# C02/r1 — internal contract/source review

2026-10-07, same-context self-review; not independent assurance or owner acceptance.
Frozen candidate/source manifest includes exact contract and existing code. Original
owner request, R01/R06/R07/R26/R31/R33/D18, storage plan and C01 actual calls reviewed.

| Attack | Disposition |
|---|---|
| Existing vector persistence mistaken for SQL search | Positively traced JSON/Python path; new query required, no new store |
| Duplicate rank/auth/credential implementation | Existing hooks/ranking/repository predicates/scoped embedder reused |
| Fixed model/dimension mismatch or stale content | Fixed compatible index contract plus actual-dim/nonzero/fingerprint guards; real tests required |
| ANN postfilter underfill/older extension | Require >=0.8, bounded iterative parameters and scoped materialized exact fallback; no recall guarantee |
| Valid index name masking wrong object / interrupted concurrent build | Compare owned definition and relation; fail collision; exact invalid index repair only |
| Unbounded startup production index build | No composition/schema/startup changes; explicit autocommit migration only |
| Pretend forced index plan proves natural use | Required natural EXPLAIN at synthetic representative scale; reopen if absent |
| Destructive fixture pointed at installed database | Exact existing test DSN/volume/global gate verified; backup/restore synthetic schema only |
| Public method behavior drift | Legacy hook extraction only; run original retrieval/caller tests and preserve foundation hashes |
| Isolated adapter proof overstated as production cutover | Current composition remains legacy; C13 explicitly retains cutover/maintenance/epoch work |

PASS bounded aligned contract for implementation, CONDITIONAL final verification
on real SQL/index/restore/recall and regression proof. No new policy/default/SLA,
donor rights assumption, provider call or broader allocation readiness granted.
Owner authorizes aligned reviewed builds on existing feature branch. Prebuild
source hashes must match; later lifecycle/source changes need new dated evidence.
