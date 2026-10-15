# Decisions selector — Phase01 candidate

Current document set: [authority map](2026-10-07-live-memory-document-authority.md).
This plan owns its design concern only; original grounding controls requirements,
register controls build status, and historical reviews/manifests are not work orders.

Revision LMD-DA-SELECTOR-r3. Corrected Phase02 candidate, conditional for release.
Authority: original grounding r11 plus LMD-DA-G-2026-10-07-r2. Runtime base
ea39a6f9da89a2999c4f7e14f686428d2088f480; feature/live-memory-decisions.
This document owns selector mapping, not learning/evidence schema, module
ownership, controller, evaluation or permissions. Those remain in owned plans.

## Mapping and candidate contract

Use the proposed decision_routing selector port, with an optional OpenAI adapter.
Application input is authenticated scope, current revision/final-turn identity,
input/context fingerprints, bounded authorized conversation/memory evidence,
eligible immutable definition IDs/versions, capability snapshot and deadline.
Output is selected ID/version or fallback, probabilities, provider/model/request
identity when returned, timings and truthful refusal/error/incomplete status.
Exact Python signatures and response parsing belong to C17 review, not this plan.

Definition retrieval: scoped pgvector example lookup → collapse by definition →
load authoritative version → check conditions, required slots, capability and
current policy eligibility → construct finite choices. Start with one choice
question selecting a workflow; add independent predicates only when a measured
scenario needs them. Do not add a fixed seven-route classifier to every request.
Known deterministic eligible match can bypass the selector; unfamiliar or
ambiguous input falls back to the ordinary conversational model/clarification.

Each supplied value maps locally to exactly one definition/version; descriptions
explain applicability and exclusions, not raw session secrets. Include a fallback
outside the definition namespace. Freeze choice mapping per request. Validate
returned type/value against that mapping; never dispatch provider text as a tool.
Log candidate universe identity so probability is not interpreted across different
candidate sets. Top-k/tuning thresholds remain experiments, not prescribed values.
Required slots are resolved by existing interpretation/model context, not fabricated
from a choice response. Decisions does not generate arguments or explanations.

The adapter uses documented model/input/questions types. Canonical textual
projection distinguishes final user input, context facts and quoted tool evidence;
native audio/tool-role inputs are not forwarded. Bound by model token capacity,
privacy and deadline. Missing required context means defer, not silently classify
without it. Untrusted history/tools cannot redefine question or available choices.
Validate all requested answers; refused/missing/unknown answers, timeout/outage,
uncalibrated confidence or insufficient retrieval produce explicit fallback.
No hidden retries after turn abandonment, no secret exposure, no tool execution.

## Memory and evolving input

[Owner shared-context clarification LC-R01–04](2026-10-07-live-recall-context-grounding.md)
controls: decisions consume the same live revision/context path as memory in
parallel, piggyback on recalled context, and retain/drop/re-search with that context.
Do not duplicate draft state, interpretation or scheduler. Separate procedural
definition/example storage is preserved. No retained route bypasses final validation.

Memory search and candidate-decision retrieval start independently for a meaningful
revision. Candidate eligibility can initially be provisional. Context-dependent
selection runs once required memory/context is ready; a context-free request may
select earlier. If new relevant memory changes context, invalidate its dependent
selection before bounded reconsideration. Never combine answers across revisions.
This is a dependency-aware parallel graph, not mandatory extra serialized calls.
Final validator owns reuse; selector receives no permission to commit a turn.

No valid learned candidates: ordinary model fallback, not a pointless Decisions
call choosing among invented workflows. No full catalog in prompt. API absent:
same fallback. This preserves chat/indexed memory when procedural modules are off.
GPT-Live-specific delegation/commentary/thinking events are not implemented.

## Stage3 decisions (seven-point gates; necessity included)

| Question / current scenario | Authority/evidence and limit | Alternatives | Candidate/function | Counterexample | Dependencies/capacity | Result |
|---|---|---|---|---|---|---|
| Global taxonomy required? repeated procedural routing | DA-R02/03; finite choices per call, not global catalog | Global route tree; dynamic workflows; model only | Dynamic eligible definitions plus fallback, minimal one question | Missing correct candidate forced to nearest | O7/O8, C15/C17; maintainer, budget unknown | CONDITIONAL on retrieval/held-out fallback proof |
| Select before contextual memory? contextual draft | DA-R10; no speed proof | Always early; always serial; dependency-aware | Parallel retrieval, context-gated selector | Person alias changes route after premature reuse | C03/C06/search/evidence ports | CONDITIONAL on race/latency proof |
| Enable endpoint now? owner resumed research | DA-P02, docs available; account/SDK not verified | Install now; plan optional adapter; defer indefinitely | Plan C17 optional adapter, no install/call | Existing SDK has no decisions client | C17 compatibility/access and bounded experiment; maintainer | CONTINUE planning, build unready |

Each item is required by named scenario now for planning, not implementation.
Smaller model-only routing remains fallback; removal tests and held-out evidence
can reject optional API use. No delivery date or recurring cost commitment.

## Delivery blocks / requirement trace

### O-DA-A — qualify historical evidence

Delivery allocation: C10 in the current register, as a separately bounded read-only
task. Learning plan owns the audit procedure. This does not block new truthful
capture or authorize private-history access/export/learning by this allocation.

Scenario/owner: DA-R05–08; Christian needs to know what old sessions can teach.
Entry: authorized scoped read-only connection/export, retained data and redaction
rules; no writes/provider calls. Deliverable: coverage report using the learning
plan audit procedure. Positive/negative: linked outcomes distinguish errors;
missing turns/truncated summaries remain unknown. Evidence: counts/source IDs,
coverage classes and representative redacted cases. Stop: wrong scope/secrets or
unsafe production test fixture. Recovery: stop reads, preserve original data.
Exit: qualified source inventory, not learned/activated rules. C03/C10 adapters
must be specified before publication. Retention policy blocks historical rebuild.

### O-DA-B — truthful finalized procedural evidence

Scenario/owner: DA-R04–07/09/10/12; Christian can inspect how an actual turn worked.
Entry: C03/C08 capture contracts, controller identities, canonical scope/erasure.
Deliverable: learning-plan evidence axes, causal links and independent review
proposals. Tests: edit invalidates old selection; tool-error/unknown-effect/correction,
duplicate replay/crash and hindsight tests. Evidence: attributed event replay and
review citations. Stop on false success, unsent learning or partial-publication
loss. Disable learner; preserve canonical final evidence/memory. Exit: durable
qualified evidence and validated proposals; BP-R02 permits automatic read-only
activation only after current eligibility gates. Writes remain inactive.

### O-DA-C — replaceable finite selector

Scenario/owner: DA-R01–03/10/11; Christian wants known workflow choice without Live.
Entry: eligible definitions, C15 implementation of BP-R02 read-only eligibility
and current grants for active use, C17 SDK/account/
schema compatibility and authorized model experiment budget. Deliverable: optional
selector port adapter, mapping validation and fallback; no execution in adapter.
Tests: valid ID, refusal/missing answer, missing candidate, unavailable capability,
wrong scope, late answer, context change, removed adapter. Evidence: bounded real
endpoint trace plus fake-port adversarial tests; neither alone is production proof.
Stop on authority bypass or invalid final reuse. Disable adapter and route to normal
model. Exit: measured safe routing; release still needs owner numerical acceptance.

### O-DA-D — prediction utility versus execution quality

Scenario/owner: DA-R12/11; Christian evaluates benefit and removability.
Entry: above qualified evidence, evaluation contract and bounded operating budget.
Deliverable: paired final-only versus speculative selection evidence; runtime/module
disable/deletion checks. Positive/negative: lower useful-response delay with correct
context; reject faster-but-wrong routes, false success counts and hidden costs.
Evidence/recovery: evaluation-owned metrics; disable speculation/adapter independently.
Exit: accepted measured benefit or honest rejection, not vendor speed claim.

Sequence: qualify evidence/data → capture/controller contracts → inactive learning
and candidate definitions → optional selector contract → integrated evaluation.
Historical audit need not block new truthful capture. No active learned routing
before activation policy; no API/Live dependency for existing chat/search work.
Next contract allocation remains existing register, no READY contracts created.

## Phase02 exact adapter and capability requirements

Optional module path: decision_routing/openai_decisions.py; imports provider client
only when adapter enabled. choose(request, *, deadline, cancellation) returns
SelectionResult; selection input fields/identity and result union are below. All
types are provider-neutral and owned in decision_routing/contracts.py. No network,
SDK or execution import in contracts. No raw HTTP bypass or broad SDK upgrade to
avoid compatibility review. C17 must pin a supported SDK and validate Agents SDK
compatibility, or return for a separately reviewed transport alternative.

SelectionRequest fields: request_id:str, scope:ScopedPrincipalRef,
input_identity:InputIdentity, phase:provisional|final, input_text:str,
context_sources:tuple[EvidenceRef,...], context_fingerprint:str,
candidate_set:tuple[CandidateChoice,...], candidate_set_fingerprint:str,
capability_snapshot_fingerprint:str, generation_id:str|None,
selector_contract_version:int. CandidateChoice: value:str, definition_id:str,
definition_version:int, applicability_description:str. InputIdentity: conversation_id,
segment_id, utterance_id, revision:int, turn_id:str|None, input_fingerprint:str.
ScopedPrincipalRef is a server-derived authorization reference, not client scope.
Choice values are unique strings only; fallback value '__fallback__' is reserved.
Budget/deadline comes from caller's monotonic clock, not a client timestamp.

Exact provider projection:
model='gpt-6-luna'; input=bounded canonical text; questions=[{type:'choice',
name:'workflow', instructions:versioned applicability/fallback instructions,
choices:[{value:choice.value,description:choice.applicability_description},...
{value:'__fallback__',description:'No supported candidate; ambiguous or missing
required context.'}]}]. Input sections preserve final/provisional label and quoted
source authority; no tools, function args, non-user roles or unsupported API fields.

SelectionResult union: Selected(definition_id,version,confidence,probabilities,
request_identity,usage,model), Fallback(reason,request_identity,provider_metadata).
Reasons: no_candidates, missing_context, refusal, timeout, canceled, unavailable,
invalid_response, low_confidence, stale. Require exactly one workflow answer with
choice type or refusal; validate every string value and finite probability/confidence
in[0,1], no duplicates, selected value present and all expected probability entries.
Reject malformed/unknown values; extra undocumented fields are ignored safely,
not executed. Threshold profile must be calibrated/approved before automatic routing;
without it selection is diagnostic and ordinary model handles final action.
Do not invent an equality between confidence and selected probability. Usage copied
as provider metadata; missing request ID is absent, not manufactured provider ID.
HTTP client timeout bounded by remaining deadline; provider retries disabled for
the speculative adapter initially. Cancellation always invalidates result; worker
quota released only when underlying request ends. HTTP403/429/error -> explicit
fallback, never credential/provider substitution or refresh loop. Original summary
availability is unsupported for Decisions (no summary field), not response failure.

Semantic capability mapping is NEW and not currently present in ToolDefinition.
Proposed read-only CapabilityResolver.resolve(scope, capability_ref) returns current
tool_id/name/schema fingerprint/effect/provider identity or unavailable/ambiguous.
Only explicit reviewed capability mappings are eligible; no LLM equivalence guesses.
Unknown tools may be recorded as provider-specific proposed procedures but cannot
be activated as interchangeable providers. Final ToolCatalog authorization remains
mandatory; snapshot fingerprint is validation evidence, not a permission epoch
that currently exists. Catalog/grants are freshly read under current authority.
Capability aliases, schema fingerprint changes and multiple-provider ambiguity
must be covered by C15 before active use. No catalog overhaul in C17.
## C17A/C17B dependency split

C17A is a reviewed offline mapping/parser boundary with injected transport, no SDK,
credentials or composition. SelectionRequest includes complete_context:bool.
ValidityToken and is_current callback bind revision/input/context/candidate/capability/
generation identity before and after transport completion. Input byte limits are
explicit fail-fast internal contract limits, not production model guarantees.
Selected is an observation, never execution approval; no activation calibration
required to build/test pure mapping. C17B (existing C17 live-adapter allocation)
adds verified SDK transport/access/account/budget and composition after boundary
implementation; active routing still waits C15. No HTTP alternative chosen merely
to avoid SDK compatibility. No raw secret resolution in C17A.
