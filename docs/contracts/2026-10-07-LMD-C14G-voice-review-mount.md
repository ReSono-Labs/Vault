# C14G — mounted finalized Voice procedural review

Prebuild internal review r1, 2026-10-07. Existing production VoiceMemoryLearning
and /voice/sessions/{id}/close/finalize call only MemoryPipeline. C14 reviewer and
checkpoint exist but are unmounted. Reuse those exact owners and the canonical
transcript/invocation/result tables, ToolCatalog and scoped credential/model runner.
NEW necessary wiring/projection only; no copied source payload ledger or agent.

Add a reference-only conversation/segment header for a finalized Voice session,
using existing conversation identity tables, linked to actual Voice session with
scoped FK CASCADE. No transcript copied into conversation turns. Scoped source
adapter reads existing rows and compares the exact reconstructed snapshot before
claim/completion; owns active local authority, closed session, current catalog and
row locks. Bound snapshot/model input rejects overflow, never silently truncates.

Existing Voice coverage is NOT complete: missing original causal model items,
browser-local/denied calls, memory context/feedback association and some provider
finality. Review available handling as coverage=unknown, persist unknown/failure
assessments but reject ALL changing proposals. This is an actual production review,
not permission to manufacture learned rules. Permit analysis-only unknown coverage
in the existing reviewer/checkpoint; complete coverage still required for publication.
Unattributed tool calls retain nullable final source and captured request kind,
never relabeled original model reasoning. Current stable ToolCatalog IDs describe
observed tools for analysis, not inferred cross-provider semantic aliases.

Mount independent procedural callback in existing Voice finalization, attempted
even if memory review fails; failure cannot change successful memory publication.
Same configured provider/model execution; resolve credentials once and bind exact
provider used to persisted checkpoint. No new credential store, system identity,
Background executor or goal machinery. Prompt already has explicit goal; eventual
Background scheduling uses existing Goal path, not a new reviewer agent.

GET owned Voice decision-review returns scoped durable state/assessments/coverage;
close/finalize include content-free procedural status. Local diagnostic events use
hashed IDs/counts/state only; no input/result/exception/credential logging.
Schema installed once from composition, no provider call/backfill on startup.
Callback/module may be detached without affecting memory or Voice. Explicit config
switch disables mount; default enabled for requested build/testing. No parallel
queue/daemon introduced. Provider calls occur on existing post-session boundary.

Actual API/DB tests: close -> existing memory and procedural prompts -> immutable
checkpoint -> GET; duplicate finalize no second procedural model call; independent
memory/procedural failures; scope/CSRF; overflow/open session/source mutation blocks;
unknown coverage cannot publish/create examples/activate; erasure cascades metadata.
Real production composition must contain callback, not merely a test-only mount.
No paid provider/installed DB/history use. Original full Chat/live/learning scope
remains and is not certified by this mount.

## Owner-directed shared learning correction — October8

Voice uses its existing session logs in the same learning path as Chat. The
blanket unknown-only restriction above is superseded for finalized sessions whose
existing close acknowledgement reports zero transcript capture failures, whose
user/assistant entries are final, and whose tool observations have matched original
user requests and captured final answers. Missing or ambiguous evidence still remains unknown. No provider
sideband, new capture transport, transcript copy, learner or storage is introduced.

The existing Voice source adapter supplies final answers within the original
ordered user-turn boundaries; ambiguous multiple answers remain unlinked. A
following user turn is a feedback candidate, never automatic approval: the same
analysis model evaluates its text and leaves unrelated or absent feedback unknown.
Captured request metadata remains tool_request, never invented model reasoning.

Production composition shares Chat's existing publisher, catalog activation gates,
semantic reconciliation and example index with Voice. The shared source owner
routes Voice review identities back to original Voice logs for activation and
rebuild checks. Existing factual Voice learning already uses MemoryPipeline and
remains on that owner. The focused mounted test covers original logs, explicit
user feedback, read-only rule activation, shared source reconstruction and retry
without another review. This does not certify real provider acceptance or full
build readiness.

Verification of this correction: mounted Voice review suite10 passed (85.34s);
shared reviewer/outcome/window unit checks53 passed (1.01s); diff whitespace
check passed. Synthetic provider with isolated PostgreSQL only. Work stopped
after this wiring as instructed; no deployment or full-build claim.
