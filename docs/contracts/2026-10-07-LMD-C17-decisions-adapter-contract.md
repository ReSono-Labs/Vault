# LMD-C17 — standalone finite Decisions adapter

AUDIT HOLD: parent includes scope already built in C17A. Do not recreate types,
projection/parser or choose interface below. Transport-only C17B must consume
actual built C17A from the current feature audit; no owner branch lookup required.
Body below is a superseded parent envelope, NOT permission to recreate its paths/
types. Current register/selector plan govern transport-only delta review.

Revision r1; lifecycle DRAFT/DEPENDENCY-BLOCKED, not READY. Inputs original r11,
amendment r2, selector r2, module r4, exact corrected candidate/source manifests.
Outcome DA-R01–03/10/11: provider-neutral selection of eligible supplied versioned
definitions, with validated fallback and no GPT-Live, execution or learning.

Owner decision_routing. Exact new paths: app/vault_runtime/decision_routing/
__init__.py, contracts.py, openai_decisions.py;
tests/unit/test_decisions_adapter.py. Allowed existing composition.py factory/injection
only; pyproject.toml/uv.lock SDK update only after separate compatibility verification.
No changes to voice providers, memory SQL/schema, grant policy, frontend, Background
executor, canonical learner. No optional imports in core startup. New folders only
decision_routing; no generic provider framework. Evidence file under docs/reviews.

Interface choose(request:SelectionRequest, *, deadline:float,
cancellation:CancellationToken)->SelectionResult; immutable types/provider projection
and parsing rules owned by selector r2. Request scope server-derived, distinct
request IDs, exact candidate mapping; fallback '__fallback__'. Disabled no-op returns
unavailable, normal model receives final request. No candidates -> no provider call.
Input text bounded from authorized sources; no unsupported native roles/audio/files.
Credential resolver is existing store behind injected connection/client factory;
secret never returned/logged. ChatGPT OAuth route is not assumed API entitlement.
Timeout/error/refusal/unknown value/nonfinite probability -> fallback. Cancellation
invalidates late result even when HTTP cannot abort; keep worker accounting until
request ends. No provider retries initially, no silent provider/credential swap.

Prerequisites BLOCKING: SelectorPort/evidence identities and C06 controller contract;
calibrated activation policy in C15 for action-influencing use; supported installed
SDK and Agents SDK compatibility proof; authorized account/model access; bounded
real endpoint experiment budget. Diagnostic fake-port tests can be contracted as
a smaller separate slice, not represented as active routing. uv.lock currently
OpenAI2.54.0 versus documented Python3.26.0 minimum; no installation now.

Tests: documented response fixture selects valid definition/version; fallback;
refusal with same question; missing/duplicate/wrong question; bool versus string;
duplicate/unknown choices; NaN/out-of-range confidence/probabilities; removed capability;
missing context; changed candidate fingerprint; edit/delete before completion; deadline
and disabled dependency; adversarial source text cannot become tool name; SDK absent
core startup still works. Existing SDK/Voice/Background tests run after any upgrade.
Real proof: bounded authorized request/response metadata, no secrets/raw unsent draft
export, latency/cost and safe fallback, no tool execution. No paid call made now.

Rollback bind model fallback, stop adapter workers, remove optional adapter dependency
only after import check. Preserve evidence/memory/grants. Stop on invalid dispatch,
compatibility regression, unknown access or missed quota. Completion requires actual
mapped response plus lifecycle/fallback and reviewed diff; model-only mocked success
cannot prove endpoint availability. Christian accepts outcomes; no release or auto-
activation permission from contract shape. No build until revised dependency-ready
contract passes review.
