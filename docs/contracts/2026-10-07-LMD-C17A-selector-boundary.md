# LMD-C17A — finite-choice mapping and response validation, offline

Revision r1. Lifecycle VERIFIED (internal same-context review; not owner acceptance). Authority DA-R01–03/10/11 and selector
r3 provider-neutral fields/projection. Outcome: supplied candidate mappings produce
documented request JSON and validated typed choice/fallback, with late-result rejection
and optional no-op, without a provider SDK or executable workflow. This is functional
boundary work, not a live API readiness claim. No active rule/production grant policy.

Owner decision_routing. New exact files decision_routing/{__init__,contracts,selector}.py
under app/vault_runtime; tests/unit/test_decisions_selector_boundary.py. No existing
runtime edit, schema, dependencies, secrets, network, provider/SDK import, composition,
Voice/Chat UI, canonical memory/Background. No directory except decision_routing.
Reuse existing strict JSON parser conventions; no tool catalog dispatch dependency.
Evidence docs/reviews/2026-10-07-LMD-C17A-build-evidence.md. Source official reference
already fetched, no paid entitlement prerequisite for pure mapping/parser work.

Types mirror selector r3 SelectionRequest/InputIdentity/CandidateChoice and result
union. Add frozen ValidationToken(revision,input_fingerprint,context_fingerprint,
candidate_set_fingerprint,capability_snapshot_fingerprint,generation_id).
Caller-provided validity is trusted only from server controller, never browser.
Deadline monotonic float from injected Clock.now(); cancel token exposes is_cancelled.
No live runtime authorization delegated to DTO or server token.

Interface DecisionSelector(transport:DecisionTransport|None,clock:Clock):
choose(request, *, deadline:float,cancellation:CancellationToken,
is_current:Callable[[ValidationToken],bool])->SelectionResult.
DecisionTransport.evaluate(payload:dict, *, timeout_seconds:float)->dict represents
blocking provider completion in this bounded slice, injected fake only in tests.
No worker/thread executor created here. Future C06 owns scheduling/accounting,
C17B owns actual HTTP transport. Type package imports nothing optional.

Choose validates trimmed unique string values and definition version>0, reserved
fallback not used by candidate, nonempty/current fingerprints, immutable candidate
mapping and input identity. Final input requires turn_id; provisional has no turn_id.
Empty candidates ->Fallback(no_candidates) with zero transport calls. Missing
required context (request.complete_context=False explicit field) ->missing_context.
No transport->unavailable. Canceled, expired deadline or false is_current before
call ->canceled/timeout/stale with zero call. Bound input canonical text65536 UTF8
bytes for offline contract; oversize ->InputError before transport, no truncation.
Invalid request is InputError, never a model fallback hiding programmer error.

Build one workflow choice request exactly as selector r3, using canonical string
input and model gpt-6-luna; projection function pure and deterministic. No unsupported
fields (tools, response_format, reasoning, streaming, instructions top-level).
Transport timeout=deadline-clock.now()>0; no internal retries. Catch typed transport
timeout/unavailable only ->Fallback; programmer defects propagate, not successful
empty answer. On return recheck cancellation/deadline/is_current BEFORE decode or
publication. No late result may be passed to consumer. Fake blocking cancellation
does not claim physical HTTP abort or independent scope authorization.

Parse exactly one answer named workflow; refusal ->Fallback(refusal); choice answer
requires string candidate/fallback, finite confidence/probabilities[0,1], exact
expected choice-value set including fallback once each (no bool coercion, duplicate,
missing or unknown). Do not require confidence=selected probability or invent
distribution-sum tolerance; preserve provider values for calibration. Unknown safe
extra response fields ignored, never dispatch. Wrong type/name/structure/nonfinite
->Fallback(invalid_response). Selected ID/version returned from frozen mapping only.
Fallback '__fallback__' ->Fallback(no_supported_choice). Usage/model metadata optional
and bounded/validated, no generated provider request ID or reasoning text.

No low-confidence automatic threshold selected in this slice. Selected is a
classification observation ONLY, not executable instruction; consumer must check
current scope/eligibility/activation/final permissions. Activation remains absent.
This avoids making calibrated active policy a prerequisite for pure typed mapping.

Tests: exact official-shaped JSON fixture; no-op; no candidates/context; fake valid
choice; fallback/refusal; bool vs string; NaN/Infinity/out-of-range probability;
missing/duplicate/unknown option; wrong question; duplicate value/version/reserved
request; input multibyte bound; cancellation/deadline/stale before and after call;
same text changed context/generation; source text injection doesn't change choice
universe or dispatch; no SDK installed needed; no environment credential access;
exact fake timeout/call count no retry. Expected choices independently handwritten
from official type shape, not snapshots generated from mapper under test.

Checks .venv/bin/python -m pytest -q tests/unit/test_decisions_selector_boundary.py;
existing tool/retrieval unit regressions; git diff --check; diff/import audit.
Completion tests reject wrong-but-plausible mapping and late-result behavior;
evidence hashes and diff review required. No real endpoint claim. Stop if new
transport/SDK/schema/permission/default policy needed; re-review rather than add.
Rollback remove unmounted module/tests only if no consumer; preserve all existing
state. C17B live SDK/access and integration remain separate prerequisite-gated build.
## Review correction clarifications (before readiness)

Current type authority selector r3. Canonical candidate-set fingerprint is computed
from ordered value/definition_id/version/description plus selector contract version
with existing canonical_json_bytes; request fingerprint must match computed value.
No reliance on caller assertion for mapping consistency. Context/capability hashes
are server-produced opaque identities, validity callback still mandatory. If clock,
deadline/revision/version has invalid type or nonfinite value ->InputError. No bool
as integer, no bool as probability/confidence; numeric response int/float allowed
only finite range[0,1]. Request/response canonical JSON obey existing1MiB/depth32/
50000-node limits; parser errors ->invalid_response, not raw log dumps. Use existing
strict_json validator without altering it. Document exact complete_context field.
Instructions are code-owned versioned constant, not payload/source-selected.
No publication or cache on Selected; future controller owns current-scope validation.

## Build checkpoint — 2026-10-07

Offline mapping/parser/no-op implemented, unmounted.107 selector tests and181
combined focused units/regressions PASS. No SDK/key/network/transport implementation,
no active routing/learning. [Evidence and exact candidate](../reviews/2026-10-07-LMD-C17A-build-evidence.md).
VERIFIED, not CLOSED; broader suite retains four existing unrelated failures.
All three staged roots C01/C03A/C17A verified. Earlier next-C03B instruction is
superseded by its withdrawal. Current register owns next bounded review; reuse
these actual foundations and do not rebuild the selector boundary.
