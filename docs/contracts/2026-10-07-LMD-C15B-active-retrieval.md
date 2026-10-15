# C15B — current active catalog retrieval

Internal prebuild review r1, 2026-10-07. Inspected C14E activation.py and existing
example_index.py/contracts.py: actual SQL ANN exists, but it accepts arbitrary
inactive generations. Extend this query owner, not a second vector retriever.

Read current owned pointer/epoch and active generation coherently under repeatable
read plus row locks. Existing indexed SQL narrows to active definitions; bounded
nearest examples collapse by definition. Reuse mandatory C14E qualification and
current C15A capability gate to filter resulting candidates structurally before
returning CandidateChoice. Return pointer epoch and capability fingerprint alongside
choices for consumer validation. No model, tool, draft persistence or automatic
execution. Recheck capabilities before return. No source/capability permissive default.

Read-only effect, source/suppression/quality are necessary not sufficient for final
execution: final meaning, required slots, installed schemas, existing grants and
confirmations still apply through actual runtime. Partial candidates are observations.
Bounded top candidates may all be rejected; return empty rather than unbounded
search. This does not prove useful recall or final condition interpretation.

Actual DB checks: indexed active retrieval, inactive write/source-denied exclusion,
revocation after activation, scope isolation, erased pointer empty result. Preserve
inactive inspection method/tests. Still unmounted; do not claim Chat/Voice enrollment.
