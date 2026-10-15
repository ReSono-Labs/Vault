# C14N — model-guided reconciliation before learned-rule save

Branch: `feature/live-memory-decisions`. Internal bounded verification, not an
independent review, paid provider evaluation, deployment or full parent completion.
Original October4/5 grounding is unchanged. Register r33 owns allocation/status.

## Actual mounted flow

`composition.py` joins the new `decision_learning/reconciliation.py` capability
to the existing Chat `VoiceDecisionReview` instance and existing learned-query
object. The Voice instance remains analysis-only; it is not silently qualified.
There is no third registered agent, generic Background goal job, new database,
or replacement factual-memory reviewer.

1. Sealed canonical segment is qualified and claimed by the existing review store.
2. `voice_review.py` resolves the workspace-selected provider/background model once
   through `background_access`, binds it via `BoundReviewAccess`, and reuses
   `OpenAIMemoryReviewer` / shared SDK runner for structured procedural analysis.
3. Its analysis is checkpointed in existing scoped
   `vault_decision_reviews.source_coverage_json.analysis` under the running lease.
4. For changing qualified proposals, the existing real embedder searches active
   indexed examples through `ActiveDecisionQueries.retrieve` (20 examples / 5
   decisions per proposal). Full candidate definitions come from the immutable
   source-bound catalog context, not just similarity scores.
5. A SECOND structured call to the SAME configured model uses the explicit
   `Vault Decisions Reconciliation` goal/prompt to compare workflows, conditions,
   slots, capabilities, exceptions and same-batch proposals. It chooses
   `add_example`, `revise`, `create`, or deferral. No active catalog means no search
   embedding call, but still a model comparison of the proposal batch.
6. Code preserves assessment values, proposal order/count, citations and examples.
   Example-only output must exactly preserve authoritative behavior. Automatic
   revision cannot drop prior conditions, required slots, exclusions or capabilities;
   removal/restructuring requires a different reviewed change, not silent broadening.
   Unknown/negative satisfaction is not rewritten into success.
7. Reconciliation output/rationale/provider/model/candidate IDs/catalog epoch are
   checkpointed in `.reconciliation`, then the existing repository completes the
   review. Existing publisher stores versioned definitions/examples/generations and
   real indexed embeddings; existing source/capability/grant gates control activation.
   The model classifies/proposes; validated code performs database writes.

Completed stages are immutable and reused on explicit retry. Lease/source/provider/
model/catalog checks reject stale work. Publisher requires reconciliation evidence
for changing mounted Chat output and preserves its epoch through activation CAS.
Search/model/index failure blocks learning/publication, not the original Chat answer.
No-change/unknown evidence does not cause an extra reconciliation call.

## Targeted proof

- 54 focused unit checks: reconciliation plus existing procedural/outcome reviewers.
  Covers semantic candidate payload/model invocation, checkpoint reuse, empty catalog,
  refinement/distinct choices, immutable assessments/citations/targets/example-only
  behavior, safeguard retention, unavailable embedding/model and changed epoch.
- 8 isolated PostgreSQL checks: review repository and actual mounted Chat learning.
  Includes stage retry/fencing/source revocation; mounted model initially proposes
  a differently worded duplicate CREATE, reconciliation finds the existing rule
  through real pgvector retrieval and changes it to example-only reuse. One ID
  advances to version2; final/live preview reuse, grant denial and erasure remain.
  Synthetic provider/embedding transports only; real isolated tables/HNSW path.
- `git diff --check` passes. No frontend code changed in this slice.

## Limits

Owner-requested formatting follow-up: shared `prompt_examples.py` now supplies
actual JSON envelope/assessment and alternative proposal examples to BOTH model
instruction strings. All required fields, null targets, arrays, parameterized slots,
unknown satisfaction and evidence references are demonstrated. Demo values are
explicitly synthetic, never copied into actual records; code-owned IDs/version/
scope/grants are excluded. Reconciliation must preserve actual analysis evidence,
not demonstration evidence. 59 focused unit checks pass, including four example
classifications against the actual typed/reference validator and shared prompt
inclusion; actual review runner test also asserts example instructions are supplied.
No DB schema, output contract or additional model call changed. Guidance checked
against [official Structured Outputs required-field documentation](https://developers.openai.com/api/docs/guides/structured-outputs#all-fields-must-be-required).
This is schema/instruction verification, not a paid model quality evaluation.

Semantic equivalence remains a model judgment, not a universal dedup guarantee.
Search covers eligible active catalog candidates, not every inactive/historical rule.
An ambiguous or stale comparison defers instead of blindly merging. Same-batch
equivalence is model-reviewed; structural exact duplicates retain existing store
guards. No paid-model accuracy/latency claim. Full-session windowing, autonomous
recovery, Voice qualification/live integration and the larger release remain open.
