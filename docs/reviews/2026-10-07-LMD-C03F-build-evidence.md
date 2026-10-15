# C03F — mounted original provider proposal links

2026-10-07, same feature branch. Actual source review/contract before edits:
[C03F](../contracts/2026-10-07-LMD-C03F-provider-links.md). Reuses existing capture
transaction/provider rows/tool call IDs and review projection; no second ledger.

Original `response.function_call_arguments.done` and `response.done` are now queued
for existing capture acknowledgment in BrowserVoiceApp, via the real events API.
Transcript fields are optional as a pair; provider-only events never add invented
memory transcript entries. Existing final-transcript atomicity/retry remains intact.
Server allowlist extracts bounded browser-origin response/item/call identities,
status and redacted JSON-object arguments into additive existing provider-event
`evidence_json`. No audio, encrypted content or hidden reasoning retained. Missing
readable summaries remain missing; Realtime is not assumed to expose Responses SDK
reasoning items. Official source:
[Realtime conversations](https://developers.openai.com/api/docs/guides/realtime-conversations).

Existing payload hash still rejects changed replay under existing 403 conflict
mapping. Exact legacy replay can repair only empty additive projection. Source joins
actual invocation by scoped call ID plus exact name, only if original proposal is
unambiguous. Original and executed arguments remain distinguishable; original
source is labeled browser_provider and includes executed-request reference.
Conflicting response identities fall back to captured server tool_request. Final
user/context/answer linkage is not inferred from timestamps. Coverage stays unknown;
no learned publication/activation is unlocked by these links alone.

Verification: 29 bounded projector/existing atomic-capture units passed (0.51 s).
14 focused frontend tests passed (3.48 s); production TypeScript/Vite build passed.
Grouped actual production DB/API run: nine unaffected checks passed; new check had
an incorrect expected HTTP code (409 versus existing 403), corrected without
changing runtime error policy. New original-proposal DB check then passed (8.60 s);
extended exact-legacy repair/ambiguity rerun passed (9.71 s). These are ten distinct
DB checks across the grouped run and corrected targeted rerun, not cumulative counts.
Synthetic executor only, exact isolated test DB, no paid providers/private history.
Frontend tests prove API serialization; no real microphone-provider E2E claimed.

Full capture/learning, readable Chat model summaries, trusted context/feedback/outcome
linkage, maintenance scheduling and live runtime/UI remain open. This is a source
producer/projection child, not complete C03C or full-build certification.
