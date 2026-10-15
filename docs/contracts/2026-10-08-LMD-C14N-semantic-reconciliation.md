# C14N — post-analysis indexed search and model reconciliation before rule save

Authority: owner explicitly requests post-session search/review before decision
save and prompt-guided nuance classification. REUSE absolute Vault root
`/home/christian/Documents/Projects/ReSono-Labs-Vault/app/vault_runtime/`:
`decision_learning/{voice_review,repository,reviewer,chat_learning,chat_activation}.py`,
`decision_routing/example_index.py`, `memory/openai_reviewer.py`, composition.
NEW `decision_learning/reconciliation.py` joining capability only. No third agent,
Background goal, provider, grant system, vector store or replacement reviewer.

Decision gate/internal prebuild review CONTINUE: use actual scoped selected memory
review model/SDK runner, not deterministic keyword classification or Decisions API.
After evidence analysis, before committed proposals/publication, embed each changing
proposal with existing real embedder and search existing active HNSW examples (20/5).
Load complete authoritative candidate applicability from bound existing definitions.
Second structured model call compares function, conditions, slots, capabilities,
exceptions and other proposals from the same review. Reuse/add_example preserves
behavior; refine/revise creates a new version of same ID; distinct creates a new ID;
ambiguity defers. Similar vocabulary alone must not merge distinct operations.
Session-specific names/IDs remain parameterized. Evidence assessments, citations,
examples and available capabilities cannot be invented/improved by reconciliation.

Persist initial analysis and reconciled result plus model/provider/catalog epoch in
existing review source_coverage_json under fenced lease. Retry reuses checked
analysis/stage output; complete review stays immutable. Search/model/index/provider
failure blocks publication, not normal Chat or factual memory. No active catalog
means explicit empty candidate set (no embedding expense), still compare same-batch
proposals with model. Catalog switch before commit/activation defers stale work;
never silently publish against a newer unreviewed catalog. Existing automatic
read-only policy and final grants remain. Module disable removes the hook.

Counterexamples/proof: semantically same workflow with different wording reuses ID;
nuanced conditions revise same ID; invoice balance/status remain separate; invented
assessment/citation/target rejected; model/embedding failure publishes nothing;
retry avoids repeated calls; current epoch change blocks publication. Synthetic
model/embedding tests plus actual mounted isolated pgvector flow; no paid calls or
installed DB tests. Similarity/model judgments are not a guarantee of universal
semantic deduplication. Full windows/Voice source/recovery remain outside this slice.

## Owner-requested record-format examples

CONTINUE, internal pre-edit review: owner requests concrete record examples in the
model prompt. REUSE the actual `reviewer.py` Proposal/PointAssessment/ReviewOutput
and reconciliation output schemas at the absolute Vault root above. NEW shared
`decision_learning/prompt_examples.py` contains synthetic formatting examples only,
included in both model instructions; no new output fields, DB schema, behavior or
model call. Show full assessment/envelope plus create/add_example/revise/defer
proposals, explicit nulls and arrays. Reconciliation preserves actual analysis
assessments/citations/examples rather than copying demo values. Database IDs,
versions, scope and grants remain code-owned. Counterexample: a demo capability or
citation leaks into real output; existing validators must still reject it. Test
example records against current typed schema and prompt inclusion. Formatting
proof is not a paid-model semantic quality evaluation.
