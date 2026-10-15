# C04G — resumable procedural assessment windows

Original R12/R13/R22/R23/R32 and owner continuation govern. Internal same-context
source/reuse review: existing `decision_learning/reviewer.py` requires every
point's independently cited outcome/context/tool/satisfaction assessment, but one
output is bounded to32 proposals/100k characters. `voice_review.py` already owns
the bound configured model, analysis checkpoint, semantic reconciliation and
publication. `repository.stage` owns fenced immutable stage metadata. REUSE these
exact absolute files under `/home/christian/Documents/Projects/ReSono-Labs-Vault/app/vault_runtime/`;
no new worker, reviewer identity, queue, publication engine or source store.

NEW small `decision_learning/analysis_windows.py` coordinator partitions OBSERVATIONS,
not arbitrary source text. Each call retains ALL original captured sources,
capabilities and bound existing rules, so later corrections remain visible.
At most16 points per assessment window and32 proposals per output page. Explicit
has_more continuation carries excluded canonical behavior fingerprints. Repeated
or nonadvancing continuation, changed assessments/model, invented citations,
exhaustion and oversized inputs fail before completed publication.

Validated pages are stored in existing review-stage JSON, bound to source claim,
input hash, provider/model and coordinator contract. Retry reuses successful pages;
all assessments/proposals are validated together before existing reconciliation
and completion. Exact same behavior across windows unions original point/source/
example references; semantic near-duplicates still use existing model reconciliation.
No publication before the full bounded aggregate completes. Preserve existing
legacy bounded review behavior; when a legacy call fills32 proposal slots, rerun
through explicit continuation rather than imply that limit proves completeness.

Continuation inputs include actual previously emitted behavior definitions and
fixed assessments, not opaque hashes alone or an expectation of model-side recall.
An immutable plan preserves window mode on retry. Aggregate schema keeps v3 field
shape; only the durable aggregate bound is expanded. Legacy single-call32/100k
limits are still enforced in its runner.

Bounded aggregate may contain up to512 proposals and256 assessments, <=1MiB JSON.
Model pages remain <=100k input/output. Existing reconciliation150k budget remains
explicit: exhausting it leaves analysis saved/incomplete, never falsely complete.
Source fingerprint permits <=1MiB validated snapshot, but existing source adapter
retains its raw capture/individual-source guards. This delivers resumable OUTPUT/
assessment windows; input-source windows above those guards remain OPEN, not
silently summarized/truncated or described as complete session coverage.

Counterexamples: later correction hidden from early window; partial page activated;
duplicate assessment differs on retry; provider changes mid-review; two successful
windows create duplicate behavior; invalid page cached; aggregate exceeds bounds.
Focused synthetic tests and actual mounted isolated-DB interrupted-window retry
must prove no early publication, saved-page reuse and final point coverage.
Voice's unknown coverage remains analysis-only. Rollback retains original source
and existing checkpoints; unsupported large review fails explicitly.

Completion of this bounded child: [focused evidence](../reviews/2026-10-08-C04G-procedural-window-evidence.md).
No full arbitrary-session source-window or parent-build completion is claimed.


## Completion continuation — original source input windows

The existing coordinator now processes snapshots over100k characters through the
shared exact-source-span utility before final assessments. Every original character
is included in a source window. The same configured reviewer selects exact original
excerpts, with original IDs, whole-source hashes and absolute offsets. Every source
window and observation group is examined; explicit has_more continuation prevents a
first32-excerpt result from silently becoming complete. Fabricated excerpts, missing
span acknowledgments, nonadvancing continuation and changed source/model bindings
are rejected before a checkpoint is accepted. Span accounting proves input coverage,
not semantic accuracy; actual outcome assessment and provider evaluation still apply.

Existing review-stage JSON retains source pages and the final verified excerpt view.
No source-copy table, worker, model identity or publisher is introduced. The final
assessment and semantic reconciliation see the SAME cross-window evidence view,
including late corrections; canonical validation/current-source fences still use the
entire original snapshot. Citations to sources with no selected excerpt are rejected.
Small inputs retain their original verbatim path and prior checkpoint bindings.
The existing fenced lease renews during successful bounded steps.

The Chat source adapter now admits <=1MiB raw capture/snapshot instead of rejecting
at100k/20k per entry. Bounded snapshots,256 observations,512 proposals,70k selected
source-view and existing reconciliation budgets remain explicit limits. Exhaustion
fails without publication; this is not an unlimited-session claim. Mounted isolated
PostgreSQL verification processes four original long answers (>100k source), fails
on the second source window, resumes without repeating the first, and completes all
four point assessments. Focused source-window tests also cover late correction,
missing coverage, invented text, nonadvancing continuation and cached replay.
