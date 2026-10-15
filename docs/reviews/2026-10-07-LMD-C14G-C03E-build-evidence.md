# Mounted Voice procedural review and capture acknowledgment — build evidence

2026-10-07, branch `feature/live-memory-decisions`. Bounded production grouping,
not a full release/owner acceptance or whole-flow review. Original grounding unchanged.

## Actual wiring

`composition.build_local_app` constructs `VoiceDecisionReview`, installs additive
schema, and passes its finalizer to existing `VoiceMemoryLearning`. Existing close
and manual finalize invoke memory then independent procedural review. Existing
configured provider/model/credential and OpenAIMemoryReviewer runner are reused;
there is no new memory analysis, credential store, agent identity or goal worker.
`RESONO_VAULT_DECISION_REVIEW_ENABLED=false` detaches the procedural callback.

`voice_source.py` reads canonical transcript/invocation/results and current actual
ToolCatalog with scoped current-authority checks and row locks. The only identity
bridge is metadata in existing conversation/segment tables, scoped to Voice via
FK CASCADE, with its own schema fingerprint. No final-turn/text payload copied.
Source fingerprint is rechecked before durable review completion; exact replay
returns the stored result without another provider call. Erasure cascades the bridge
and checkpoint. Original source mutation changes qualification.

Actual Voice lacks complete original model/context/feedback/all-attempt causality.
Projection labels that coverage **unknown**. Captured server tool request is not
original model reasoning. Unattributed calls have no invented user-final linkage.
Assessment prompt separates tool/context/result correctness and satisfaction;
missing evidence stays unknown. Every changing proposal and publication requires
complete capture; mounted unknown analysis cannot create rules or generations.
Overflow is rejected, not silently clipped into a qualified snapshot.

Authenticated `GET /voice/sessions/{id}/decision-review` returns owned durable
status/assessments with no-store. Close/finalize return content-free review status.
Hashed-ID/count/state diagnostic events contain no prompt, transcript, tool result,
credential or exception text; diagnostic failure cannot fail learning.

## Capture gate

Browser close waits for every queued transcript write, sends actual rejected count
through existing close API; failed promises remain rejected despite immediate error
observation. Existing session transaction stores unknown/acknowledged/incomplete
and bounded integer failures. Incomplete closes session but invokes neither reviewer;
manual finalize and procedural source bypass are blocked. Missing legacy count stays
unknown; zero acknowledges writes only, not semantic/source completeness.

## Verification

Actual isolated Postgres: exact test URL guard before schema fixture reset, synthetic
model executor only; production composition, real credential store/API identity,
ToolCatalog/grants/Contacts invocation/results, source locks and durable checkpoints.
No paid provider, installed DB or retained private session history accessed.

- Initial mounted 3 tests passed after correcting status authority lookup. Extended
  mounted 5 tests passed (30.55 s), including incomplete capture and invalid counts.
- Grouped mounted + existing phase4 regression initially 8 passed/1 failed (39.52 s):
  old exact-response assertion omitted additive `captureState`. Updated assertion;
  final grouped rerun: **9 passed in 37.93 s** (six mounted checks and three existing
  phase4 checks), including removable production composition. No inflated rerun count.
- 57 focused reviewer/outcome/diagnostics/config/existing-memory-runner units passed
  (1.17 s). No broad unrelated suites or actual-provider semantic quality claim.
- 13 focused frontend tests passed (3.83 s); production TypeScript/Vite build passed.
  Browser tests prove settlement helper and close request body/CSRF, not a real
  microphone/provider-browser end-to-end failure injection.

Remaining full-build work: complete trusted capture/context/feedback association,
forget suppression/qualified publication/activation and existing Background goal
scheduling, Chat/text model/tools/UI, actual parallel VoiceMem/live Decisions mounts,
production indexed cutover and final integrated logging/whole-flow review. Nothing
in this evidence declares those delivered.
