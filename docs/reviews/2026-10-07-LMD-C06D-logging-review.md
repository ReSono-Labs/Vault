# C06D/r1 — postbuild live Decisions diagnostic review

Owner requested backend logs for analysis and review. Exact contract read before
changes. Hooks extend existing shared ParallelPreparation, actual VoiceMem stream
and standalone selector; no new source ledger or learning process.

## Code trace and coverage

| Backend transition | Actual emitted events / fields |
|---|---|
| Draft accepted, including deletions/revisions | revision_accepted with revision/event_sequence and pseudonymous scoped identity |
| Off/IME/empty/insufficient draft | draft_skipped with exact reason |
| Preparation start/reuse check | preparation_started/reuse_checked, attempt ID, retained counts and complete-reuse booleans |
| Parallel retrieval | memory_lookup_complete/decision_lookup_complete, counts; existing actual worker/controller path |
| New memory changes decision context | decision_reconsidered, fresh_memory reason, memory count |
| Publication/late rejection/failure | preparation_ready with counts/elapsed; preparation_stale or preparation_failed, no raw error |
| Final prepared context | final_reused OR final_preparation_rejected followed by final_researched/final_completed; exact current/stale reason |
| Final deadline/cancellation | final_timeout/final_canceled; same original cancellation/drain behavior |
| Teardown/Off invalidation | stream_invalidated when current handle exists |
| Finite selection | selection_started/selection_completed, pseudonymous request/rule IDs, rule version, selected/fallback reason and elapsed |

Default component logger emits schema-versioned JSON locally to stderr, no files,
root logging reconfiguration, outbound telemetry or raw session tokens. Injected
sink/removal preserves same execution. Metadata ID strings are hashed; input text,
input fingerprints, recalled text, provider payloads, tool arguments, secrets,
original reasoning and probability payloads are excluded. These logs describe
operations, not training examples or successful request-resolution evidence.

## Executed checks and findings

Targeted existing stream/adapter/selector plus diagnostic tests verify the paths below.
**160 tests passed** after final rejection-event additions, no failures/skips.
The earlier run passed 159 before the additional changed-final diagnostic case;
these are repeated coverage, not additive counts. `git diff --check` passed.
They cover parallel reconsideration, final reuse, changed-final rejection/fresh search,
stale selector fallback, failure-tolerant logger and privacy sentinels. Initial
compatibility run caught Selected.version vs an incorrect property name; fixed
before closure. The old selector package-file assertion was narrowed to its exact
lightweight core plus allowlisted diagnostics; optional SQL inspection remains
outside the SDK/DB-free core import, which is still tested with optional packages
blocked and credential environment access forbidden. No broad suite rerun.

Internal review PASS for **content-free operational event emission**, not full
production backend coverage. Production live component/Decisions transport remain
unmounted. Therefore these logs do not yet prove real installed sessions execute
the intended routes. Worker-level stale diagnostics may appear more than once
for one revision; group by scope/utterance/revision/attempt/event sequence, never
count each line as a separate prediction or rule success. Stream-level events may
lack attempt ID but retain revision/event sequence. No dedicated retained-file
rotation/analysis dashboard or per-provider cost accounting delivered; stderr is
managed by existing package logging. Source causality/usefulness still belongs to
qualified session evidence, not these logs.

Remaining integrated review must run production Chat/Voice mounts through draft
edits, stale replies, Off, final validation and actual execution evidence, verifying
candidate/reason logs against outcomes. The owner asked for review after wiring;
this bounded review is complete, final production review remains explicitly open.
