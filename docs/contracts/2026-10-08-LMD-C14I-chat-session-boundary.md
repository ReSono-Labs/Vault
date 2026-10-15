# C14I — bounded post-segment Chat analysis, resumable history

Correction to C14H integration, not new learning/model design. Original owner goal
is post-session review, not repeatedly paying to review a growing prefix per turn.
Reuse exact existing Vault `app/vault_runtime/conversation/{repository,runtime,
runtime_store,api}.py`, `decision_learning/{chat_source,voice_review}.py` and frontend
`frontend/src/browser-voice/conversation/{api,useConversation}.ts*`. NEW only missing
segment-close adapter and bounded review dispatch. No new queue or source ledger.

Decision CONTINUE: an explicit authenticated/CSRF POST end-session seals the current
idle segment and opens its next continuation segment in the same transaction.
Existing history/turn IDs stay unchanged. No active response is canceled on
navigation. Empty-segment retry returns the previous sealed segment, not another
review unit. A failed/interrupted segment is incomplete, never relabeled complete.
New Chat and switching saved chats request this boundary for the previous idle
chat; plain page hiding/unmount does not invent a session completion.

Dispatch uses existing runtime worker capacity/lifecycle and independent review
claim/checkpoint. Capture the exact segment snapshot before dispatch; later close
does not substitute a newer segment. Source-current rechecks the explicit immutable
segment ID, not whichever segment is newest. Published answers/tools remain intact
on review failure; retry the same ended segment without model duplication. Review
failure/unknown outcomes never create successful procedures. Closed source remains
analysis-only until the remaining qualification gates are actually implemented.

Counterexamples: New Chat cancels an active old turn; resume republishes old source
as new learning; end-session lost acknowledgment creates empty reviews; queue
capacity leak; stale source publication. Tests cover boundary/retry/resume and
mounted existing reviewer with synthetic provider in isolated DB. Internal prebuild
review: CONTINUE bounded lifecycle; durable autonomous retry scheduler and factual
Chat learning remain separate parent work, not implicit acceptance.
