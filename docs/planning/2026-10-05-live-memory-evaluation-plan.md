# Retrieval quality and useful-response latency

Current document set: [authority map](2026-10-07-live-memory-document-authority.md).
This plan owns its design concern only; original grounding controls requirements,
register controls build status, and historical reviews/manifests are not work orders.

2026-10-07 applicability: [Decisions/evidence grounding amendment](2026-10-07-decisions-api-evidence-grounding.md)
requires Phase01 revalidation of this plan's applicable draft, final-turn, causal
evidence, history coverage, evaluation and provider assumptions. GPT-Live is not
in scope. This notice is not a replacement design or renewed review approval.

Revision: LMD-EVAL-PLAN-r2. Phase 01 candidate. Owns evaluation methodology,
not feature defaults. Authority: grounding r11 R21/R28; numeric gates undecided.

## O1 comparative experiment before committing to a memory implementation

Use an isolated, reproducible synthetic authorized corpus first. A READY
experiment contract must bound assets, dependencies, hardware, dataset, provider
calls/spend if any, and cleanup. Planning creates no harness or database.
Compare existing final-only search, indexed hybrid, and the bounded VoiceMem
factual-retrieval pattern. Different embedding models require distinct frozen
indices; comparing only engines while changing embeddings is confounded.

Version prompts, embedding/index configuration, source commit, corpus and query
stream. Separate tuning cases from held-out acceptance cases. Gold labels cover
required facts, current/historical version and evidence combinations; full
scoped exact search is an ANN comparator, not a relevance gold standard.
Owner-reviewed semantic labels are needed; a model grader alone is insufficient.

| Test group | Material counterexamples |
|---|---|
| Evolving context | Generic prefix becomes specific; mid-sentence topic shift; trailing negation; name/date/amount correction; pause then continued speech |
| Text editing | Delete all, replace selection, paste, IME composition, ABA same text with changed context, rapid Send |
| Knowledge quality | Paraphrase, alias, temporal update, contradictions, multiple supporting facts, ambiguous reference and correct abstention |
| Isolation/lifecycle | Private/shared scope, membership revoke mid-query, forgotten fact, generation switch, preference Off mid-job, restarted conversation |
| Runtime bounds | Slow embedder/search, non-cancellable worker, provider 429/outage, long utterance, concurrent users and repeated failed reranking |
| Voice correctness | OpenAI delta/final correlation, unordered finals, turn commit failure, barge-in and context handoff before response |

Report Recall@k, precision, evidence coverage, relevant no-match/abstention,
unsupported answer and temporal/entity correctness. Report each difficult
slice, not just an aggregate. ANN recall versus exact search is separate from
semantic retrieval quality. Correct authorization is a hard invariant.

Record monotonic timestamps for input arrival, meaningful query scheduling,
embedding, SQL, interpretation, ready context, end-of-speech/Send, final
validation, model first useful content, and first useful played audio.
Client/server timings need clock correlation or same-clock durations; subtracting
unrelated clocks is invalid. Include confidence intervals/sample counts and
p50/p95/p99 where sample size supports them, warm/cold/provider-error cases,
queue wait, requests/tokens/cost, wasted work, peak workers and reuse rate.

A filler phrase or first token is not a useful answer. Speech latency includes
actual playback and endpointing. Compare Live Memory On/Off paired randomized
runs using the same final inputs, load and unchanged endpointing. Separate
quality-equivalent cases from changed answers; no gain purchased by missing
facts. No artificial silence extension to hide retrieval. Short or corrected
queries may correctly fall back and show no benefit; quantify the fraction.

## Decision and acceptance gate

Christian must accept numeric quality, speed, cost and concurrency limits after
O1 evidence; maintainer supplies measurements. Near-perfect retrieval is the
objective, not a current guarantee. Proposed gate structure: quality no worse
than accepted final baseline, demonstrable useful-response improvement, bounded
tail regression/waste and zero stale/scope violations. Exact thresholds are
not silently selected. If no candidate meets both goals, O2/O3 design reopens;
do not proceed by replacing the goal with fast database-only benchmarks.

Rollback/stop: isolate/delete experiment artifacts; retain source evidence.
No production defaults or deployment arise from passing a synthetic benchmark.
Final O9 requires authorized representative audio/model/database operating
results, modular-disable checks and owner acceptance, with live Off retained.

## Separate Chat acceptance additions

R34–37 require real-browser scrolling/input/waiting/streaming/reconnect geometry,
existing active Voice navigation continuity, repeated-history loads with no
model/learning/tool calls, incremental correction publication, actual image/file
input trace and authorized write/unknown-effect recovery. Include attachment
add/remove/readiness changes in live revision tests. UX acceptance checklist is
owned by Chat plan; history/attachment plans own data/ingestion/tool proof. These
are required outcomes, not proof inherited from UI library or old unit baseline.
## October7 decision prediction and learning evaluation

DA-R12: report draft prediction stability, superseded/abandoned work and reuse
coverage separately from finalized-route correctness, actual tool errors, request
resolution and supported usefulness. Do not count unused predictions, duplicate
replays, synthetic paraphrases or provider-confidence values as observed successes.
Freeze candidate sets and available-at-decision evidence; assess missing correct
candidate separately from selector error given a valid candidate set. Split tuning
and held-out sessions to prevent example leakage; report abstention/fallback,
wrong-route rate, confidence calibration and outcomes per class.

Pair no preparation, retrieval-only preparation, and retrieval-plus-selector where
authorized budgets permit, keeping final model/context/corpus fixed. Measure
context wait, selection round trip, final-validation fallback, useful final response,
requests/tokens/cost and wasted work. Provider speed claim is not Vault evidence.
Reviewer fixtures include hindsight, successful-unneeded/error/unknown-effect calls,
missing summary, correction and source injection. Semantic gold/owner acceptance
remain needed; no invented numerical release thresholds. Disable selector and
learner independently and prove canonical memory, history, grants and existing
Voice work; generation deletion must not cascade into final evidence.
