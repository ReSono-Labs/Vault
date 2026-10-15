# C04E — idle Chat review and independent durable coverage

Owner: review on idle, distinguish saved/not saved from unreviewed. Original
grounding remains controlling. Internal same-context source/reuse review.

REUSE exact Vault root `/home/christian/Documents/Projects/ReSono-Labs-Vault/`:
`app/vault_runtime/conversation/{runtime,runtime_store,runtime_schema,api}.py`,
`memory/chat_learning.py`, `decision_learning/repository.py`, existing worker,
review checkpoints, segment identity and scoped local authority; frontend
`frontend/src/browser-voice/conversation/{api,useConversation}.ts` (hook is .ts).
NEW only idle metadata/discovery and independent consumer progress. No new queue,
worker, model, copied source or memory/decision store.

Selected reversible default: 120 seconds without typing/submission/response
completion, checked by existing 30-second dispatcher (roughly 120–150 seconds).
Draft edits send text-free authenticated activity heartbeat at most once/15s;
activity is not evidence. Submit/completion touch the same scoped metadata.
Only actual traffic arms idle review; no implicit backfill of legacy conversations.

Discovery returns scoped metadata. Resolve current local authority, then recheck
activity/history version under the existing conversation header lock before
sealing through existing end_session. Active responses cannot be sealed. Same
saved conversation continues with a new segment, same history version. Review is
background work, not a user-visible end or tool replay. New activity racing with
discovery cancels that idle checkpoint. No raw unsent draft is retained/reviewed.

Sealed segment captures exact first/last canonical turn ordinal and independent
memory/decision consumer states: not_requested/pending/completed/failed/disabled.
Completed consumer skipped on retry; successful memory survives decision failure.
Existing segment also retains bounded result references/counts: factual checkpoint
segment and stored count; decision review/generation IDs and separate publication/
activation state. GET `/conversations/:id/review-status` exposes the latest 50
scoped segment markers, not copied review payloads. No_change/analysis_only/inactive
are not represented as active learned rules. Detailed source dispositions remain
owned by the original factual/procedural checkpoint rows.
Each source owner retains fingerprint and detailed outputs. Factual checkpoint
adds source IDs and per-source reviewed_no_memory_proposal versus candidate
dispositions; decisions retain original source IDs/observations plus their existing
assessments/proposals and publication checkpoints. Analysis complete is not proof
of publication/activation; segment decision progress advances only after existing
publication gate succeeds. Empty outputs still get completed coverage markers.
Markers cover this segment only; prior history remains contextual, not newly
observed contribution. Failure/source loss cannot advance a completed boundary.

Counterexamples: continuous typing, active tool call, newer turn after discovery,
two dispatchers, expired authority, failed publication, model proposes nothing.
Existing locks/current-source checks and explicit per-consumer state handle these.
Incomplete source stays incomplete, never marked reviewed. Existing long-session
guards remain; idle checkpoints are not full history compaction/windowing.

CONTINUE for this delta. Acceptance: actual mounted idle seal/continuation,
no-op on new activity/running response, independent retry/no duplicate calls,
empty proposal markers, real saved memory marker, CSRF/revocation denial; focused
frontend heartbeat check. No paid models or installed DB. Rollback disables idle
discovery, preserving existing explicit end and checkpoints.
