# C06F — additive Voice live host and controlled final handoff

Authority: original R02–05/R19/R25/R29, LC shared parallel context path,
and October5 transcription plan. Correction, not a replacement Voice runtime.

Observed: Voice startup memory, tools, final capture and review are mounted.
VoiceMemStream/ParallelPreparation are built and Chat-mounted. BrowserVoiceApp
ignores user transcript deltas; only assistant deltas/finals are consumed. Existing
OpenAI session enables automatic response before final retrieval. No live Voice
adapter is mounted. Existing C14G Voice procedural analysis remains analysis-only
because its causal coverage is unknown; that is NOT a missing Voice conversation.

REUSE exact Vault absolute-root files: `live_memory/chat_runtime.py`,
`current_state.py`, `voice/{repository,provider,openai_realtime}.py`,
`memory/repository.py`, `local_api/app.py`, `composition.py`, frontend
`browser-voice/{BrowserVoiceApp,localApi}.tsx` (localApi is .ts).
NEW narrow Voice source/transport adapters only. One preparation loop, worker
budget, vector engine, selector, preference and registry for both channels.
Voice source identity is namespaced and resolves actual Voice rows; never insert
fake Chat conversations/turns or duplicate transcript rows.

API-key OpenAI experimental sessions use a dedicated gpt-live-transcribe
transcription sidecar with null turn detection, reusing the existing microphone
stream and ephemeral-secret provider transport. Existing conversation VAD supplies
commit boundaries. No GPT-Live conversation migration. OAuth sidecar entitlement
is unverified: retain ordinary Voice, no credential/provider substitution.
Disable automatic conversational response only for the mounted supported path.
Capture authoritative conversation final first; validate exact prepared input
against current scope/memory/preferences/history or use canonical final search;
then supply quoted authorized data and release one response. Predictions never
invoke tools. Empty/abandoned/retired turns cannot release a response.

Counterexamples: stale final after continued speech, duplicate final, sidecar
failure, Off, revoked user, wrong workspace, tool-grant change, early response,
navigation teardown. Scope guards must reject each; unsupported preparation falls
back to ordinary authorized final lookup, not stale preparation or tool replay.

Acceptance: synthetic mounted scoped API flow with real test pgvector; shared
Chat regression; browser adapter ordering/duplicates/fallback/teardown. No paid
calls. Actual microphone/provider latency and OAuth entitlement remain unverified,
not implied by synthetic tests. Removing this adapter preserves ordinary Voice.
