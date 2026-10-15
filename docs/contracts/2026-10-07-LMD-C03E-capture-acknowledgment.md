# C03E — failed transcript acknowledgment blocks final review

Internal prebuild review r1, 2026-10-07: BrowserVoiceApp.closeVoice awaits
Promise.allSettled but ignores rejections; close API calls memory finalization
regardless. Minimal adaptation to existing capture/close owners, not a new ledger.

Browser reports rejected pending transcript writes on close. Persist bounded
nonnegative integer count and unknown/acknowledged/incomplete transcript-capture
state atomically in existing Voice close transaction. Missing old-client field
stays unknown. Acknowledged means queued transcript writes acknowledged ONLY,
not full causal/tool/context/feedback coverage. Never promote it to complete.

Incomplete capture closes transport/session but blocks BOTH existing memory review
and procedural review in close/finalize API. Explain safe error/status; retain
history. No replay or automatic missing-write repair, invented summary, raw draft
storage or provider change. Existing memory pipeline/model unchanged. Source adapter
also rejects incomplete capture, so bypassing API cannot claim qualified review.
GET procedural status includes actual persisted capture state.

Tests: actual close with failure count performs zero model calls, persists count,
manual finalize remains blocked; invalid bool/negative counts leave session open;
old close stays compatible; browser helper sends actual rejected count, handles
settlement without hiding failure. No installed DB or paid providers. This does
not solve missing original summaries or browser-local/all-attempt causality.
