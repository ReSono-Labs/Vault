# C04G — procedural assessment/output window evidence

Branch `feature/live-memory-decisions`; internal same-context review. Original
grounding unchanged. [Reviewed contract](../contracts/2026-10-08-LMD-C04G-procedural-assessment-windows.md).

## Actual wiring / reuse

`VoiceDecisionReview.finalize_source` remains the shared channel execution owner:
qualified source/lease, bound configured model, immutable analysis, existing semantic
reconciliation, completed review, existing publication/activation callback. It now
selects observation/output windows when>16 points, oversized snapshot serialization,
or a legacy response fills/exceeds32 proposal slots. Legacy overflow raises a typed
error, never clips output. Existing small-session calls/prompts remain unchanged.

NEW `decision_learning/analysis_windows.py` is a small coordinator, not a scheduler,
source store or additional agent. Each page keeps ALL original source/corrections
visible. At most16 observations/window and32 proposals/page; typed has_more controls
continuation. Prior emitted behavior records, not opaque hashes alone, tell the
model what to exclude. Fixed assessments are supplied verbatim on continuation;
changed judgments/explanations are rejected, not silently overwritten.

`DecisionReviewRepository.stage` stores plan and validated pages in existing scoped
review metadata under the same source-current/authority/lease fences. Provider/model,
coordinator contract and actual page-input hash bind each step. Plan persistence
prevents rerunning legacy analysis on retry after switching to continuation. Invalid
or nonadvancing pages never become successful checkpoints. Expired leases do not
authorize writes; existing retry worker resumes retained pages.

Exact behavior equality merges point/source/example unions across windows, not
just the first example. Near-duplicates still require the existing semantic model
reconciliation. Full aggregate is validated once against the original root source
before reconciliation/completion/publication. Schema shape and evidence rules stay
v3; aggregate storage bound grows to512 proposals/256 assessments and1MiB, while
legacy model calls still reject>32 proposals/>100k output. No new DDL or worker.

## Focused evidence

Only synthetic models and allowlisted isolated PostgreSQL/pgvector
`127.0.0.1:55436/resono_vault_test`; no installed/history DB, paid calls, deployment
or external donor writes.

- New coordinator + existing reviewer/outcome/reconciliation/prompt-example units:
  **65 passed in0.99s**. Twenty-one assessed points across windows; interrupted
  second window resumes first; same behavior retains all21 point references;
  later correction source appears in EVERY model input. Dense40-proposal
  continuation preserves all output and fixed assessments. Repeated behaviors,
  changed assessments/model and oversized source are rejected before false save.
- Existing mounted Chat/Voice regressions: **10 passed** in the initial combined
  run. New mounted fixture initially exceeded its10-second turn wait by executing
  eighteen redundant DB lookups; corrected test uses one actual execution and
  seventeen captured abandoned proposals, a relevant negative-learning scenario.
  Runtime timeouts/budgets were NOT increased to hide a failure.
- Final mounted new-window + ordinary Voice close/checkpoint pair:
  **2 passed in18.21s**. Window failure leaves retryable review with one saved page,
  no aggregate/completed prefix. Retry invokes only the remaining window and
  completes all18 assessments. One completed transport and17 not-requested
  proposals remain distinct; no unsupported success/satisfaction is inferred.
  Same full source is visible in both windows, independent consumer marker ends
  completed, and no rule generation is fabricated from unknown assessments.
- Final targeted publication-hook assertion: **1 passed in8.88s**. The actual
  existing publisher is never called on the interrupted prefix, then called
  exactly once with all18 assessments after retry. No installed data was used.

## Remaining limits / next source boundary

These are OUTPUT/assessment windows, not arbitrary character-based SOURCE windows.
The source adapter's100k raw capture and individual20k source guards remain explicit;
each model page must fit100k input/output, and source snapshot/aggregate fit1MiB.
All source must fit per page; it is not secretly dropped or replaced by summary.
Continuation exclusions have20k budget and128 pages/window; exhausted bounds fail.
Existing semantic reconciliation150k bound also remains explicit and can block a
large aggregate while preserving analysis. Full-source bounded hierarchical
qualification/consolidation remains open, along with Voice qualification/recovery
and other audited seams. This does not establish real-provider semantic quality,
latency/cost acceptance or full-build completion.

Official structured-output required-field/schema and incomplete-output guidance
consulted: [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
Existing SDK runner still owns provider completion/refusal handling. JSON schema
does not establish semantic coverage, correctness or satisfaction; application
evidence validation and explicit continuation remain necessary.
