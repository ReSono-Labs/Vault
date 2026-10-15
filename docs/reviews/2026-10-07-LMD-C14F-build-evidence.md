# C14F/r1 — goal-directed outcome reviewer v2

Owner-requested extension of the existing shared model capability, not a new system
agent/memory reviewer/Background executor. Actual prompt starts with explicit GOAL;
all captured points require assessments of tool choice/context/result correctness,
tool/context/result/overall user satisfaction and failure attribution. Unknown is
explicit; absence of complaint is not satisfaction. Point-linked captured feedback,
context and answer references required. Later correction/repair cannot turn an
original bad attempt into success. No hidden/original reasoning reconstructed.

Changing successful proposals require all necessary correctness assessments and
no negative satisfaction, plus existing final/resolved/non-error source checks.
Failures/no-change/insufficient evidence retain assessments. Additive assessments_json
in existing review store; learner v2 claims/output fingerprints fence immutable
replay; old v1 results retained and explicitly unsupported, not silently upgraded.
Existing memory reviewer unchanged, same scoped provider/model executor reused.

Final **159 targeted units passed in 1.42s**, including 17 outcome tests, reviewer,
checkpoint units, existing memory reviewer/capabilities/diagnostics/selector. Three
initial new-test tuple/list fixture errors corrected; previous 158 was intermediate.
Actual DB checkpoint tests verify stored v2 assessment payload, failure assessment
recovery, conflicting assessment retry rejected and v1 explicit refusal; combined
16 distinct DB tests/last two corrected passes described in C14E evidence. No
actual provider/private retained history requests or semantic-model eval performed.

Internal bounded review: PASS shape/reference/failure gates and persistence only.
Semantic correctness remains model judgment, not source/user ground truth; real
source projection must prove feedback association/coverage and suppression. Numeric
satisfaction/confidence thresholds not invented. Reviewer capability has explicit
objective, but existing goal-based Background scheduling mount is still required;
no new runtime agent identity/goal authority. Whole-flow review remains deferred
until full build as owner requested. Older C14A/B/C/D manifests are historical for
changed code, not rewritten to pretend their frozen review approved v2.
