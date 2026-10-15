# C14F — evidence-linked multidimensional outcome review

Prebuild internal review r1, 2026-10-07. Inspected reviewer/schema/repository/service:
existing request_outcome collapses correctness and stores only proposals. Owner
requires distinct tool/context/result/satisfaction analysis, including failures.
Reuse existing model capability/checkpoint; no additional reviewer process/identity.

Reviewer contract v2: one assessment per captured observation, exact evidence-linked
dimensions, bounded explanation/failure attribution. Input adds captured context,
assistant final and user feedback references; no inferred source links. Changing
successful proposals require assessed correct tool/context/result and not negative
satisfaction, plus existing resolved non-error final-source validation. Prompt has
explicit goal, full-session correction-aware evaluation and unknown handling.
User satisfaction positives/negatives cite linked user feedback/correction only.
Tool-choice, context, result and overall satisfaction are separate typed fields;
positive feedback about one aspect cannot stand in for another aspect.
No complaint or assistant declaration is never user satisfaction.

Add assessments_json to existing review table, record v2 learner version in claims,
store/hash/replay assessments with proposals. V1 checkpoints remain retained but
cannot silently qualify as v2 outputs: explicit unsupported-old-result rejection.
No forced private history rebuild, synthetic providers only. Additive idempotent
schema change. Store assessments even for insufficient_evidence/no_change outputs.

Tests: correct tool/wrong context; right context/bad result; dissatisfaction; missing
or contradictory feedback; missing/foreign references; all-point coverage; safe
unknown output; durable immutable checkpoint/replay/hash; existing memory reviewer
unchanged. No model-semantic accuracy claim from synthetic output tests. Actual
source producer qualification and existing Background goal-based mount still open.
Final whole-flow review is explicitly deferred until full build, as owner requested.

OpenAI Docs skill: searched then opened [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
2026-10-07. Typed schema constrains shape, not judgment correctness. No model/SDK
upgrade, paid calls or credentials read.
