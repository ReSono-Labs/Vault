# C05A/C06A/r2 — VoiceMem external-text extraction and shared preparation

[Bounded build evidence](../reviews/2026-10-07-LMD-C05A-C06A-build-evidence.md);
register owns lifecycle. This bounded child is not completion of
C05 comparative retrieval or C06 production controller. Authority original
R02–05/R09/R18/R25/R28/R31 plus LC-R01–04; pinned source/reuse/rights reviewed in
[source review](../reviews/2026-10-07-LMD-C05A-source-review.md).

## Exact build and exclusions

NEW app/vault_runtime/live_memory/{__init__,contracts,preparation,voicemem_stream}.py;
app/vault_runtime/live_memory/VOICE_MEM_LICENSE.txt copied verbatim from reviewed
Apache license; tests/unit/test_live_memory_component.py. Documentation permitted.
No other runtime changes, dependencies, database/API/composition/frontend/provider
calls, durable drafts, tools, learning or Background runtime change. Unmounted.
pyproject.toml package-data entry alone may include the copied license in wheels;
no dependency/version/build-backend changes. This corrects a distribution gap.

Reuse C17A ScopedPrincipalRef/InputIdentity/EvidenceRef/CandidateChoice and C01
RetrievalMatch, not another identity/selector/memory store. InputSnapshot carries
exact text fingerprint, caller-owned context sources/fingerprint and validity
fingerprint (memory/preference/authority/capability/generation dependencies).
Current guard and reuse planner are required injected ports, no permissive default.
Production loaders and relevance implementations remain reviewed follow-on work.

Extract donor VoiceStream external-text methods into VoiceMemStream, documenting
each adaptation. One instance per authenticated scope/conversation/segment/
utterance, increasing revisions; same-revision conflicting payload rejected.
Empty, IME, disabled, abandoned and every edit invalidate the prepared envelope
immediately. Old complete output may remain transient as reuse input only, never
ready evidence. Scope switching requires a new instance; ABA text cannot adopt
an old job. No logs include draft text or exception payloads.

Injected scheduling parameters have no product defaults: debounce, maximum wait,
meaningful-input predicate. One active pump and latest pending snapshot; maximum
wait prevents continuous typing starvation; IME blocks expensive work until end.
Shared WorkerBudget takes explicit global and per-user concurrency. Synchronous
ports run via to_thread ONLY after both permits; cancellation shields worker task
and holds permits until actual completion. Superseded jobs are not canceled and
their results are rejected by exact current snapshot. Shutdown invalidates first,
then permits safe drain; no forced thread-kill claim.

NEW ParallelPreparation uses one snapshot for required reuse validation, then
memory and decision retrieval concurrently. ReusePlan explicitly identifies
currently validated retained candidates and complete branches; absent a real
relevance proof the port must return empty/incomplete, never guess from cosine or
substring. Memory/decision outputs stay separate. Decisions take memory plus the
same conversation context. If fresh memory differs, perform at most one dependent
decision reconsideration before publishing; never publish an old-context route.
No selector/model call is built here and no fictitious learned definitions are
seeded. Future C14/C15/C17B consume these existing types/ports.

Final snapshot requires turn_id and seals this utterance. Exact text/context/
validity match may rebind only after current guard checks final output; changed
final requires current preparation, bypassing debounce. Final has a required
caller deadline; timeout yields no prepared result and invalidates late work.
Cancellation also invalidates without releasing worker permits early. Post-final
edits require another utterance. Guard must check current authorization/epochs
and candidate versions on publication AND ready/final consumption. No prepared
result means ordinary final retrieval/reasoning, not no-memory certainty.

## Review tests / proof limits / removal

Required tests: genuine concurrency barriers, late memory changes decision route,
validated retained candidates vs drop/re-search, delete/empty/ABA/name/negation,
conflicting/out-of-order revisions, cross-scope rejection, continuous updates,
IME/Off, stale guard/revocation, changed/exact final, Send while work pending,
deadline/cancellation, underlying blocked thread capacity, no-op preparation,
shutdown. No provider/vector/quality claim from synthetic callback tests.
Check C01/C02/C03A/C17A/C03R hashes remain unchanged and focused regressions.
No production mount means removal is deleting the isolated module/tests/notices;
no schema/data rollback. Consumer mount requires separate contract proving actual
authorization/epoch/relevance ports, benchmark and erasure/final evidence linkage.

Material alternatives: independent decision scheduler or serialized entire route
versus shared parallel snapshot with one memory-dependent reconsideration. Select
last per LC-R02. Counterexample memory identifies a different invoice while route
remains attached to previous context. Same-context internal candidate review must
pass before READY/build; unit evidence cannot substitute for owner acceptance.
