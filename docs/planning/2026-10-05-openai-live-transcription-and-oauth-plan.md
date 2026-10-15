# OpenAI live transcription and scoped OAuth integration

October8 C06F mounts the API-key experimental path with synthetic-provider proof:
dedicated transcription sidecar on existing microphone media, existing provider
ephemeral transport, primary conversation VAD notifications committing the sidecar,
and controlled response release after canonical final capture/context validation.
Existing OAuth conversation remains intact; dedicated OAuth transcription is still
unverified and rejected without substitution. [C06F](../contracts/2026-10-08-LMD-C06F-voice-live-host.md)
does not establish real microphone quality, latency, entitlement or paid success.

Current document set: [authority map](2026-10-07-live-memory-document-authority.md).
This plan owns its design concern only; original grounding controls requirements,
register controls build status, and historical reviews/manifests are not work orders.

2026-10-07 applicability: [Decisions/evidence grounding amendment](2026-10-07-decisions-api-evidence-grounding.md)
requires Phase01 revalidation of this plan's applicable draft, final-turn, causal
evidence, history coverage, evaluation and provider assumptions. GPT-Live is not
in scope. This notice is not a replacement design or renewed review approval.

Revision: LMD-TRANSCRIPTION-r1. Phase 01 candidate; provider compatibility is
conditional, not a claim of working token access. Authority: grounding r11
R02/R05/R22/R24/R29/R31 and latest request to explicitly wire existing OAuth.
Ownership: [module integration](2026-10-05-modular-codebase-integration-plan.md).

## Verified provider contract and current overlap

Official [Realtime transcription](https://developers.openai.com/api/docs/guides/realtime-transcription)
was fetched on 2026-10-05: dedicated transcription session, `gpt-live-transcribe`,
deltas during speech, final on application commit, item_id/content_index matching.
This model requires turn_detection omitted/null; server_vad/semantic_vad are
unsupported. Client/application VAD must decide commit. Delay options trade
transcript quality and latency; there is no fixed134ms provider guarantee.
No word timestamps, speaker labels or confidence are supplied by this model.
Do not configure current server_vad defaults on the dedicated live session.

Current `voice/openai_realtime.py` builds type=realtime conversational sessions.
API-key path creates `/v1/realtime/client_secrets`; ChatGPT OAuth path posts
multipart SDP/session to `/v1/realtime/calls` with the existing bearer token.
That implementation proves wiring exists, not that transcription-only sessions
or `gpt-live-transcribe` are authorized for the installed account. Keep it intact.

Official [Realtime WebRTC](https://developers.openai.com/api/docs/guides/realtime-webrtc)
 documents standard API-key server authentication and ephemeral client secrets.
It does not establish ChatGPT subscription OAuth entitlement for this model.
The page also includes GPT-Live documentation: do not accidentally substitute
`/v1/live/sessions` for the requested transcription Realtime workflow.

## Credential wiring: explicit conditional path

1. Authenticated Vault session establishes active principal/workspace; verify
   conversation ownership and enabled OpenAI connection before session creation.
2. New `live_transcription/credential_adapter.py` calls existing
   `VoiceProviderCredentialStore.resolve(principal, 'openai')`. Resolve existing
   selected/shared or individual scope using the existing policy. Tokens stay
   encrypted in the existing credential store; no new OAuth DB/table/login flow.
3. Existing resolver refreshes expiring OAuth through its existing refresh method
   and persists replacement securely. Do not copy refresh credentials to frontend,
   logs, drafts, memory reviewer, VoiceMem or learned examples. Disconnect/revocation
   invalidates new session creation and tears down affected owned transports.
4. Branch on auth_method. API key uses documented server-mediated SDP exchange or
   ephemeral secret creation with transcription configuration. OAuth uses the
   existing server bearer path only AFTER model/session compatibility is verified
   in a narrowly scoped authorized integration test or authoritative entitlement
   documentation. Do not relabel OAuth as API key or bypass rejected scopes.
5. Return SDP answer/provider opaque session identity, or short-lived client secret
   only on supported ephemeral flow. Never return long-lived OAuth/refresh/API keys.
   Server owns model/configuration; frontend supplies bounded offer and local IDs.
6. Capability status distinguishes supported/unverified/unauthorized/unavailable.
   401/403 yields connection/access status, not endless refresh loops or a promise
   reconnect fixes missing entitlement. Retry only transient setup failures within
   deadline; no silent billable alternate credential/provider selection.
7. If OAuth does not support the dedicated model, dependent OAuth transcription
   is BLOCKED pending provider support/owner choice. Indexed/live text memory,
   chat and complete-session analysis continue. Existing voice stays available;
   API-key transcription is an explicit supported alternative, not automatically
   substituted for the owner's OAuth requirement.

No secret is read or paid call made during planning. OAuth test requires account
access plus separately authorized provider experiment scope. Embeddings have
separate endpoint/model authorization; voice token success cannot establish it.

## Audio and event flow

User presses voice button → new browser transport requests microphone → registers
data/event handlers → SDP offer via authenticated new handler → server credential
adapter/config creates transcription session → answer installed → deltas normalize
into utterance revisions → optional live search prepares scoped memory → application
VAD ends turn and commits once → final transcript replaces partial → final context
validator → existing conversation model/tool authority → response playback.
Dedicated transcription session has no conversation tools/reply model.

Candidate session payload: type=transcription; audio.input.transcription.model=
`gpt-live-transcribe`; audio.input.turn_detection=null. WebRTC media is negotiated
through SDP; do not blindly reuse the raw PCM WebSocket example. If a server-side
WebSocket experiment is needed, use documented audio/pcm24000 with resampling,
bounded append buffers and explicit commit; avoid a second microphone upload on
both transports. Transport choice stays a measured contract decision.

Maintain mapping (provider session,item_id,content_index)→utterance and commit
sequence. Deltas append per documented event; final authoritative text replaces
accumulated draft. Ignore duplicate events/late events from retired epochs. Empty,
failed or missing finals mark incomplete; no fabricated final from displayed
partial. Different-item final order need not equal arrival order. VAD false stop,
continued speech, late correction, interruption and reconnect need explicit tests.
Do not commit while another authoritative auto-response can execute the same turn.

When integrating with existing response audio, choose exactly one response owner:
conversation final-turn handler releases model response after validation. If using
existing conversational realtime session, disable auto response for this feature
path and inject validated context before response.create; prove its independent
ASR/audio timing cannot double-submit or respond early. Preserve audio modality
and output behavior; text-only completion is not a complete voice implementation.
If that controlled handoff is unsupported, freeze a different reviewed response
transport rather than guess. No new TTS vendor/system is selected here.

## VAD, lifecycle and evidence

Application VAD is an owned replaceable port, not code added to BrowserVoiceApp.
Benchmark actual microphones/noise/accents with commit latency separated from
search/response latency. Manual end-turn remains an explicit fallback while VAD
is being tested; numeric endpoint settings are not yet accepted. Playback/barge-in
stops owned response audio, invalidates abandoned preparation and starts distinct
utterance. Never execute partial commands. Close drains final event acknowledgments;
on timeout report incomplete and retain acknowledged final evidence for retry.
Dispose media tracks, data channels, timers, queued jobs and server transport.

Store final transcript and actual tool/assistant outcomes via common evidence
adapter, not raw audio or partial drafts. Reasoning availability for response
model is independently recorded; transcription output is not reasoning evidence.
Live Memory Off stops preparation but transcription still serves voice conversation
and normal final retrieval/session memory analysis still run.

## Required proof / rollback

Positive: actual selected OpenAI model produces deltas before commit; exact final
correlates to one submitted turn; retrieval overlaps speech; valid context reaches
response before useful audio; token never reaches browser except documented
ephemeral secret. Negative: expired/revoked OAuth, unauthorized model, duplicate
commit, unordered finals, permission denied mic, network loss, excessive buffer,
barge-in, memory Off mid-speech and workspace switch. Measure end-of-speech to
played useful audio against same voice request without live preparation. Rollback
removes new adapter/mount; retains existing OAuth store and existing voice path.
## October7 explicit non-Live selector integration

GPT-Live conversational migration/delegation is excluded. Standalone Decisions
consumes normalized text/context through selector port; transcription remains the
separate existing candidate workflow, not a Decisions audio endpoint. No
session.delegation/commentary/thinking event dependencies are introduced. Existing
Realtime response authority must still be controlled before final validation on
experimental path. OAuth transcription entitlement does not establish Decisions
endpoint access; each capability needs independent verification and no silent
credential substitution. Removal leaves current Voice and credential store intact.
