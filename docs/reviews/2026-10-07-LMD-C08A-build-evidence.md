# C08A submitted-text runtime — bounded mounted proof

Branch `feature/live-memory-decisions`, base `ea39a6f9da89a2999c4f7e14f686428d2088f480`.
Original grounding unchanged. Actual production composition/API, isolated real
Postgres only, synthetic provider transport; no installed DB/private history or
paid provider touched. This is internal bounded verification, not full-build signoff.

## Actual wiring

`composition.py` injects `ConversationRuntime` after current catalog registration.
`/conversations` authenticated/CSRF routes delegate to its owned API. C03A stores
one immutable submitted final; original model responses, readable returned summaries,
context, tool status, deltas and final/terminal events are durable and bounded.
The shared SDK's required source hook precedes dispatch; failed source/delta sinks
cancel and drain its streamed loop. Stop/closing/deadline/current authority feed
cancellation. Worker accounting remains held through synchronous tool completion.

`ConversationToolRuntime` uses the same interactive identity, catalog, grants and
LocalToolAuthority, with real conversation/turn references in the existing invocation
and result owners. No fake Voice session or direct unclaimed catalog execution.
History rehydrates original proposal/status and actual canonical result pairs as
server-owned contextual data; SQL preflight bounds payload loading, with explicit
compaction-required failure rather than truncation. Startup recovers only exclusive
unowned running claims or never-started submissions older than ten minutes; fresh
submission-to-claim handoff is not an orphan. No model/tool replay on recovery.

## Tests and fixes

- Final three mounted DB/API tests: **3 passed in 20.98s**. Real contacts read,
  actual workspace write, source-before-tool link, full 17k returned summary,
  encrypted-content exclusion, canonical history pairs, HTTP SSE/no Content-Length,
  cursor replay/case-insensitive Last-Event-ID, idempotent Send, changed-text and
  malformed-version rejection, CSRF/auth, active-turn conflict, exclusive-owner
  recovery, Stop, uncaptured-call denial, failed thread startup, stale orphan,
  post-effect capture failure without reexecution and revoked grant/no claim.
- Final focused runner/source/foundation/Background/Voice capture units:
  **54 passed in 2.53s**, including failed-delta immediate cancel/drain.
- Eight existing mounted Voice review/capture tests passed in the earlier grouped
  regression run (53 passed total, two new text tests failed). Those new failures
  exposed a history query using nonexistent `created_at` on existing invocations;
  corrected to actual `prepared_at`. Subsequent final three text tests pass.
- Passive foundation dependency test now scopes only its original four files;
  its allowed imports are unchanged. It does not pretend the new composed runtime
  is another passive identity file.

Official [SDK streaming guide](https://developers.openai.com/api/docs/guides/agents/running-agents)
and installed openai-agents 0.18.3 source inspected for original ModelResponse,
hooks, stream cancellation and draining. No SDK upgrade or alternative provider loop.

## Remaining boundaries (not concealed by backend success)

No frontend Chat certification, multimodal attachment support, Gemini text adapter,
history pagination/compaction, generic memory mutation confirmation, Chat post-session
learning, production live revision/parallel VoiceMem+Decisions mount, qualified rule
activation or complete Background maintenance flow is claimed. Unknown effects and
session-revocation-during-effect still need their expanded production-flow checks.
Actual provider semantics are not established by synthetic transport. C08 parent
and full build remain open. C09 can consume this bounded working backend next.
