# Live input, memory, learned decisions, and Vault chat — grounding

Date: 2026-10-04
Revision: `LMD-G-2026-10-04-r11`
Phase: 00 — grounding complete; later planning conditional on named unknowns.
Acceptance owner: Christian. Owner acceptance is not claimed.
Implementation authority: none in this request; review and grounding only.

This is the sole change-specific requirement/decision record. It supplements
[GROUNDING.md](../../GROUNDING.md) for this owner-requested change and is indexed
from [PROJECT-STATE.md](PROJECT-STATE.md). Existing product records remain
valid outside the explicitly reopened scope. Evidence lives in
[the code review](../research/2026-10-04-live-memory-decisions-code-review.md).

Method: [/home/christian/Documents/Projects/drift-protection/AI-PLANNING-PROTOCOL.md](/home/christian/Documents/Projects/drift-protection/AI-PLANNING-PROTOCOL.md),
Stage 1 and Material Decision Gate; Phase 00 prompt. Do not copy the method
into Vault or treat drift-protection's own product state as Vault scope.

## Owner request and authority

Original owner instruction on 2026-10-04 supplies the full conceptual “ReSono
Link — Live Memory, Decisions, and Learning Architecture,” with these later
constraints in the same request:

> “this is all modular. we need to build it with modularity in mind because we are testing.”

> “we need to add and remove each component or workflow as needed if we are wrong or need more. it has to be clean in the codebase!”

> “decisions api is not publicly available yet so we would need to just do a full review and plan, then later adapt to decisions api through documentation.”

> “we also dont know much about decisions schema so this is theoretical.”

> “we would alos need to build a chat area for Vault. i think on the voice screen, we remove the big voice icon, have it be a chat window and have a voice button on the right side of the text input.”

> “real vectors. HNSW. Postgres/pgvector. Relational definitions + JSONB metadata + vectorized examples.”

Immediate instruction: “do a full review and create grounding documents,”
referencing `/home/christian/Documents/Projects/drift-protection/`.

Later owner clarification (same date): inspect
`/home/christian/Documents/Projects/ReSono-Labs-Presentation/app/sdk_agent_runtime.py`
for reasoning-summary capture. Capture it for each voice/text conversation
session as input to the decisions reviewer. Wire a text model into chat;
review typing/deleting dynamically before Send, with relevant memory retrieved
in parallel when context is required. A routing decision alone is insufficient.
Owner emphasized that establishing the proper capture path is important.
This extends the grounding; it does not request an implementation phase.

Further owner instruction: add the discussion of live text edits, code/model
memory selection and latency to grounding. The discussion below is recorded
for planning; saving a recommendation does not establish benchmark results or
freeze a final implementation. Owner said to wait; no build/Phase 01 started.

Owner clarification: “vault is the link personal/business agent package yes.”
This resolves the product mapping.

After the draft/provider question was explained, owner selected: “lets go with
partial drafts are ok for now. we will test and decide later.” Partial drafts
may reach the configured embedding/analysis provider before Send for this
experimental preparation workflow. This is a provisional testing decision;
reassess after cost, latency, quality and edit/cancellation behavior testing.
It does not authorize early tool execution or learning from unsent drafts.

The supplied architecture additionally directs: parallel memory/rule lookup
during meaningful partial voice/text input; debounce rather than every
keystroke; stale revision rejection; final validation before response/action;
known-rule, finite-selector, and reasoning fallback; completed-session review
updating memory and learned behavior; versioned examples and definitions;
confidence evidence; grants separate from learned rules; disposable decision
generations rebuilt from retained sessions; stable capability references;
bounded candidate retrieval/collapse/filtering; persistent database plus local
metadata cache; Link as trusted connectivity, installed agent as intelligence.
The 200–300 ms, 10–20 examples and 3–7 candidates are supplied examples, not
measured limits. Illustrative SQL/JSON is conceptual, not a frozen schema.

Delegated now: inspect code, run relevant non-mutating diagnostics, verify
material primary sources, classify requirements/unknowns, save grounding and
review evidence. Reserved: implementation, migrations, deployment, new agent
identities, paid/provider experiments, final product/schema decisions not
settled in the request, and owner acceptance. Phase 01 is the next workflow
step; a full frozen plan is not being claimed in Phase 00.

## Audience, objective, and observable success

Audience: owner and later Vault/Link planning and implementation passes.
Actual use: a local user asks by voice or text; optional preparation during
input reduces work after finalization; reviewed sessions improve knowledge
and repeatable routing without bypassing permission.

This phase succeeds when the owner can distinguish existing reusable code,
missing behavior, confirmed storage direction, theoretical provider/schema
claims, modularity expectations, and unresolved consequential choices. A later
planner must be able to allocate responsibilities without inferring a new
identity, granting permissions, or freezing the unavailable API.

Future product success requires a working Vault conversation window, shared
revision semantics, authorized indexed retrieval, final-input validation,
safe fallback, separate learning outputs, and independently removable new
components. Faster response and fewer model decisions are hypotheses to
measure against the same requests with preparation disabled.

## Current scope, exclusions, and constraints

Current deliverables: change grounding, code-review evidence, authority/index
links, and documentation change record. No code, new package, schema,
component scaffold, UI mockup, provider adapter, or release.

Future owner-directed scope to be planned: Vault text/voice conversation area;
live revision processing; hybrid memory retrieval; learned decision definitions
and examples; real HNSW retrieval; structural eligibility; model fallback;
completed-session decision learning; rebuilding generations; stable capability
resolution; experimental component/workflow replacement.

Explicitly excluded: fabricating Decisions API documentation; treating an
embedding as executable policy; sending all learned rules to a model; treating
SQL LIKE as semantic retrieval; duplicate memory/credential/grant stores;
new specialist/system agents; new accounting or SMS integrations merely
because the supplied examples mention them; compulsory Link dependency for
standalone Vault; unrelated UI restyle; modifying donors.

Environment: Python Vault runtime, React/TypeScript/Vite Browser Voice,
PostgreSQL/pgvector Docker package, local multi-user/workspace authority.
Free installation does not establish free inference/transcription/embeddings.
No operating budget, hardware resource target, schedule, scale envelope, or
latency threshold was supplied. One owner and this review pass; no delivery
staffing or implementation estimate committed.

## Controlled terms

- **Memory:** existing canonical facts/preferences/episodes/project decisions,
  with R1 taxonomy and evidence. Existing memory type `decision` stays knowledge.
- **Learned decision:** proposed procedural routing/handling definition plus
  conditions, examples, provenance and lifecycle. It is not permission.
- **Decision selector:** finite routing choice, currently a conceptual role.
  **Decisions API** names the deferred provider integration, not a verified wire contract.
- **Partial revision:** provisional text tied to utterance identity/version;
  finalization is a distinct event. Unsent edits are not completed sessions.
- **Prepared context:** expendable retrieval/routing results; must be validated
  against final input and current authority before use.
- **Reasoning summary:** provider-supplied summary captured from actual model
  output, separate from session summary, transcript, encrypted reasoning state,
  and post-session reviewer inference. Availability is model/transport-dependent.
  It supplements actual tool outcomes and user corrections as learning evidence.
- **Generation:** replaceable derived procedural state; retained source history,
  canonical memory and grants are outside its destructive boundary.
- **Capability:** stable semantic operation, resolved to currently available
  authorized tools. A current `tool_id` alone does not prove provider interchangeability.
- **Link:** connectivity/identity/trust/discovery/routing among agents.
  **Vault:** the Link Personal/Business Agent package, confirmed by the owner.
  This product mapping does not establish additional runtime agent identities.

## Premises

| ID | Statement / classification | Provenance and applicability | Validation/status | Accountable owner / dependents |
|---|---|---|---|---|
| LMD-P01 | Owner constraint: new system must be modular and replaceable | 2026-10-04 request | Explicit | Christian / all future components |
| LMD-P02 | Owner decision: PostgreSQL + pgvector + HNSW, relational authoritative rules, JSONB metadata, vector examples | Request | Explicit direction; SQL illustrative | Christian / storage and retrieval |
| LMD-P03 | Owner boundary: Decisions API unavailable; schema theoretical | Request | Provider availability not independently established | Christian + future provider docs / selector adapter |
| LMD-P04 | Owner decision: chat replaces large Home voice control; voice button right of input | Request | Narrow change to existing visual lock | Christian / Home UI |
| LMD-P05 | Fact: real embeddings stored, semantic scoring currently in Python; no inspected HNSW schema | Review, memory schema/retrieval/repository | Source verified; no production DB inspection | Maintainer / retrieval migration |
| LMD-P06 | Fact: final transcripts, memory reviewer, learning on close, tool grants exist | Review, Voice/memory/API owners | Source verified; baseline checks passed | Maintainer / reuse |
| LMD-P07 | Fact: general conversation composer and live draft/rule processing absent from inspected chain | Review, Home/API/contracts | Source inspection; Help chat is support-only | Maintainer / new work provenance |
| LMD-P08 | Fact: PostgreSQL supports required index classes; ANN can underfill scoped results | Official sources in review, checked 2026-10-04 | Documented; deployed version unknown | Maintainer / ANN proof |
| LMD-P09 | Hypothesis: overlap reduces final-to-response latency and repeated model decisions | Owner conceptual explanation | No benchmark | Christian + maintainer / performance acceptance |
| LMD-P10 | Owner decision: partial drafts may reach configured cloud embedding/analysis providers for testing before Send | Explicit owner selection following explanation, r5 | Provisionally allowed; review after testing | Christian / speculative remote processing |
| LMD-P11 | Owner decision: Vault is the Link Personal/Business Agent package | Explicit owner clarification following r3 | Resolved; no separate product runtime inferred | Christian / product packaging and identity |
| LMD-P12 | Constraint: canonical memory learning mandatory; exactly two fixed agents | Existing GROUNDING, contract 20 | Retained except later explicitly bounded change | Christian / removal/fallback and UI identity |
| LMD-P13 | Unknown: retention/deletion, rule promotion, confidence calibration, budgets | Request supplies direction but no governing values | No defaults selected as facts | Christian + maintainer / learning and activation |
| LMD-P14 | Owner requirement: session reasoning summaries feed procedural reviewer; text model and parallel evolving draft/memory preparation required | Later 2026-10-04 clarification | Explicit | Christian / chat, evidence, reviewer |
| LMD-P15 | Fact: Presentation requests summary auto, extracts SDK reasoning items and writes report; Vault already has SDK observation and Background persistence | Review addendum with exact source paths | Source verified; mocked observation checked; no live provider proof | Maintainer / reuse and session capture |
| LMD-P16 | Unknown: reasoning summary availability in each voice provider/model/transport | Inspected Vault voice code and official docs | Responses support verified; blanket voice parity unproved | Maintainer / voice evidence adapter |

## Requirements and acceptance scenarios

Requirements express owner behavior or existing applicable invariants, not
chosen module APIs. Acceptance owner for every row is Christian. Scenario
checks are for later contracts; they were not executed for absent features.

| ID | Required behavior / invariant | Authority | Positive scenario | Negative / failure scenario |
|---|---|---|---|---|
| LMD-R01 | Keep components/workflows separately replaceable; preserve coherent fallback | P01 | Disable decision learning; conversation and memory learning still operate | Hidden imports or shared side effects make disabling one remove all learning |
| LMD-R02 | Normalize voice/text to utterance revisions with final marker | Owner live-input architecture | ASR correction and draft edit both invalidate prior preparation | Provider delta appended as final statement prematurely |
| LMD-R03 | Debounce meaningful changes and bound outstanding work | Owner §§5–6 | Meaningful pause starts preparation; trivial text does not | Every keystroke starts provider/DB work |
| LMD-R04 | Reject stale results, including deletion/abandonment and scope/session changes | Owner revision tracking + existing scope | Old request finishes after edit; result unused | Latest revision number alone reuses another utterance's result |
| LMD-R05 | Prepare during input; validate final request before respond/execute | Owner live/final flows | Exact final request uses eligible preparation | Speech-stop auto-response races ahead of validation |
| LMD-R06 | Preserve canonical hybrid memory retrieval and scoped evidence | Owner memory + existing R1 mandate | Scoped lexical/entity/semantic result answers recollection | New decision subsystem replaces memory taxonomy/reconciliation |
| LMD-R07 | Implement real PostgreSQL HNSW semantic lookup for memory and procedural examples | P02 + owner's semantic retrieval direction | Repository uses index-compatible distance query; index/recall evidence | Add index but still fetch/score all vectors in Python |
| LMD-R08 | Definitions authoritative; examples independently embedded/version-linked | P02 | Paraphrases retrieve same valid definition | Similarity or example text becomes executable instruction |
| LMD-R09 | Collapse examples by rule; enforce database scope plus runtime eligibility | Owner hybrid flow + existing authorization | Valid rules only; required slots and capability checked | Globally retrieved private rule leaks before filtering; ANN underfill called no match without assessment |
| LMD-R10 | Known rules, finite selector, reasoning fallback remain separable | Owner runtime hierarchy + P03 | No valid rule/selector unavailable: authorized model fallback | Fake Decisions endpoint/schema becomes mandatory core dependency |
| LMD-R11 | Revalidate grants, confirmation and tool availability at execution | Owner §19 + ToolCatalog/Voice authority | Prepared SMS still requires current confirmation | High confidence creates grant; tool removed after preparation still called |
| LMD-R12 | Final session evidence records rule/model route, tools, outcomes and corrections | Owner logging | Reviewer can cite successful path and failures | Deleted unsent draft is treated as completed evidence |
| LMD-R13 | Post-session review updates memory and procedural decisions separately | Owner §§14–17 | Decision update fails; accepted memory remains valid; retries avoid duplicates | One output gains arbitrary write authority or reviewer becomes third agent |
| LMD-R14 | Update/merge rules without erasing materially distinct actions | Owner deduplication + final meaning | Related account queries share domain with distinct required slots/actions | Outstanding balance silently mapped to single-invoice status |
| LMD-R15 | Store observed outcomes/confidence; defer uncertain routing | Owner §18 | Low-evidence or ambiguous rule defers | Cosine score or one success treated as calibrated permission to act |
| LMD-R16 | Rebuild derived decision generations without destroying source/core state | Owner disposable system | New validated generation activated; old can be rolled back | Dropping learned generation deletes transcripts, memory or grants; deleted facts resurrected |
| LMD-R17 | Reference stable capabilities, resolve current providers, retain unavailable rules | Owner tool changes | Provider removed: rule retained but execution unavailable | Hardcoded stale tool name bypasses current catalog |
| LMD-R18 | Cache metadata/preparation under scope and version; DB remains authoritative | Owner runtime cache | Generation/tool/grant change invalidates preparation | Cache serves revoked access or obsolete definitions |
| LMD-R19 | Add a separate Chat page; preserve existing Voice page and persistent voice mode across navigation; any Chat voice control is a small right-side composer icon | Latest owner correction supersedes P04 | Independent Chat works; navigating Voice/Chat/Workspace leaves active Voice unchanged | Chat replaces Home, disconnects Voice on navigation, or uses a large microphone control |
| LMD-R20 | Keep Link trust/transport separate from installed-agent intelligence | Owner §24 + local-first baseline | Local Vault operates without Link | Learned routes move memory/grants into Link or require hosted control plane |
| LMD-R21 | Measure speed/cost and degradation truthfully | Owner objective + P09 | Same final request compared with preparation enabled/disabled | Claim instant/free/offline from local vector storage alone |
| LMD-R22 | Capture available reasoning summaries for each voice/text session, linked to model turns, tools/outcomes, with truthful missing/truncated status | Later clarification + P15/P16 | Actual text turn summary reaches scoped session evidence; unsupported voice turn records absence | Reviewer-generated explanation mislabeled as original reasoning; opaque encrypted content parsed as summary |
| LMD-R23 | Decisions reviewer uses captured summaries together with final input, memory references, route, tool results, failures and corrections | Later clarification + R12/R13 | Rationale suggests rule; actual corrected outcome bounds it | Plausible summary outweighs failed tool/user correction or activates a grant |
| LMD-R24 | Wire a text conversational model through existing scoped provider/tool authorities independently of voice transport | Later clarification + R19 | Text-only session responds, uses authorized tools and records reasoning evidence without microphone | Composer sends generic conversation to support-only Help endpoint or requires audio session |
| LMD-R25 | Review current draft dynamically; retrieve context in parallel and revise interpretation as either branch changes | Later clarification + R02–R05 | Contextual draft starts retrieval; edit/deletion immediately invalidates old context/route, then latest meaningful revision prepares | Wait until Send; decide route before memory and never reconsider; empty draft resurrected by late result |

## Live draft handling and memory-selection discussion

Status: behavior extends R02–R05/R25; the ownership split/default below is an
agent recommendation recorded at the owner's request, pending Phase 01 review.

A local draft controller owns the current text and draft/utterance identity.
Typing, deletion, replacement and paste immediately advance its revision and
invalidate preparation. A short debounce starts new meaningful analysis; the
supplied 200–300 ms range is an initial experimental value, not a measured
requirement. Clearing the field clears preparation immediately. Cancel obsolete
work where possible, but reject stale results even if cancellation fails.

Intent/entity/rule interpretation and relevant memory retrieval run in parallel.
Returned memory can refine interpretation only within the still-current draft
and context version. Do not combine a route for one revision with memories from
another. Simple requests can avoid unnecessary long-term search, but saved
location, person, timezone or recent context can still matter.

Send freezes the exact text into its own submitted turn. Validate preparation
against that text, current memory/rule versions and permissions; finish missing
retrieval through the final-input path. Subsequent typing belongs to a new
draft and cannot mutate the sent turn. Preparation does not execute tools or
make an unsent draft learned session evidence. Owner provisionally allows
configured-provider processing of partial drafts for testing (P10/D06/U02).
Sending an old draft cannot be undone by deleting it locally; invalidate its
results regardless, and reassess this policy after the experiment.

### Proposed code/model ownership

| Task | Recommended owner | Planning boundary |
|---|---|---|
| Revisions, debounce, cancellation and stale-result rejection | Code | Correctness must not depend on a model following revision instructions |
| Explicit names/IDs and recent-turn references | Code where sufficient | Ambiguous entity resolution may still need model/context help |
| Ambiguous intent and contextual reference interpretation | Small model when needed | Bounded, replaceable; no model call required for every edit |
| Semantic query embedding | Embedding model | Remote provider adds RTT/cost; local storage does not mean local inference |
| Nearest candidate retrieval | PostgreSQL/pgvector HNSW | Model embedding represents meaning; database selects candidates |
| Membership, scope/visibility, lifecycle and embedding compatibility | Code at repository boundary | Apply before candidate exposure; models cannot authorize access |
| Combine lexical, semantic, entity and recent-session matches | Code | Ranking/limits need quality tests; scores are not action confidence |
| Resolve difficult candidate relevance/ambiguity | Optional model reranking | May improve quality but adds a model round trip; removable component |
| Final preparation validation | Code, with model interpretation where necessary | Freeze sent turn; recheck current authority and semantic match |

Recommended starting point: code-driven hybrid retrieval with parallel
lexical/entity and vector lookup; optional model interpretation/reranking only
when ambiguity warrants it. Keep model reranking off the default path initially
and evaluate it. Retrieval exposes authorized candidates with relevance scores,
memory identity/version and provenance; interpretation/reranking sits above that
boundary and can be replaced without altering storage or authorization.

For “What did we decide about Link federation?”, explicit topic/entity plus
lexical/vector lookup can start directly. For “What did we decide about that
thing John mentioned?”, recent conversation context and model interpretation
may be necessary to formulate a useful query. Keyword-only matching misses
semantic/contextual relationships; a model selecting all memories on every
revision creates avoidable work. Neither tradeoff is resolved by embeddings
alone: embedding generation is model-based, not final memory selection.

### Latency and cost hypotheses

Speculation adds total processing but may reduce the delay after Send by
overlapping preparation with typing. Code/database filtering avoids an extra
selection-model round trip; embeddings still take time, and optional model
interpretation/reranking adds processing and potentially network latency.
No latency reduction is guaranteed or measured by this documentation.

| Timing case | Expected effect to validate |
|---|---|
| Relevant preparation finishes before Send | Less remaining retrieval/interpretation work after Send |
| Send arrives while necessary preparation is running | Wait for remaining required work or complete it through fallback |
| User changes meaning/deletes input | Earlier work may be discarded; resources consumed without helping final response |
| Excess speculative work or simultaneous users | Provider/CPU/database contention can make final response slower |
| Ambiguous candidates need model reranking | Additional latency may be justified by better contextual accuracy |

Compare preparation enabled/disabled for the same finalized requests and
comparable load. Measure Send-to-first-useful-response (not merely first token),
total provider cost, discarded work, relevant-memory/answer quality and final
request latency under contention. Include short drafts/quick Send, substantial
edits, empty drafts, ambiguous references and provider failure. Do not report
database latency alone as end-to-end speed or speed gains bought by incorrect
memory selection as success. Budgets/thresholds remain U08.

## Material Decision Gate traces

Each numbered entry below completes the protocol's seven points. These are
grounding interpretations; they do not freeze a schema or module design.

### LMD-D01 — Phase and authority

1. Question: implement the supplied concept now, or review/ground it?
2. Authority: final request explicitly says review and grounding; Phase 00 method. Conceptual “want Codex implementing” describes later desired behavior, not a READY contract.
3. Alternatives: immediate build; full frozen plan now; grounding then planning.
4. Selected: complete code review and grounded requirements now; no implementation.
5. Counterexample: creating empty decision packages or migrations as “documentation.”
6. Dependents: all code/UI/schema changes and later Phase 01.
7. Result: `CONTINUE` for this phase; later stages deferred.

### LMD-D02 — Storage direction versus schema commitment

1. Question: is Postgres/pgvector/HNSW selected, and is sample SQL final?
2. Authority: explicit real-vector storage direction; schema is theoretical. Official sources establish mechanisms, not local implementation/latency.
3. Alternatives: JSON-only matching; provider-specific final schema; hybrid direction with schema unresolved.
4. Selected: retain hybrid storage requirement; defer exact DDL, embedding identity/dimensions, generation links and index layout.
5. Counterexample: unconstrained vector index DDL or globally unique decision key treated as production-ready without scope/version analysis.
6. Dependents: repository, migration, candidate selection, cache.
7. Result: `CONTINUE` for direction; `CONDITIONAL` for concrete schema.

### LMD-D03 — Future Decisions API

1. Question: must the unavailable provider API govern today's local schema?
2. Authority: owner says schema unknown and adaptation later through docs. No provider contract verified.
3. Alternatives: invent API; freeze local representation as provider schema; keep provider-specific details deferred.
4. Selected: required selector behavior is conceptual; no endpoint, SDK, payload, latency or confidence contract asserted.
5. Counterexample: tests pass against a guessed schema and claim official compatibility.
6. Dependents: finite-selector adapter, schema translation, provider readiness.
7. Result: `CONDITIONAL`; published docs required before provider integration, not before recording independent requirements.

### LMD-D04 — UI visual authority

1. Question: does the latest request reopen the locked Home screen?
2. Authority: explicit remove-large-icon/chat/right-hand-voice-button instruction; existing Browser Voice visual lock.
3. Alternatives: refuse all visual change; general redesign; narrow Home change.
4. Selected: record narrow Home/composer change within existing visual primitives; implementation deferred.
5. Counterexample: new branding/navigation/theme claimed necessary to add chat.
6. Dependents: Home presentation, text backend, transcript/voice integration, visual evidence.
7. Result: `CONTINUE` for stated UX requirement.

### LMD-D05 — Modular removal versus mandatory core

1. Question: may experimentation silently remove canonical memory or authorization?
2. Authority: latest request requires add/remove components; existing grounding requires canonical learning and scoped permission. Latest request does not define supported defaults after removal.
3. Alternatives: disable all core by inference; prohibit experimentation; retain invariants and leave disputed supported defaults unresolved.
4. Selected: require independently replaceable experimental behavior, preserving canonical data/security; production removal of mandatory learning remains unresolved.
5. Counterexample: disabling learned rules disables user memory or grants, or removes the only safe final-input path.
6. Dependents: configuration, fallback/removal acceptance, product defaults.
7. Result: `CONTINUE` for experimental modularity; `CONDITIONAL` for mandatory-core disabling.

### LMD-D06 — Partial input and external authority

1. Question: does preparation authorize cloud draft disclosure or early tools?
2. Authority: owner authorizes retrieval/preparation and separate finalization/permission; after explanation explicitly permits partial drafts for now, with testing and later reassessment. Existing embedder is remote.
3. Alternatives: transmit/call tools by inference; disable all local preparation; record unresolved disclosure and keep speculative execution outside authority.
4. Selected: allow partial draft embedding/analysis through configured providers for testing before Send. Retain revision invalidation, final validation, bounded work and no pre-Send tool execution/learning. This provisional choice may change after evidence.
5. Counterexample: deleted text's late result affects the sent turn, becomes learned evidence or triggers a tool action; test reveals unacceptable cost/latency/quality and the provisional policy is not reassessed.
6. Dependents: embeddings, routing models, transcription choices, logs and settings.
7. Result: `CONTINUE` for experimental cloud-draft preparation; policy remains provisional and subject to post-test owner decision. No implementation started in this documentation change.

### LMD-D07 — Product and agent identity

1. Question: is Vault being renamed/replaced by a Link Personal/Business runtime?
2. Authority: request names both; existing Vault has two fixed identities and optional Link. No packaging/identity replacement instruction.
3. Alternatives: create two more agents; rewrite Link connector as intelligence; preserve Vault scope while recording mapping question.
4. Selected: owner subsequently confirmed Vault is the Link Personal/Business Agent package. Preserve existing runtime identities and Link/intelligence separation; no separate implementation inferred.
5. Counterexample: adding an agent selector/registry because conceptual examples mention specialist routing.
6. Dependents: cross-repository ownership, installer/package, role labels.
7. Result: `CONTINUE`; product mapping resolved by explicit owner clarification in r4.

### LMD-D08 — Learned generations and source lifetime

1. Question: does rebuildability mean keep every session forever and replay deleted knowledge?
2. Authority: owner requires source history preserved during generation disposal; baseline requires deletion/forgetting. Neither settles retention lifetime.
3. Alternatives: permanent raw history; delete source with each rebuild; preserve retained history independent of generation and honor deletion policy.
4. Selected: preserve retained source/core during rebuild; retention and privacy-safe reconstruction require explicit later resolution.
5. Counterexample: forgotten person/fact appears again after replay.
6. Dependents: session logging, evidence links, learning, rebuild/rollback, export/deletion.
7. Result: `CONTINUE` for separation; `CONDITIONAL` for lifetime/replay policy.

### LMD-D09 — Reasoning evidence and donor reuse

1. Question: what is captured, and what does the Presentation path prove?
2. Authority: owner's explicit clarification; Presentation `_run_config`, `_sdk_items_json`, `_reasoning_summaries`, report output; Vault `sdk_runner._observe` and `RunProgressRecorder.reasoning`; official reasoning docs. Sources prove summary extraction, not every voice model's support or a complete rationale.
3. Alternatives: copy full builder/reviewer runtime; fabricate retrospective reasoning; reuse capability-only summary extraction and distinguish missing evidence.
4. Selected: summaries from actual conversation model turns are reviewer input alongside observed results; reuse existing Vault observation first, inspect bounded Presentation helper if needed. No Builder/Reviewer identities imported.
5. Counterexample: rule learned from summary saying success while tool failed, or voice rationale invented and presented as provider output.
6. Dependents: text-model wiring, voice transport evidence, session log, decisions reviewer and provenance.
7. Result: `CONTINUE` for text capture pattern/requirement; `CONDITIONAL` for voice availability and session integration.

### LMD-D10 — Dynamic context before Send

1. Question: is draft processing only routing, or parallel context-aware interpretation?
2. Authority: latest owner clarification explicitly requires typing/deleting review, dynamic change and parallel relevant memory; earlier debounce/revision requirements.
3. Alternatives: route once; defer all retrieval until Send; parallel provisional routing/retrieval with revision-bound reconsideration.
4. Selected: require evolving interpretation plus context retrieval, allowing simple requests to skip unnecessary long-term lookup. Concrete scheduler/model APIs remain Phase 01 decisions. Every mutation invalidates old results even while the next search is debounced.
5. Counterexample: weather draft changes to “what did we decide about…” but earlier no-memory route survives, or late memory changes another revision's route.
6. Dependents: draft controller, memory retriever, route selection, final-input validation, cost/latency and cancellation.
7. Result: `CONTINUE` for required behavior; D06 now provisionally allows configured-provider draft processing for testing.

### LMD-D11 — Hybrid selection and latency recommendation

1. Question: should code or a model select memory, and does speculative retrieval reduce latency?
2. Authority: owner asked to preserve this discussion; existing vector/storage direction and scoped-retrieval requirements. Code inspection proves current owners; no benchmark proves proposed speed/quality.
3. Alternatives: keyword-only selection; model selecting memories every revision; code-driven hybrid candidates with optional model interpretation/reranking; unresolved defaults pending measurement.
4. Selected: record hybrid/default-no-reranking as a recommended test starting point, not accepted implementation. Overlap may hide latency; additional processing may also hurt it.
5. Counterexample: optional reranking silently becomes required on every edit, or faster first token with irrelevant context is claimed as successful latency reduction.
6. Dependents: retrieval interfaces, draft scheduling, model budgets, quality/performance tests and final-input fallback.
7. Result: `CONTINUE` for documenting behavior/tradeoffs; `CONDITIONAL` for final ownership/default choices and performance claims until planning and evidence.

## Unknowns, accountable owners, and affected work

| ID | Question / evidence needed | Owner | Dependent work / status |
|---|---|---|---|
| LMD-U01 | Resolved: Vault is the Link Personal/Business Agent package | Christian, explicit clarification in r4 | Product mapping settled; no shared-runtime extraction required by this clarification |
| LMD-U02 | Resolved for testing: partial drafts may reach configured embedding/analysis providers before Send; owner will reassess after tests | Christian, explicit selection in r5 | Experimental preparation may use providers; permanent product/privacy defaults are not frozen |
| LMD-U03 | Actual provider partial/final event semantics and response/context control? | Maintainer, current provider docs | Voice adapter and finalization contract; investigate in Phase 01 |
| LMD-U04 | Published Decisions API schema/access/pricing/capabilities? | Provider docs + Christian | Provider integration deferred |
| LMD-U05 | Supported toggles/defaults; may existing mandatory learning be disabled? | Christian | Production configuration/removal; conditional |
| LMD-U06 | Rule promotion/activation, ambiguity/confidence evidence and allowed effects? | Christian + maintainer | Learned execution readiness; no automatic activation criteria frozen |
| LMD-U07 | Session retention/deletion and replay after forgetting? | Christian + maintainer | Logging/rebuild/backup; conditional |
| LMD-U08 | Scale/hardware/budget, embedding latency, concurrency and acceptable speed/quality? | Christian + measured evidence | Performance gates; no schedule/numeric SLA |
| LMD-U09 | Installed pgvector version, index-compatible dimensions/query, scoped recall? | Maintainer, isolated test DB | Storage readiness; floating image not version proof |
| LMD-U10 | Chat session end, history/resume, voice/text switching and overlapping submissions? | Christian + inspected reuse | Conversation lifecycle; must preserve final-input and evidence invariants |
| LMD-U11 | Reusable donor code for new functions and public-release rights? | Maintainer + owner where rights unresolved | NEW classification/copy contracts; no exhaustive donor absence claim |
| LMD-U12 | Durable review retry and partial-publication recovery? | Maintainer, fault/restart evidence | Learning publication; source concern in review, no fix performed |
| LMD-U13 | Which configured voice/text models expose summaries, how are turns correlated, and what absence/truncation states are required? | Maintainer + official provider docs | Session reasoning capture; known text pattern, voice support unresolved |
| LMD-U14 | How does newly returned memory revise provisional interpretation without mixing draft/context versions or unbounded model calls? | Maintainer, bounded scheduler/model evidence | Parallel draft preparation; required behavior explicit, implementation not frozen |

These unknowns do not block the requested documentation. They block only
implementation choices that depend on their answers. A later plan can keep
independent outcomes conditional rather than invent values to appear READY.

## Failure criteria and revalidation

Reject a later plan that invents provider schema, equates vectors to behavior,
bypasses scope/grants, adds specialist identities/new example integrations,
duplicates existing memory or tool authority, claims unmeasured speed, requires
Link for local Vault, cannot remove experimental components independently,
lets stale draft work execute, or rebuilds deleted knowledge. Reject a
grounding completion claim if it represents a plan/build/live benchmark as
already performed.

Reopen affected decisions when owner clarification, provider documentation,
schema/embedding identity, tool/grant changes, retention policy, actual index
version, donor evidence, or measured latency invalidates the premise. Historical
reviews do not approve changed inputs.

## Current state and next handoff

Phase 00 complete: request classified, existing chain reviewed, requirements
and seven-point traces saved, material unknowns assigned. Baseline checks and
limits are in the linked review. Internal self-review only; no owner acceptance,
frozen implementation plan, READY contract, production experiment or code change.

Next action: Phase 01 for this change only. Inspect existing responsibility
owners and targeted donors; resolve U05/U06/U07/U10 where necessary;
bound components and dependencies; define disabled/failure behavior and tests;
freeze a minimal plan without inventing the Decisions API or committing distant
DDL. The protocol requires stopping after each phase; no new permission is
needed to accept these saved review artifacts.

## 2026-10-05 owner continuation — r6

Owner authorizes Phase 01 only, using anti-drift, on its own branch before any
other work. Branch created: `feature/live-memory-decisions`; base
`ea39a6f9da89a2999c4f7e14f686428d2088f480`. Pre-existing documentation edits
were retained. No implementation, dependency install, migration or deployment.

Owner requires research before design, covering each proposed feature with
special attention to live memory/intent retrieval. Prioritize reputable primary
sources and adopted repositories; popularity is screening evidence, not proof.
Owner correction: OpenAI live transcription is selected for voice. Do not
research alternative voice frameworks as the proposed solution; find a memory
system matching live retrieval. No whole-framework migration is authorized.

Additional requirements:

- **LMD-R26:** Isolate all new behavior in separately owned components. Do not
  embed new scheduler/search/intent/learning logic in existing monolithic files.
  Existing hosts may only mount, delegate, inject dependencies and adapt current
  authorities. Exact integration edits must be reviewed in contracts. No
  duplicate canonical memory, identity, permissions or agent runtime.
- **LMD-R27:** Provide a user-facing Live Memory On/Off option. Owner confirmed
  it controls only live preparation and does not affect normal memory retrieval
  or autonomous learning. Default and persistence remain planning proposals.
- **LMD-R28:** Research and validate evolving-input memory retrieval against
  both near-perfect relevant retrieval and faster useful response. These are
  paired owner objectives, not measured outcomes or numerical SLAs. Every word
  or chunk must update validity; expensive retrieval frequency is to be tested.
- **LMD-R29:** Separate documents logically by implementation concern and keep
  research evidence distinct from normative feature plans.
- **LMD-R30:** Voice live retrieval consumes OpenAI live transcript updates;
  provider/turn adapters must correlate updates, corrections and finalization.

D12 Material Decision Gate: question is whether stricter owner modularity
changes the previous permission to extend existing responsibility owners.
Authority: latest explicit instruction, R26; existing canonical boundaries.
Alternatives: embed behavior in current hosts; duplicate the runtime; isolated
new components with narrow adapters. Selected: isolated components and narrow
adapters, preserving existing authority. Counterexample: composition or
BrowserVoiceApp gains the scheduler itself. Dependents: all feature plans and
contracts. Result CONTINUE for planning; actual paths require Phase 02 review.

D13 Material Decision Gate: question is whether OpenAI transcription needs
alternative voice-runtime selection. Authority: latest owner correction.
Alternatives: evaluate voice frameworks; use selected OpenAI live transcription
and research memory. Selected: latter. Counterexample: replacing Vault with
LiveKit/Pipecat as a prerequisite. Dependents: voice adapter and research scope.
Result CONTINUE; provider access and local runtime timing remain unverified.

r6 supersedes r5 for this change. Prior review r2 remains historical inventory;
it is not a review of this extension or a READY build contract. Material
unknowns remain conditional only for their dependent outcomes. Numeric quality,
latency/cost gates, embedding runtime and hardware must be settled using bounded
experiments before production readiness. No claim of owner acceptance.

## 2026-10-05 further owner corrections — r7

Owner confirms Live Memory switch affects ONLY live memory, not normal retrieval.
Owner requires a full written current implementation/overlap/wiring review,
preserving the existing storage and analysis system. VoiceMem store replacement
is not authorized; enhancement is conditional on demonstrated compatibility and
benefit. Owner clarifies the analysis component is the memory agent plus an
embedding model, not the separate Background Agent. Background Agent is outside
this change; physical SDK/credential naming does not change responsibility.

- **LMD-R31:** Preserve existing autonomous memory-agent review, canonical store,
  taxonomy, citations, reconciliation, scope, correction/deletion and embedding
  pipeline. Evaluate a retrieval-only VoiceMem integration; no duplicate store
  or replacement analysis system by inference.
- **LMD-R32:** Replace silent 100,000-character session-review truncation with
  complete retained-session analysis through bounded processing/consolidation.
  Preserve evidence across windows and report incomplete work honestly; no
  silently dropped tail or candidate overflow. Complete capture/retry coverage
  must be verified, not assumed from the model call.
- **LMD-R33:** Replace Python semantic-vector scanning with index-compatible
  PostgreSQL/pgvector HNSW retrieval while preserving canonical authority and
  truthful hybrid fallback. An unused index does not meet this requirement.

D14 Material Decision Gate: question is whether live switch changes normal
retrieval. Authority: explicit owner correction. Alternatives: all-memory Off;
partial-only Off. Selected: partial-only Off; normal retrieval/analysis stay.
Counterexample: turning Off disables memory_lookup or session analysis.
Dependents: settings, draft scheduler, removal tests. Result CONTINUE; initial
default and persistence still conditional.

D15 Material Decision Gate: question is whether to import VoiceMem storage and
analysis or reuse a retrieval subset. Authority: explicit preserve-store/
analysis and memory-agent clarification; current implementation review r1.
Alternatives: full replacement; retrieval subset over canonical store; defer
integration. Selected: evaluate retrieval subset, with no Background dependency.
Counterexample: VoiceMem ingest becomes another canonical writer or Qdrant
replaces PostgreSQL. Dependents: component ownership, experiment and contracts.
Result CONTINUE for research/planning, CONDITIONAL for concrete subset adoption.

D16 Material Decision Gate: question is whether identified retrieval and review
limits may remain final behavior. Authority: owner explicitly requires change;
source review proves current Python scan and character slicing. Alternatives:
retain limits; increase constants/add unused index; complete bounded analysis
and actual indexed search. Selected: latter. Counterexample: tail evidence is
lost or new index never serves runtime query. Dependents: analysis/retrieval
plans, coverage/recall/performance evidence. Result CONTINUE for requirements;
concrete build needs reviewed contracts.

Current source review:
[implementation/overlap review](../research/2026-10-05-current-memory-implementation-review.md)
`LMD-CURRENT-MEMORY-REVIEW-r1`. r7 supersedes r6; existing feature drafts must
use r7. Planning continues after owner review of the inventory. No phase
completion, implementation or owner acceptance is claimed by this checkpoint.

## r8 continuation — explicit planning and post-compaction recovery

Owner directs exhaustive Phase 01 planning now: indexed pgvector store upgrade
with tables/fields, embedding persistence/query wiring, full-context memory agent,
VoiceMem integration, OpenAI live transcription and access through existing OAuth,
all codebase integration seams. Owner reiterates MODULAR FOR NEW STUFF and requires
regrounding from disk after compaction, then continuing. This authorizes planning,
not implementation, migration, paid tests or deployment. Earlier immediate-phase
wording is historical; current deliverables are the separate Phase 01 candidate
plans and handoff. Requirements R01–R33 and resolved boundaries remain unchanged.

D17 Material Decision Gate: question: does current OAuth voice code establish
live transcription entitlement? Authority: owner asks OAuth integration; existing
voice source and fetched official OpenAI transcription/WebRTC docs. Alternatives:
assume token works; verify capability; choose API key without asking. Selected:
reuse credential resolver and condition dedicated OAuth transcription on verified
model/session entitlement. Function: preserve user's desired access without
inventing provider support. Counterexample: OAuth voice succeeds but dedicated
transcription returns403. Dependents: transcription-only OAuth outcome, not memory/
chat/indexed search. Result CONDITIONAL; no paid compatibility test performed.

D18 Material Decision Gate: question: what does migration to pgvector mean here?
Authority: owner HNSW request and source schema showing real vector column already
present. Alternatives: replace canonical store; upgrade SQL/index path; add unused
index. Selected: additive indexed-query migration retaining canonical authority.
Counterexample: Python still scores vectors or donor store becomes canonical.
Dependents: storage/search, embeddings, live adapter. Result CONTINUE for planning;
installed version/schema/resource capacity and actual plans remain unverified.

D19 Material Decision Gate: question: where does new implementation live?
Authority: repeated explicit owner modularity requirement; current host/conventions.
Alternatives: inline monolith changes; separate owned modules with narrow ports;
parallel replacement runtime. Selected: separately removable modules composed into
current authority through narrow adapters, as defined in modular integration plan.
Counterexample: removing live retrieval disables autonomous learning, or host owns
new scheduler. Dependents: all feature/build contracts. Result CONTINUE for planning.

r8 supersedes r7 for current planning; past source facts/role correction remain
valid. No owner acceptance or completed Phase 02 review is asserted.

## r9 — separate Chat, prior sessions, attachments and full tool functionality

Owner's latest correction supersedes the earlier Home/chat replacement: keep the
Voice page and current functionality unchanged; live-memory/transcription additions
remain planned, not permission to redesign the page or break persistent voice mode.
Create a separate Chat page integrated with existing navigation and the same live
memory pipeline. Merge pages only if separately requested later. If Chat offers
voice access, its control is a compact icon on the right of the composer; it uses
the existing persistent mode authority, not another navigation-owned microphone.

Owner authorizes prior-session list and continuation, image capture/import and
document import, normal/write tools and capability parity through existing tool
authority. Future filesystem donor replacement is deferred; current filesystem
adapters must be replaceable. Screenshot supplied2026-10-05 provides dark navy
left navigation/cyan accents/Voice hero baseline; exact Chat placement is provisional.
Explicit basics include correct scrolling/alignment, compact composer and visible
waiting state; visual polish must be verified in browser, not presumed from jsdom.

| ID | Requirement | Authority | Positive | Negative |
|---|---|---|---|---|
| LMD-R34 | Chat uses shared live/final memory ports and has working scroll, compact composer, aligned content, pending/stream/error/stop states, keyboard/mobile/accessibility behavior | Latest owner request | Reading history doesn't jump during stream; pending reply visibly acknowledged | Rushed textarea, clipped content, oversized input, hidden waiting/error |
| LMD-R35 | Scoped prior-session list and continuation load existing evidence/context without copying or re-ingesting it; new evidence ingested idempotently | Latest owner request | Resume already-reviewed session, append new turn, publish only new contributions | Boolean ingested blocks future learning or reopen replays tools/duplicates memory |
| LMD-R36 | Image capture/import and document import reach supported model input with preview/status, citations and explicit unavailable/extraction failure | Latest owner request | Submitted attachment visible to model and retained by reference | Displaying thumbnail counted as model analysis; unsupported input silently ignored |
| LMD-R37 | Chat exposes existing authorized general/read/write/delete tools, imported capabilities and confirmations with replaceable filesystem adapter | Latest owner request + existing grants | Authorized file write works from submitted Chat turn | Read-only fake chat, permission union/bypass or a new system agent |

D20 gate: question separate page or replace Voice? Authority exact latest owner
correction and screenshot; alternatives replace/merge now, separate now, defer.
Selected separate Chat; function add usable conversation without changing Voice.
Counterexample navigation stops active Voice or new UI replaces hero. Dependents
R19/O4/UI seams. CONTINUE; earlier conflicting plans/review identity STALE.

D21 gate: question how mark history ingested? Authority R35 + current per-snapshot
fingerprint/ingestion tables; alternatives boolean, whole-history re-review on each
resume, entry/contribution coverage plus snapshot jobs. Selected explicit coverage
ledger + immutable snapshots, full context read separately from new publications.
Counterexample older ingested correction prevents later update or full snapshot
publishes old candidates twice. Dependents history/O0/O6. CONDITIONAL pending
idempotency/late-correction proof; no ingestion migration assumed.

D22 gate: question does tool parity create third identity or union grants?
Authority R37 and fixed two identities; alternatives thirdChat agent, unionVoice/
Background access, existing interactive Voice identity/channel adapter. Proposed
last, function parity through current catalog/authorization without authority
expansion. Counterexample Background-only grant becomes usable from Chat or
Voice-mode control fires from typed chat. Dependents tool adapter. CONDITIONAL:
only differing explicitly enabled capability is withheld until correct authority
mapping; inventory proof and owner decision resolve genuine grant differences.

## r10 — assistant-ui owner selection

Owner: “if its open source, i approve.” This refers to the recommended assistant-ui
UI primitives. Verified2026-10-05 repository
[MIT license](https://github.com/assistant-ui/assistant-ui/blob/main/LICENSE).
Condition satisfied: open-source assistant-ui components approved for Chat.
Preserve required copyright/license notice. No assistant-cloud/backend/store
replacement approved; exact dependency version/React compatibility and adapter
verification remain implementation prerequisites, not another owner selection
request. This is component selection, not acceptance of whole plan or permission
to skip anti-drift review/build contracts.

D23 gate: question whether assistant-ui selection is authorized; governing
authority is explicit conditional owner approval + inspected MIT license;
alternatives select open-source primitives, custom mechanics, hosted replacement.
Selected open-source primitives over Vault-owned backend; function reliable Chat
mechanics. Counterexample selected package requires cloud authority or incompatible
React runtime. Dependents O4 adapter/dependency contract. CONTINUE for selection;
CONDITIONAL technical integration until pinned compatibility proof.

## r11 — Phase02 corrections, source compatibility and first build boundary

Phase02 same-context internal self-review, not independent assurance/owner acceptance.
Original request and r10 candidate hashes recovered before plan justification.
Review corrects implementation mismatch rather than expanding feature scope:
local HTTP server lacks PATCH and buffered responses can't stream; static frontend
Permissions-Policy blocks camera; immutable review/source attachment identities need
explicit type adapters; canonical citation/authority and erasure must include every
new durable owner. These are scoped necessities under R01/R19/R22/R24/R31–37.

D24 gate: question how expose replaceable retrieval without adding live/donor logic
to current MemoryService? Authority R01/R06/R07/R31/R33 plus inspected search callers.
Alternatives direct rewrite of existing MemoryRetriever, port plus default legacy
adapter, replacement whole runtime. Selected small read-only search port and default
legacy adapter foundation. Function same caller contract with independently replaceable
query engine; indexed backend is later contract. Counterexample new optional backend
silently changes default search, bypasses scope, or live Off disables lookup.
Dependents next LMD-C01 foundation and O2. CONTINUE for this bounded foundation;
no HNSW/indexed-search success claimed by it. Production query/index/cutover needs
isolated DB evidence in later contract, not approval invented from port tests.

D25 gate: question does “don't touch Voice functionality” prevent additive live
voice work? Authority latest owner explicitly retains both original Voice and
previous live enhancements. Alternatives cancel all voice enhancement, redesign
Voice/UI, additive opt-in controller adapter. Selected additive adapter preserving
existing default mode/page/transport until verified feature path; function live
retrieval without navigation regression. Counterexample Chat mount closes active
Voice or new partial transcript replaces canonical final unexpectedly. Dependents
O5/O4 integration. CONTINUE for boundary; O5 transport/access still CONDITIONAL.
