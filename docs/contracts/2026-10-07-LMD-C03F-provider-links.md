# C03F — original browser-provider tool proposal links

Prebuild source review, 2026-10-07. Existing provider-event rows retain only hash;
actual BrowserVoiceApp drops response.done/function_call_arguments.done evidence
after scheduling tool execution. Reuse existing authenticated events API, atomic
capture transaction, provider-event owner, tool invocation call ID and review source.
No second ledger/tool observer/agent. Current OpenAI Realtime conversation docs
confirm response.done response.id/output function_call item.id/call_id/name/arguments:
https://developers.openai.com/api/docs/guides/realtime-conversations

Add bounded typed JSONB projection to existing provider-event rows, not full provider
payload/audio/hidden reasoning. Capture original final function-call event and response
completion even without transcript; existing final-transcript path remains atomic.
Persist browser origin explicitly; response/item/call identities are not trusted
server causality or user acceptance. No absent summary may be reconstructed. This
child does not promise readable reasoning from Realtime or adopt GPT-Live.

Frontend sends original completion/call event through existing event route and queues
its write for the existing close acknowledgment. Server extracts/validates allowlisted
identities/status/function call proposals, redacts arguments, bounds size/count, and
rejects event-type mismatch. Exact replay checks original payload hash as before;
legacy empty projection is repaired only on exact replay, never different content.

Review source correlates original proposal to actual invocation by scoped call ID,
only when name matches and candidate is unambiguous. Retain actual executed argument
source separately so normalization/context mismatch can be examined. Unknown overall
coverage and all changing-proposal blocks remain. No timing-based answer/final/context
association. Missing/ambiguous original proposal leaves existing tool_request source.

Tests: typed bounded projector; malformed event/oversize/audio exclusion; actual
production capture optional transcript, exact replay/changed replay, original
proposal + actual tool call -> procedural input, missing/ambiguous handling; failed
capture counts at existing close. Targeted scope only, synthetic executor/test DB.
