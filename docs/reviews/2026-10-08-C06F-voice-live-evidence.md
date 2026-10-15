# C06F — Voice live trace and bounded acceptance

Branch feature/live-memory-decisions. Existing Voice startup memory, conversation,
capture, authorized tool dispatch and factual/procedural review callbacks were
already mounted. Missing link was partial speech into the shared controller and
final response release; those are now joined, not rebuilt.

Chain: BrowserVoiceApp's persistent microphone → API-key OpenAI dedicated
transcription sidecar → item-correlated revisions → same ChatPreparationRuntime
VoiceMemStream/ParallelPreparation/worker budget/registry → canonical indexed memory
and Decisions selector → actual Voice final capture → exact-input/current-history,
memory, preference and authority guard or canonical final lookup → quoted data
supplied to existing conversation → response.create. No speculative tool invocation.
Actual Voice rows/transcripts remain authoritative; no synthetic Chat rows.

Official docs fetched October8 through OpenAI Docs:
[transcription](https://developers.openai.com/api/docs/guides/realtime-transcription)
defines gpt-live-transcribe deltas, item IDs and application commit with null VAD;
[VAD](https://developers.openai.com/api/docs/guides/realtime-vad) defines conversation
speech notifications and create_response=false. No GPT-Live conversation migration.

Evidence: 11 existing provider/current-state units; 12 browser checks including
existing BrowserVoiceApp; TypeScript no-emit succeeds. Three isolated DB checks
pass for actual mounted Voice preparation, Chat preparation regression and existing
Voice close/review checkpoint. Extended Voice check passes (10.44s): exact final
reuse, real indexed scoped memory, no partial tool invocation, uncaptured final
denial, Off invalidation/changed-final fallback, ordinary Voice automatic response
preserved when Off, CSRF/revoked-session denial, OAuth sidecar rejected without
substitution, no copied Chat rows or duplicate Voice transcripts. Browser adapter
checks capture-before-response, duplicate response suppression, continued speech,
capture failure and teardown. Providers/embeddings synthetic; exact isolated test
Postgres only. No installed database or paid model calls.

Final safety pass: the existing preparation acknowledgment reports the captured
preference state. The browser closes its speculative transcription channel when
that state is Off or draft preparation fails, without closing the conversation
or suppressing the normal final lookup/response. Four focused browser adapter
checks pass, including this Off transition; TypeScript no-emit succeeds.

Limits: no real microphone/network quality or latency proof; no OAuth sidecar
entitlement. Existing Voice procedural source remains unknown/analysis-only, not
promoted by this live mount. Full-session windows/rebuild/attachments are unrelated
remaining original scope. These checks do not certify the entire build complete.
