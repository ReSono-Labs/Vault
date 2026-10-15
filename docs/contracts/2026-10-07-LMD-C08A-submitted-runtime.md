# C08A — mounted submitted-text model/runtime and replayable stream

Internal source/contract review, 2026-10-07. Owner requires working Chat/text model,
complete attributable observations and modular actual mounts, not another memory
review or fake Voice session. C03A owns final input, C01 canonical search, existing
credential store selected provider/text model, shared SDK runner, ToolCatalog and
LocalToolAuthority remain authorities. Existing HTTP responses buffer; no streaming
support is presumed. No draft provider/tools run in this child.

## Reviewed source and decisions

Reuse exact Vault sources under `/home/christian/Documents/Projects/ReSono-Labs-Vault/`:
`conversation/{contracts,repository,schema}.py`; `background_agent/sdk_runner.py`
(CAPABILITY_ONLY shared runner; never copy Background executor/goal semantics);
`background_agent/openai_executor.py` function-tool adapter pattern only;
`voice/tools.py` durable claim/replay/failure policy; `tools/{catalog,definitions}.py`;
`voice/credentials.py` existing selected provider/background_access text model as
already used by memory/help; `local_api/{app,server}.py`; `composition.py`.
Official SDK streaming guide fetched; installed 0.18.3 ModelResponse.response_id,
output and RunResultStreaming.cancel(mode='immediate') inspected. No upgrade.

NEW necessary owners: conversation runtime/events/model adapter and conversation
tool adapter; no second grant/provider/ranker/system agent. Chat runs as fixed
interactive VOICE identity, never Background to gain tools. Existing tool claim
policy is adapted to real conversation/turn identity in the existing invocation
owner, not bypassed by a direct unclaimed catalog call. Voice behavior stays intact.

Select SSE over authenticated scoped GET with replay cursor, CSRF POST Send/Stop,
as already proposed by integration plan. Alternative buffered response cannot
provide waiting/text/cancel; new external server/framework is unnecessary. Native
server emitter owns headers/iterator only. Stream disconnect stops viewing, NOT
execution; explicit Stop reaches runtime cancellation. Counterexample: a reload
reruns a stored tool call, or socket disconnect reports an executed write undone.
Disposition CONTINUE for this bounded child; full C08/C09 acceptance remains open.

## Runtime and evidence

Persist final user text exactly once through C03A; no duplicate user-final event.
One active turn per conversation, immutable idempotency key/history CAS. Load
server-owned prior final text/answers, not client history. Context budget overflow
fails explicitly pending reviewed compaction, never silently drops earlier turns.
Final canonical memory search uses existing MemoryService; capture exact selected
memory IDs/content versions/text as context, not learned facts.

Provider resolves current selected connection and its configured text model, same
credential/model source as existing help/memory. Preserve provider, never substitute.
Initial SDK-supported OpenAI/xAI path; unsupported provider returns explicit safe
failure, not fake success. Gemini parity remains a required later adapter.

Shared SDK runner adds optional raw ModelResponse/text-delta/cancel callbacks,
default callers unchanged. Original model observation persists complete readable
summary text (if actually returned), response/item/call IDs and redacted original
tool proposals BEFORE execution; no hidden/encrypted reasoning or clipped-complete
summary. Bounded capture overflow aborts and marks incomplete. Existing Background
observation remains compatible. Source capture failure is fatal before tools.

New canonical conversation events are necessary because no existing Chat response
source exists. Scope/turn FK CASCADE, monotonic sequence, bounded JSON payload,
context/model/proposal/tool status/text/final/error/terminal types; no unsent draft
or duplicate user-input payload. Durable replay reads never execute providers/tools.
Claim/result records remain existing tool owner with real conversation/turn refs.
Current grants/catalog/authority rechecked immediately before invocation. Missing
call ID/original proposal rejects effects; replayed changed args rejects; unknown
writes never automatically repeat. Transport-only tools and currently Voice-only
memory confirmation refuse truthfully until generic confirmation adapter; full
tool parity is not certified by this child.

Runtime work is bounded, no new Background goal scheduler. Explicit Stop/provider
deadline/shutdown cancel actual SDK task; retain worker accounting until underlying
work ends. In-flight uncertain effects remain unknown; no blanket retry. Restart
may mark orphaned turns interrupted only with exclusive ownership proof; no automatic
model/tool replay. Stream events recheck current authority and never contain keys.

## Edits, verification and removal

New logic stays below `conversation/` and `conversation_tools/`; hosts only compose,
authenticate/envelope/delegate/emitter/stop. Narrow existing edits: shared SDK optional
hooks; tool context optional paired conversation/turn fields; LocalToolAuthority
shared claim entry; schema additive nullable real-conversation source references;
C03A optional atomic idle guard; composition/app/server injection/emission.

Actual production composition/API tests with synthetic runner + isolated real DB:
Send -> immutable final -> canonical context -> original model/summary/tool proposal
-> current granted actual handler -> result -> stream/final; same Send no repeat;
changed key/history, concurrent sends, scoped/auth/CSRF, malformed call, denial,
revocation, Stop, failed capture, unknown write and restart/replay. HTTP emitter
test verifies SSE/no Content-Length/reconnect cursor, not just response dataclass.
No paid providers/private history. Existing Voice/Background regression required.
Unmounting runtime preserves canonical source/memory/tool history and Voice;
worker stop is registered in actual application close. C09 UI is next consumer,
not declared built by backend tests. Attachments/live/learning remain allocated.

## October8 completion amendment — channel reuse

Gemini uses the same installed SDK runner/function tools through Google's official
OpenAI-compatible chat-completions endpoint. OpenAI/xAI retain their existing
Responses protocol. No new credential, agent or execution runtime is added.
Provider identity is preserved; supported transport does not certify live account
entitlement or paid-provider acceptance.

Memory prepare/confirm/forget and explicit remember now consume the original
scoped Chat turn and later turn ordinal using the existing pending-action table.
Same-turn confirmation, changed conversation and consumed action are rejected.
Consume plus canonical correction/forget is one transaction; failed publication
leaves the pending action retryable. Chat evidence references the immutable original
submission, never a fabricated Voice transcript. Confirmation source text must fit
the existing16384-character evidence bound so no complete-source claim hides clipping.
Explicit later Chat remember is a scoped exception to the existing digest/source
suppression guard; full semantic changed-identity suppression is still separate.

Display pagination reads final user/assistant text independently from bounded model
history; loading earlier pages does not execute, learn or mutate source history.
Attachments use the amended C03A/C11 binding and actual SDK typed input parts.
