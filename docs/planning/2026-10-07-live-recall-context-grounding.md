# Owner clarification — one evolving live context for recall and decisions

2026-10-07. Supplements original r11 R02–05/R09/R18/R25/R28/R31 and October7
Decisions amendment; does not replace or edit the original grounding. Owner asks
to keep VoiceMem implementation/planning active and progress tracked, continuing
through logical groups rather than pausing after every small task.

## Explicit owner behavior

LC-R01: While input continues, recall must retain relevant preparation, drop
irrelevant/stale preparation and search again as context changes. Decision
candidates follow the same lifecycle, staying provisional until the turn ends.
This is not a single pre-Send classification or a retrieval done only after Send.

LC-R02: Memory and decisions use the same exact live input/context path in parallel.
One controller owns current scope, utterance/revision and context identity; both
branches consume it. Decisions piggyback on recalled relevant context as it arrives.
Do not build an independent draft buffer, context interpretation, scheduler or
disconnected model loop for decisions. They remain distinct factual/procedural
retrieval outputs and stores, not the same authoritative memory table.

LC-R03: VoiceMem remains part of the retrieval-only adaptation/evaluation scope.
Validate its actual pinned source and reuse the appropriate subset over Vault's
canonical search path. It must not become a second store/ASR/analysis system or
be silently replaced by a differently named generic controller. Existing research
found changed-final, empty-update, stale-ready-result and underlying-thread gaps;
fix them in the reviewed adaptation rather than trusting donor reuse unchanged.

LC-R04: Track real work/status/evidence in the existing register and PROJECT-STATE.
The register is sole lifecycle owner; current checkpoint records progress/next
activity, not a competing status list. Continue through logical delivery groupings.

## Grounded interpretation / material gate

Question: separate decision context pipeline or shared evolving recall context?
Authority: latest explicit owner clarification and original parallel context-aware
preparation requirements. Alternatives: independent route classification; serialized
decision-only-after-all-memory; shared revision/context with parallel retrieval and
context-dependent reconsideration. Select last: reuse common input/interpretation
and memory context, no unnecessary duplicate call. Counterexample: memory branch
sees revised person/invoice/negation but decision stays on its old context/token.
Dependents C05/C06/C15/C17B/C08/C09; CONTINUE planning, exact new interfaces still
require source-backed contracts before build.

Every input mutation invalidates the prior prepared envelope immediately. Retaining
a still-relevant candidate is permitted only after current relevance, identity,
versions and authorization validation, then binding it to the new context/revision;
not carrying forward stale preparation as valid. Changes to memory context also
invalidate dependent selection. Cached work can be reused safely; cancelled workers
still count until actually finished. No speculative tool execution or draft learning.
Final immutable input requires one final current-context validation before use.

## Current proof boundary

C02 provides indexed query prerequisites, not the live loop. Subsequently reviewed
[C05A/C06A component](../reviews/2026-10-07-LMD-C05A-C06A-build-evidence.md) supplies
only unmounted extraction/parallel lifecycle; full C05/C06 adoption is not proved. Planning
must explicitly test continued topic, appended qualifiers, negation, replacement,
delete/empty/ABA, late memory changing route, and final input while jobs remain.
Missing source/compatibility is reported honestly, not a claim VoiceMem already works.

## Owner clarification — live preparation visible in Chat

October7 follow-up after the C08A/C09A checkpoint; original grounding unchanged.
The owner wants the preparation displayed on the Chat page while typing, inside
the chat area, then disappearing on Send. This is a requested UI outcome, not only
an optional external stress-test dashboard. Prove actual live preparation first;
do not create a simulated display or claim the current draft state performs recall.

LC-R05: Show a compact provisional preparation area inside Chat while a meaningful
unsent draft is being processed. Show actual selected/candidate memories and
proposed decisions/tool routes, with observable searching/retained/dropped/revised/
unavailable states where supplied by the shared pipeline. Clearly label it
preparation, not an executed tool call or assistant answer. Explanations must use
actual selection signals or available attributable summaries, never invented
reasoning, hidden reasoning or fabricated confidence. Authorized memory previews
remain scoped; the display does not grant additional access.

LC-R06: Update from the same current revision/context envelope used by parallel
memory and decision preparation. Typing, deleting, replacing or clearing input
must immediately invalidate stale displayed readiness; late results cannot repaint
an old draft. Clear the preparation display immediately when Send is invoked
(including Enter that submits), before acknowledgment/model response; fence its
old callbacks through final handoff. Shift+Enter and IME composition are not Send.
Empty input, scope change and logout clear it too. Next-draft preparation is a new
revision lifecycle, never the previous submitted turn's lingering predictions.

LC-R07: Clearing the on-screen preview is not deleting backend diagnostic evidence.
Retain the already-required scoped, content-free operational trace of preparation
selection/invalidation/final disposition so stress tests can correlate what was
prepared, discarded, used or replaced at final execution. Do not persist unsent
draft text as session evidence or learn rules from provisional candidates. Actual
post-Send model/tool evidence remains separately attributable to the final turn.
The display observes existing preparation; it must not trigger a second retrieval,
model call, selection loop or speculative tool execution merely to render status.

Allocation: existing C06/C06D live lifecycle/diagnostics and C09 Chat presentation,
not a second module, scheduler, learning store or competing progress register.

## Owner correction — upcoming Chat and Voice input, October9

The owner clarified that live preparation searches what is being typed/spoken for
the upcoming message, not past Chat context. This supersedes interpreting
"shared context" as concatenating prior full turns into a retrieval query.
Chat and Voice use the same current-input query and lifecycle. Recalled memories
must be relevant to that input; provisional selection receives those memories
and current input, not an appended history transcript. Existing history-version
and authority checks still fence prepared results. Final answering history and
complete-session learning remain their existing owners' responsibilities.
The configured shared model/credential may evaluate the existing selector wire;
this does not grant execution or constitute native Decisions endpoint acceptance.
Acceptance: continued context, edits/deletions/empty/ABA, late memory changing the
route, Send while jobs remain, delayed Send acknowledgment, subsequent draft and
scope teardown. Show real state before Send; after Send no old preparation remains
visible, while safe diagnostic correlation survives. Planned, not implemented.
