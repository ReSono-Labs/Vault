# C04C — durable Chat review recovery

Governing requirement: original complete-session analysis/recovery scope. Reuse
ConversationRuntime's bounded workers, execution advisory locks, sealed segments,
ChatMemoryLearning reviewed-output checkpoint and VoiceDecisionReview checkpoints.
NEW scheduling metadata belongs to existing conversation segments, not another
queue, model, memory repository or tool executor. Donor: this workspace's
`app/vault_runtime/conversation/runtime.py` and `runtime_store.py`.

Seal and queue atomically. A bounded dispatcher resumes only explicitly queued
segments, under their original current local session authority. No historical
backfill. A session advisory lock fences dispatch across processes and releases
on process death. Three attempts, 30-second retry delay; exhausted/unauthorized
work stops until explicit authenticated retry. Successful checkpoints are reused.
Revocation, workspace changes and erasure must not be bypassed. No raw transcript,
credential or exception logging. Existing worker budget also bounds recovery.

Acceptance: restart discovery, no concurrent double claim, retry exhaustion,
authority rejection, and existing factual reviewed-output retry regression.
This slice does not claim Voice recovery or complete-session windowing complete.
