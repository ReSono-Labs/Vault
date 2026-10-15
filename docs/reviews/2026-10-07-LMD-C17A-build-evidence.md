# LMD-C17A/r1 — offline selector build evidence

2026-10-07. PASS for bounded offline implementation; VERIFIED, not owner acceptance.
Internal same-context review. Owner requested next reviewed slice only.

## Restart and material gates

C17A READY identity a04ed0f11f84b6580193b70b5a20d59c6aeade5f6074a21d269f43d59432b3dd
and split review957c1bcdb903b12538e2795806dc6343b5bdc3a543b8a3af71a9f09916cb6618
match frozen inputs. Original planning manifest all OK. C01 and C03A implementation
manifests all OK; their intentional existing-runtime edits preserved. No selector
exists in actual code. Authority selector r3, DA-R01–03/10/11, reviewed C17A.
Allowlist three new decision_routing files and one new unit file; no host edit.
Next check exact hand-written JSON mapping/response plus adversarial validity tests.

OpenAI Docs skill used: official guide and create reference fetched again October7.
Choice request/answer shapes unchanged; no live API call. Sources:
[guide](https://developers.openai.com/api/docs/guides/decisions#select-from-fixed-options),
[create reference](https://developers.openai.com/api/reference/python/resources/decisions/methods/create).
Reference choice values can be bool, but this application contract permits strings
only. Responses have optional captured model/usage, no documented request ID or
reasoning summary. No provider ID is manufactured. No SDK/key prerequisite for
pure offline mapping. Existing strict_json.py is the canonical validator, unchanged.

Gate: dynamic immutable definition mappings or provider-generated executable route?
Authority owner mapping/removal requirement, DA-R02/03 and official choice shape.
Select frozen supplied strings -> exact local ID/version plus reserved fallback;
not free-text action generation. Counterexample unknown/bool value resolves a tool
or mapping mutation changes result. Dependents live adapter/controller; CONTINUE
only classification boundary, no permission/execution policy.

Gate: trust late completion, revision alone, or whole server validity identity?
Authority DA-R10/C17A: revision/input/context/candidate/capability/generation token
checked before and after blocking transport. Select whole frozen token and injected
server callback, cancel/deadline before parsing. Counterexample identical text with
new context/generation publishes old choice, or deadline/cancel returns Selected.
Dependents scheduler and final validation; CONTINUE without HTTP abort/quota claim.

Gate: malformed-request fallback, invented probability threshold, or fail-explicit
request validation + provider-response fallback? Authority C17A and reference.
Select programmer InputError; only typed timeout/unavailable caught; no threshold,
probability-sum tolerance or confidence equality. Counterexample malformed mapper
silently appears unavailable, missing probability accepted, or low confidence grants
execution. Dependents C17B and calibration; CONTINUE for diagnostic typed results.

Minimal local record details freeze in implementation: ScopedPrincipalRef carries
server user/workspace/local-session IDs; EvidenceRef carries source ID/kind/authority
and exact authorized text. No auth resolver/new storage. Result identity includes
request/scope/input/phase and validation token. Provider metadata is frozen typed
model/token usage only, no arbitrary raw response or inferred rationale. These
reversible DTO details implement existing r3 fields, not new grants/capture policy.

## Evidence and frozen candidate

Exact candidate: [four-file implementation SHA manifest](2026-10-07-LMD-C17A-implementation.sha256).
Only three new runtime files and one new test file; excludes manifest/evidence,
contract lifecycle metadata and project/change checkpoints. No existing runtime
file changed in C17A. C01/C03A exact hashes rechecked after build: all OK. Earlier
planning/source/READY identities remain historical inputs; their intentional
source/lifecycle changes are recorded per preceding slices, not erased/rehashed.

Environment Python3.13.2, existing `.venv`, branch feature/live-memory-decisions,
HEAD ea39a6f9da89a2999c4f7e14f686428d2088f480. No SDK/dependency/config/database
changes. No provider endpoint/account/key experiment, Docker startup or history read.

| Exact check / command | Expected | Actual / exit | Date |
| --- | --- | --- | --- |
| Frozen planning-input manifest, C17A/review direct hashes and C01/C03A manifests | Current reviewed inputs and prior code | All match / 0 | 2026-10-07 |
| `.venv/bin/python -m pytest -q tests/unit/test_decisions_selector_boundary.py` | Mapping, parsing, races, no optional imports | 107 passed,0.57s / 0 | 2026-10-07 |
| Combined focused command below | Earlier caller/retrieval/conversation behavior unchanged | 181 passed,1.31s / 0 | 2026-10-07 |
| `.venv/bin/python -m pytest -q tests/unit` | Broader diagnostic, no new failures | 443 passed,4 existing failures,13.69s / 1 | 2026-10-07 |
| `git diff --check` | No whitespace errors | No output / 0 | 2026-10-07 |
| Runtime status/import and complete new-file review | Allowlist and neutral direction | PASS; no host import or existing source edit | 2026-10-07 |
| `.venv/bin/python -m pytest -q tests/unit/test_strict_json.py tests/unit/test_background_openai_executor.py tests/unit/test_background_agent_contracts.py tests/unit/test_background_tool_supply.py` | Existing JSON/Background interfaces unchanged | 9 passed,2.42s / 0 | 2026-10-07 |
| `sha256sum -c docs/reviews/2026-10-07-LMD-C17A-implementation.sha256` | Frozen candidate intact | Four files OK / 0 | 2026-10-07 |
| `.venv/bin/python scripts/test_env.py status` | Prior test harness stays stopped | Empty status / 0 | 2026-10-07 |

```sh
.venv/bin/python -m pytest -q tests/unit/test_decisions_selector_boundary.py tests/unit/test_conversation_identity.py tests/unit/test_memory_search_boundary.py tests/unit/test_memory_search_boundary_callers.py tests/unit/test_memory_retrieval.py tests/unit/test_memory_contracts.py tests/unit/test_memory_evidence.py tests/unit/test_scoped_tool_catalog.py tests/unit/test_tool_catalog.py tests/unit/test_memory_adapter_package_contract.py tests/unit/test_workspace_storage.py
```

Initial selector check99 PASS; expanded coverage then107 PASS. No failed new-test
correction or existing-test weakening. Broad-suite failures exactly same four as
recorded and reproduced with baseline service in C01: Mail tool audience,
DocumentsPanel prohibited marker, MCP migration workspace source, workspace_files
prohibited markers. Unchanged affected files; no whole-suite PASS claimed.

## Review of actual implementation

Same-context internal structural/semantic review PASS against frozen candidate,
C17A/r1, selector r3, original owner requirements and official provider reference.
The module validates and projects local types; it does not retrieve definitions,
build a learned tree, authorize scope, call tools or implement model transport.
No new reason to change in host/permissions/memory/Background/Voice owners.
Only shared dependency strict_json validator, not tool dispatch; unchanged limits
1MiB/depth32/50000 nodes. Public results are detached immutable records, no retained
transport dict or mutable probability mapping.

Functional counterexamples tested with independently handwritten wire fixtures:
ordered candidate value/definition/version/description fingerprint recomputed;
changed mapping/order/text and bool/nonpositive versions fail before transport.
Final input requires turn ID, provisional forbids it. Canonical projection labels
phase and quotes source identity/authority/text; source strings cannot alter code
question/options or introduce tools/arguments. This proves wire separation, not
empirical model resistance to prompt injection. Actual model behavior untested.

Request/InputIdentity/scope/candidates/evidence types are frozen; callback receives
whole revision/input/context/candidate/capability/generation token. Context and
capability fingerprints are opaque server-owned references; this boundary does
not verify membership or grant access from an ID. Input SHA matches literal user
text; input JSON sections including context limited to65536 UTF8 bytes, no silent
truncation. This is an internal root bound, not model capacity or final composer limit.

No candidates/context/unavailable/canceled/expired/stale request issues zero calls.
Configured transport gets exactly remaining monotonic seconds; callback time is
included. Typed timeout/unavailable returns fallback without retry; programmer
exceptions propagate. Guard runs before transport, after completion before decode,
and after bounded decode before publication. Canceled/expired/stale completion
wins over even malformed response or typed outage. Tests invalidate each token
field while identical text remains, proving revision alone is insufficient.
No thread/worker/cache or physical abort claim; future controller still validates
scope/current final state and accounts for outstanding provider work.

Response requires one named workflow choice/refusal. Strings only; bool unknown
values, missing/duplicate/extra options, invalid numeric ranges/types/nonfinite,
wrong name/structure, oversized/deep/cyclic/numerous JSON fail invalid_response.
Confidence and probability distribution preserved independently; no sum tolerance,
selected-probability equality or automatic confidence threshold invented.
Reserved fallback is no_supported_choice. Optional bounded typed model/token usage
preserved; safe unknown fields ignored, no reasoning/request ID fabricated.
Selected maps exactly to supplied definition/version and is diagnostic only.

Fresh subprocess imports succeed with optional OpenAI/Agents/psycopg imports blocked
and environment cleared/getenv failing; AST dependency allowlist confirms no SDK,
secrets/network/execution package. Existing core does not import new module.
This is offline removability evidence, not production disable/route fallback proof.

## Current state and next route

C17A/r1 VERIFIED, not CLOSED/owner accepted. C01/C03A/C17A root foundations are
implemented and internally verified; complete live memory/chat/learning remains
unfinished. Existing dirty owner work preserved, no deleted/renamed runtime files,
no commit/deployment. Rollback removes unmounted new package/tests only if unused.

No real endpoint, latency/quality/budget/access/SDK compatibility, active candidate
retrieval/rules, HNSW, input controller, drafts, reasoning capture or reviewer proof
claimed. C17B still needs its separate reviewed transport prerequisites; GPT-Live
is excluded. No invented activation/retention thresholds needed for this slice.

Exactly one next route: Phase02 C03B attributed finalized-evidence capture contract
against verified C03A identities and C17A typed observations. Existing parent C03
draft has stale C08 identity dependency and is NOT permission to implement it.
Re-review atomic source/projection capture, trusted producers, causal linkage,
missing reasoning, erasure/recovery and bounded payloads before next build.
