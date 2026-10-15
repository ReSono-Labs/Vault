# C03C — existing capture source revalidation

Read-only code inspection on feature/live-memory-decisions. This is allocation
evidence, not an implementation approval or historical-session qualification.
No database, model, tool replay or donor mutation was performed.

## Feature-by-feature actual sources

| Requirement | Existing owner and actual code | Missing delta; do not duplicate |
|---|---|---|
| Immutable final text | conversation repository/types from verified C03A | Consume existing final identity; no second user-final row |
| Voice provider/transcript atomicity | voice/events.py VoiceProviderEventCapture and voice/repository.py transaction method, verified C03R | Preserve the atomic seam/exact retry; not a new ledger |
| Readable model summary | voice/schema.py provider events retain payload_sha256 only; frontend captures transcript-final events; Presentation sdk_agent_runtime.py `_reasoning_summaries` extracts raw reasoning summary text | Vault does not currently persist readable summaries. Presentation is reference, not Vault wiring; its 2200-character slice is not acceptable complete evidence |
| Provider response/item causality | browser submits providerPayload, but repository persists its hash rather than original response/item IDs | Add only demonstrated missing typed linkage, not full copied provider payload |
| Tool identity, arguments hash, effect and execution state | voice/schema.py existing invocation/result tables; voice/tools.py LocalToolAuthority durable claims | Reuse these records; do not create another tool execution ledger or grant engine |
| Denied/invalid/exception evidence | tools/catalog.py invoke returns before observer for visibility/grant/schema denial; handler exceptions also bypass observer | Explicit outcome capture seam required; current observer cannot prove all-attempt coverage |
| Successful observer durability | tools/catalog.py observer exceptions are swallowed; no set_invocation_observer call site found under app | Existence of observer is not production evidence wiring; durable failure/completeness handling required |
| Ordered source entries | memory/repository.py append_transcript_next uses per-scope/session advisory lock; browser supplies its own increasing entry_index for capture | Reuse server append ownership, resolve shared-producer ordering/idempotency; browser count alone cannot establish full source coverage |
| Evidence metadata | transcript metadata_json exists; transcript_entries projection returns TranscriptEntry without metadata | Add a separate typed source projection over existing rows; preserve legacy DTO/reviewer contract rather than silently changing it |
| Close coverage | BrowserVoiceApp.closeVoice awaits allSettled then closes regardless of rejection; local_api closes session then VoiceMemoryLearning.finalize reviews retained transcript | Rejected writes must mark incomplete/pending, never complete procedural evidence. Close status and coverage are different |
| Draft vs final vs after-the-fact | C05/C06 transient preparation exists unmounted; ToolInvocationContext has tool_call_id and optional utterance but no draft revision/final-turn attribution | Carry server-owned final identity and explicit preparation/selection provenance; never infer causality from timing or reviewer text |

## Exact inspected boundaries

- app/vault_runtime/voice/events.py capture, existing atomic source/transcript seam.
- app/vault_runtime/voice/repository.py record_provider_event_in_transaction.
- app/vault_runtime/voice/schema.py provider-event, invocation and result tables.
- app/vault_runtime/tools/catalog.py invoke and set_invocation_observer.
- app/vault_runtime/tools/definitions.py ToolInvocationContext.
- app/vault_runtime/memory/repository.py transcript_entries/append_transcript_next.
- app/vault_runtime/memory/models.py TranscriptEntry.
- app/vault_runtime/memory/voice_learning.py capture/finalize.
- app/vault_runtime/local_api/app.py Voice events/close routes.
- frontend/src/browser-voice/BrowserVoiceApp.tsx normalized/final transcript capture
  and closeVoice.
- /home/christian/Documents/Projects/ReSono-Labs-Presentation/app/sdk_agent_runtime.py
  `_reasoning_summaries`; inspected read-only, not imported or edited.

No historical corpus was queried; unsupported/absent summaries cannot be
reconstructed. No provider claim was inferred from example code. Before any SDK
summary producer implementation, official OpenAI docs skill/current provider
contracts must be checked; opaque encrypted reasoning is not a readable summary.

## Dependency and implementation split

First bounded child should qualify/project existing scoped sources, with explicit
unknown coverage and trusted-vs-browser origin. This unlocks factual context
without fabricating complete procedural evidence. A later reviewed child owns
producer causality/readable summary capture, all-attempt tool observation and
durable acknowledgement/close coverage. General Chat must consume the same source
contract without a fake Voice session or a second tool authority.

Do not mark the C03C parent READY or mount the C06C adapter with default-true source
qualification. Source qualification, producer capture and complete-review jobs are
distinct responsibilities; keeping them separate does not create new source stores.
