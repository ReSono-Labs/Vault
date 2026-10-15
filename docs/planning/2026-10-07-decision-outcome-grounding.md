# Decision-review outcome grounding

Owner addition 2026-10-07: review user satisfaction with results and tool calls;
correct tool selection can coexist with wrong context. Analyze all these separately
in the actual prompt/logic. Agent work must be goal-driven, not arbitrary wiring.
After full implementation, review the complete flow end-to-end, not now.

This supplements, never replaces, October4 grounding. Existing memory analysis and
the two system identities remain. The procedural reviewer is a capability invoked
through the same configured model execution, with an explicit review objective.
Any Background scheduling mount must use its existing Goal/task machinery; no
third reviewer agent or autonomous new goal authority is introduced.

Required dimensions per captured decision point: tool selection, context selection,
result/answer quality, user satisfaction, and failure attribution. Positive evidence,
negative evidence, mixed evidence and unknown must remain distinct. Absence of
complaint, another turn, a non-error tool response or an assistant's own claim is
not satisfaction. Corrections are negative/repair evidence, not original intent.
Feedback/context/answer references must belong to the exact captured point. Missing
capture cannot be reconstructed. Preserve failure assessments even when no rule
is learned. Do not convert model judgments into tool/source/user ground truth.
Record satisfaction with tool choice, context and result separately from overall
satisfaction; a correct tool choice must not mask a dissatisfied result.

Validated success requires correct route and context plus a supported result, not
merely transport success. Dissatisfied/mixed feedback cannot teach an unqualified
successful procedure. Unknown satisfaction must remain unknown; it does not become
an endorsement or invented numerical score. Current activation quality/source
qualification remains required independently of the reviewing model.
