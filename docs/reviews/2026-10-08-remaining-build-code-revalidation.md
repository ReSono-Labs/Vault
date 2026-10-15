# Remaining build — code revalidation after C04E

Later C04H bounds continuous completed-turn accumulation; C13D now consumes Chat
source_ref_json for same-identity forgotten-source replay suppression. Full
semantic suppression and oversized individual source handling remain open.
Register r46 controls current status; bounded local deployment proof is in
`docs/evidence/2026-10-08-live-memory-local-deployment.md`. Frozen observations
below are not instructions to duplicate these delivered deltas.

Later implementation notice: C04D2 supersedes this frozen audit's factual Chat
window/continuation absence; see [measured evidence](2026-10-08-C04D2-chat-window-evidence.md).
C04F implements bounded context handoff by reusing Voice, not a new compaction
service; [proof and exact limits](2026-10-08-C04F-session-context-evidence.md).
Active-segment overflow, display pagination and procedural/Voice windows remain.
C04G adds procedural assessment/output windows without dropping source; oversized
input-source windows remain open. [Exact bounds/proof](2026-10-08-C04G-procedural-window-evidence.md).
Register r44 owns current status; observations below describe the pre-C04D2 tree.

Scope: owner's six remaining groups, current working tree including untracked
implementation, branch `feature/live-memory-decisions`. Read-only code inspection;
documentation corrections only. No tests, providers, installed DB, deployment or
historical session access. This report is evidence, not another status authority;
the build register owns lifecycle. No whole-feature absence inferred from old plans.

## 1. Long-running Chat — PARTIAL

Built: immutable final turns/segments, scoped history projection, idle checkpoint
and current-authority dispatcher, independent durable consumer markers/retries,
canonical source provenance and pure bounded source-span partition/validation.
Exact code: `conversation/runtime.py::{review_idle,_review_segment}`,
`runtime_store.py::{end_session,history,consumer_state,review_progress}`,
`memory/analysis_spans.py::{partition_sources,validate_coverage}` and
`memory/chat_learning.py::finalize`.

Missing: `runtime_store.history` still raises bounded-context-compaction errors
above 256 turns, 262144 bytes or event/result limits; no mounted compactor exists.
`ChatMemoryLearning._read` still rejects >256 turns/results and >16384-character
entries. Reviewer still rejects >100000 characters/>32 candidates; checkpoint
still rejects >150000 serialized characters. Planner is not called by review.
No resumable window coordinator, explicit candidate continuation or cross-window
consolidation is mounted. Procedural `chat_source._read` also checks the historical
prefix against 100000 bytes; idle segmentation alone does not solve that limit.
Extend existing checkpoints/model/publication; do not recreate source spans,
idle review, history owner or queue.

## 2. Voice decision learning/recovery — PARTIAL

Built: ordinary Voice conversation, atomic capture, live shared preparation,
canonical factual finalization and independent procedural callback. Exact code:
`memory/voice_learning.py::finalize`, `decision_learning/voice_review.py::finalize_source`,
`composition.py` configured callbacks and C06F shared host.

Missing: `decision_learning/voice_source.py` explicitly constructs coverage
`unknown`, with empty context/feedback/reasoning links and no answer attribution
on observations. It cannot qualify automatic rule publication. Voice composition
has no Chat-style qualified publisher/activation mount. `VoiceMemoryLearning`
finalizes on the close/finalize call; the durable discovery dispatcher searches
Chat segments only. Autonomous Voice review recovery is not implemented by that
Chat dispatcher. Reuse existing capture and callbacks; do not rebuild Voice live
or general factual memory learning.

## 3. Chat tool/provider parity — PARTIAL, narrower than all tools

Built: `conversation_tools/runtime.py` supplies granted catalog definitions and
uses original captured call IDs, current authority and existing once-only ledger;
ordinary shared tools and their existing pending-action flows are NOT absent.
Mail/Calendar already have pending/confirm tool logic; verify each existing
handler before allocating any adaptation. No blanket new confirmation subsystem.

Missing demonstrated code: `memory/tools.py` remember/correct/forget/confirm
handlers require actual Voice session/utterance identities; Chat creates real
conversation/turn context instead. These memory operations need a channel adapter,
not fake Voice rows or weakened confirmation. `conversation/runtime.py::_work`
explicitly accepts only openai/xai; Gemini reviewer support elsewhere is not a
Gemini conversation adapter. Remaining provider parity applies to configured
supported providers, not every possible provider. No new credential/model runner.

## 4. Chat attachments — NOT MOUNTED

Built reusable prerequisite: existing authorized workspace file upload/preview/
storage. Chat submission currently accepts final string input, not typed file
parts. `conversation/api.py` enforces exactly submissionKey/input/history version;
`useConversation.ts` sends that shape; `ChatPanel.tsx` has no attachment tray/model
parts. No Chat staging/extraction/reference lifecycle or actual multimodal model
input is wired in these owners. Extend existing file/storage authority; do not
rebuild upload management or silently publish private drafts as workspace files.

## 5. Rebuild and semantic forget suppression — PARTIAL

Built: rule versions/examples/generations, atomic activation/current pointer,
incremental merge and inactive generation deletion. `decision_learning/rules.py`
has publish/examples/store_vector/drop_inactive, not a retained-session rebuild
workflow. `activation.py::_merge` is incremental catalog merge, not history replay.

Built suppression: `memory/suppression.py` compares normalized content digests or
identity digest plus original transcript-ID overlap; history is retained. Missing:
semantic/paraphrase qualification, procedural/rebuild enforcement and a controlled
session-to-generation reconstruction coordinator. Specific additional seam:
`record_suppression` reads transcript_entry_id, while new Chat provenance is in
source_ref_json with null transcript IDs. That provenance is not currently consumed
by the overlap guard. Do not call exact-digest suppression full semantic protection;
do not rebuild existing confirmed-forget, version or generation infrastructure.

## 6. Historical-session qualification audit — NOT PERFORMED

Built: current canonical source adapters and source snapshots; historical evidence
can exist without qualifying for learning. No scoped O-DA-A report over retained
installed history is present in the inspected current evidence. This code audit
did not access that history and cannot substitute for it. Next task must be
read-only, source/coverage focused, no replay/model/export/publication, using
reviewed authorized access. Keep it separate from new-session capture and rebuild.

## Other stale parent entries corrected

`decision_routing/openai_transport.py::OpenAIDecisionTransport.evaluate` exists and
is the default transport_factory in the mounted shared preparation host. It must
NOT be rebuilt because C17 parent says not READY. Real-provider/account/latency
acceptance remains unproved; transport implementation is not missing.

`composition.py` starts owned IndexedMemoryMaintenance and assigns it to shared
preparation. C13C delivered the indexed runtime/cutover. C07 preference persistence
and Chat toggle are mounted (`useLivePreparation.toggle`, `ChatPanel`). Remaining
parent assurance is not a new setting, vector owner, startup loop or transport.

## Next build boundary

Finish the existing C04D contract for long Chat: bounded context compaction plus
resumable factual/procedural analysis of unreviewed contributions, preserved prior
context and exact source mapping. Reuse C04D1/C04E and existing checkpoints. The
six groups above are not six greenfield builds; implement only missing deltas
after the per-contract source/reuse gate. No implementation authorized by this
audit itself; current owner instruction was audit/update before resuming.
