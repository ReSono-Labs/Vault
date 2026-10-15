# Live memory, conversation and learning — Phase 01 plan

2026-10-07 revalidation notice: [Decisions/evidence grounding amendment](2026-10-07-decisions-api-evidence-grounding.md)
is controlling for the resumed API and speculative-evidence scope. This plan's
affected mapping, evidence, learning, removal and provider assumptions require
Phase01 revision, then Phase02 review. Earlier API-unavailable/deferred wording
is historical and does not override the amendment. No build readiness added.

Revision: LMD-PLANNING-INDEX-r11. Design/outcome authority only; the linked
build-contract register owns current readiness and implementation status.
Current document set: [authority map](2026-10-07-live-memory-document-authority.md).

Current sequence: preserve built C01/C03A/C17A; C03B READY is withdrawn pending
necessity proof, not the next build. [Feature audit](../reviews/2026-10-07-feature-validation-index.md)
and [reconciled missing deltas](2026-10-07-live-memory-reconciled-build-scope.md)
identify current missing work; explicitly historical sections below are not build
instructions. Product requirements are not superseded by implementation inventory.
Next is bounded existing-source crash-consistency contract review; C02 indexed
SQL migration and C08 text-tool-context prerequisites remain explicit. No owner
branch lookup is a prerequisite. Contracts must reuse actual existing code.
Not owner-accepted or whole-feature build-ready. Grounding r11 plus DA amendment r2. Source baseline:
`ea39a6f9da89a2999c4f7e14f686428d2088f480`. Branch: `feature/live-memory-decisions`.
Earlier `decisions-reviewed-plan.sha256` identifies a historical candidate only.
Old reviews do not approve these corrected documents.
Method: [anti-drift protocol](/home/christian/Documents/Projects/drift-protection/AI-PLANNING-PROTOCOL.md),
Phase 01 / Stages2–4. Plan authored in same context; no Phase02 semantic review.

## Architecture and separate authoritative artifacts

- [Decisions/evidence amendment](2026-10-07-decisions-api-evidence-grounding.md):
  sole new requirements DA-R01–12, supplements original r11.
- [Selector plan](2026-10-07-decisions-selector-plan.md): finite dynamic mapping,
  adapter boundary and O-DA-A–D delivery/requirement traces.
- October7 sections in owned plans supersede conflicting older assumptions only;
  candidates await Phase02. Revalidation notices refer to revision work now drafted,
  not reviewed. Older frozen manifests remain historical.

- [Grounding](2026-10-04-live-memory-decisions-grounding.md): sole requirements,
  owner authority, controlled terms and material governing decisions.
- [Current implementation and overlap](../research/2026-10-05-current-memory-implementation-review.md): existing store, memory agent, embedding, capture and all integration findings.
- [Research](../research/2026-10-05-live-memory-retrieval-research.md): donor/source evidence and benchmark limits.
- [Modular codebase integration](2026-10-05-modular-codebase-integration-plan.md): sole module ownership, ports, dependency direction and existing-file seams.
- [Storage and embeddings](2026-10-05-pgvector-storage-and-embedding-plan.md): actual additive migration, table/index fields, embedding persistence and query cutover.
- [Live runtime](2026-10-05-live-memory-runtime-plan.md): revision/controller/final validation, switch and retrieval-only VoiceMem adapter.
- [OpenAI transcription and OAuth](2026-10-05-openai-live-transcription-and-oauth-plan.md): dedicated provider/session/events, commit and credential capability verification.
- [Complete-session analysis](2026-10-05-complete-session-memory-analysis-plan.md): captured full history, windows/consolidation/jobs and autonomous canonical publication.
- [Conversation](2026-10-05-vault-conversation-plan.md): real text model, clean UI, final turn/tool/audio handoff and session mapping.
- [Decision learning](2026-10-05-decision-learning-plan.md): procedural definitions/examples/generations independent of canonical memory and grants.
- [Evaluation](2026-10-05-live-memory-evaluation-plan.md): authoritative measurement methodology; numeric release thresholds remain owner-reserved.

Do not copy changing definitions between these documents. Proposed schema/paths
are explicit designs for review, not evidence they exist. Later contracts freeze
actual signatures/DDL using installed provider/DB facts. No runtime scaffolding,
dependencies, migrations, provider experiment or deployment happened in Phase01.
Pre-existing owner working changes remain preserved.

## Current / deferred scope and capacity

Current planning includes all R01–R37: optional live voice/text context preparation,
actual indexed retrieval, clean conversation, full-session memory analysis,
original reasoning evidence, procedural proposals/routing/rebuild and removal.
Decisions API wire integration is now planned as optional C17 after SDK/account
verification and contract review; no GPT-Live. New amendment supplements r11.
VoiceMem full store/ingestion/ASR/persona, unrelated UI, new agent identities,
separate Background goals and Link changes are excluded. Existing canonical
store/reconciliation/taxonomy/evidence/credentials/tool grants remain authoritative.

Christian is acceptance/policy owner. Future maintainer implements/operates
reviewed contracts; no additional staffed role or simultaneous delivery capacity
is assumed. Hardware, target corpus scale, spend, concurrency, latency/quality
thresholds and calendar estimate are unknown. Scope experiments before spending;
sequence by prerequisites instead of invented dates. Autonomously recurring memory
analysis has bounded leases/retries/resource budget; operator capacity must be
measured, not treated as an unlimited model service.

## Plan and dependency order

Outcome IDs below retain prior draft numbering but order is dependency-based.
The full-session fix is a first-class outcome O0, not postponed behind donor/UI.

| Outcome | Requirements | Deliverable | Dependencies / readiness | Evidence | Owner/capacity | Recovery |
|---|---|---|---|---|---|---|
| O0 complete captured-session analysis | R12/R13/R22/R23/R31/R32 | Shared final evidence ordering/acknowledgment, coordinator coverage/retry, independent canonical publisher | Reviewed capture/source-retention and publication contracts; current store/reviewer reused | >100k tail fact, >32 facts, cross-window correction, duplicate/crash/delete tests | Maintainer; bounded reviewer worker, Christian policy/acceptance | Pause retryable jobs, preserve final source and accepted facts; never label incomplete review complete |
| O1 comparative retrieval research experiment | R21/R27/R28/R33 | Isolated same-corpus final baseline/indexed hybrid/VoiceMem factual-subset comparison | Reviewed experiment contract, frozen donor/license/config; explicit provider/hardware budget | Held-out semantic gold plus evolving input and paired useful-response timing | Maintainer; Christian labels and numeric gate decisions | Remove experiment, reopen donor choice if no quality+speed gain |
| O2 actual indexed search | R06/R07/R18/R31/R33 | Additive HNSW/query migration and SearchPort across normal/live/external/plugin paths | Isolated DB/version/backup/capacity; reviewed storage contract; O1 needed for donor/rank choice, not basic HNSW requirement | SQL plan, exact-vs-ANN scoped recall, canonical payload/fallback, restore | Maintainer; migration/DB operator capacity measured | New/legacy search flag; preserve canonical tables/vectors |
| O3 revision preparation and live setting | R01–R05/R18/R25/R28/R30 | Bounded revision scheduler, transient context, no-op port, persisted setting and epochs | Search interface O2; O1 metrics for tuning; owner setting scope/default before release | Delete/ABA/late jobs/Off/revocation; exact-final validation | Maintainer; bounded user/global workers | Disable live preparation; normal final search/learning stay |
| O4 real conversation | R19/R22/R24/R25/R34/R37 | Separate Chat, complete UX basics, selected text model and general/write tools | Reviewed continuation/context contract; O2 final search; O0 evidence port; live port may be no-op | Text without microphone, tools/summary correlation, duplicate Send/disconnect/scope | Maintainer; Christian visual/policy acceptance | Unmount separate Chat; existing Voice remains |
| O5 live OpenAI voice | R02/R05/R22/R29/R30 | Dedicated transcription, application commit, final validation before response, scoped credentials | O2/O3/O4; documented provider session access; OAuth capability independently verified | Actual deltas before commit, unordered finals, OAuth failure, barge-in; useful played audio | Maintainer; authorized audio/model experiment budget | Disable new adapter; retain existing voice/credentials |
| O6 durable procedural review | R12/R13/R22/R23 | Independent evidence consumer/proposals with retry/idempotency | O0/O4 evidence; O5 voice adds channel; retention rules | Procedure failure leaves accepted memory; truthful absent summaries | Maintainer; separately bounded worker | Disable procedural consumer, preserve memory workflow |
| O7 rebuildable definitions/examples | R08/R14–R18 | Inactive proposals, vectorized examples, validated generation rebuild | O2/O6; retention/deletion/dedup contracts and scale | Related-but-distinct actions, forgotten source, interrupted build/rollback | Maintainer; Christian activation policy remains reserved | Keep previous generation/inactive state; no action replay |
| O8 eligible routing | R09–R11/R15/R17/R18/R20 | Known rule + replaceable finite selector + reasoning fallback | O7 plus explicit activation/effects/capability policy; Decisions API not required | Ambiguous slot/current grants/tool removal; unavailable selector fallback | Maintainer; Christian policy acceptance | Deactivate routing/generation; ordinary model/tools remain |
| O9 integrated acceptance | R01/R21/R26–R33 and all earlier applicable rows | Quality/speed/cost, modular removal and operator acceptance evidence | Required policy/access/capacity established; implementation outcomes pass | Representative paired DB/provider/audio and regression evidence | Christian acceptance; maintainer real measurements | Live Off or rollback component without losing canonical learning |

Sequence: first capture/complete-analysis and database prerequisites; isolated
experiment in parallel only if independent resources exist; indexed retrieval;
revision controller; real text conversation; dedicated voice; independent procedural
learning/generation/routing; integrated release. A blocker affects dependents only.
Text conversation and indexed/full-session work do not wait for Decisions API or
OAuth-only transcription entitlement. No forced wait for donor experimentation
before preparing the required canonical migration contract.

## Stage 3 necessity / alternatives register

Each row answers the eight required questions: scenario, authority, current need,
prerequisites, builder/operator capacity, smaller design, tests/reversal, and
invalidating counterexample/independent resolution. Refer to outcome table for
exact test/evidence and capacity; this register does not invent readiness.

| Item | Scenario / authority / now | Prerequisite / capacity | Smaller alternative | Test/reverse / falsifier and resolution |
|---|---|---|---|---|
| O0 | Owner wants whole history, R32; yes | Capture/reviewer contracts, bounded maintainer worker | Increase limit rejected: finite context still truncates | O0 tests; source retained on failure. Full coverage counters but missed correction falsifies; semantic late-fact labels resolve |
| O1 | Proven retrieval + speed, R28; yes | Isolated assets/access/budget, maintainer + owner labels | Indexed baseline alone may win | O1 teardown; donor aggregate score may not transfer. Paired held-out evidence resolves |
| O2 | Real HNSW, R07/R33; yes | Existing pgvector/version/backup, maintainer operator | Preserve vector/table, add query/index rather than replace store | O2 rollback; index exists but unused falsifies. SQL plans and scoped recall resolve |
| O3 | Context ready while input evolves, R02–05/R25/R30; yes | Search port/work bounds, maintainer | One running/one pending revision and no-op adapter | O3 disable; late reversal uses old memory falsifies. Final-input tests resolve |
| O4 | Real text chat without microphone, R19/R24; yes | Lifecycle/provider/tool/evidence, maintainer + owner review | Existing tokens/components; no Help backend reuse | O4 restore; textarea without model or mixed host state falsifies. Actual turn/UI evidence resolves |
| O5 | Speech-time preparation/OpenAI, R29; yes conditional | Account/model access/VAD/final response port, paid capacity unknown | Dedicated OpenAI transcription, existing response authority | O5 fallback; OAuth voice succeeds but transcribe403 falsifies. Exact provider capability proof resolves |
| O6 | Independent learned procedure review, R13/R23; yes conditional | Durable final evidence/retention, bounded maintainer worker | Inactive proposals first | O6 disable; memory fails with procedural reviewer falsifies. Independent failure tests resolve |
| O7 | Rebuildable procedure definitions/examples, R08/R16; later interface now | O6/deletion policy, maintainer capacity unmeasured | One inactive generation until acceptance | O7 pointer rollback; forgotten facts rebuilt falsifies. Deletion/replay tests and owner policy resolve |
| O8 | Repeat routing without losing authority, R10/R11; later conditional | Activation/grants/capability policy, maintainer | Ordinary reasoning fallback; selector optional | O8 deactivate; similar example grants a tool falsifies. Negative eligibility tests and existing authority resolve |
| O9 | Near-perfect retrieval plus fast useful response, R21/R28; necessary gate | Actual operating evidence + owner thresholds | Release live Off while evaluating rather than false claim | O9 disable; search134ms but same response pause falsifies. Played-audio paired evidence resolves |

## Material decision results and unknowns

Governing gates D14–D19 are in grounding; do not duplicate their authority here.
Additional candidate implementation choices have the following seven fields:

| Question | Authority/evidence and limit | Alternatives | Selected/function | Counterexample | Dependents | Result |
|---|---|---|---|---|---|---|
| Adopt VoiceMem how? | R28/R31, pinned inspected donor; published complete-question harness doesn't prove live/factual subset gains | Full import; licensed factual subset; baseline only; defer | Evaluate retrieval-only subset over canonical port | No benefit without donor ingestion or unsafe final reuse | O1/O3/O5 | CONDITIONAL |
| Which embedding identity? | Existing1536 OpenAI vectors; no local latency proof | Retain; local E5/reindex; dual model | Retain current identity for additive migration, separately measure alternatives | Provider query embedding dominates final latency | O1/O2/O3 | CONTINUE for migration design; speed hypothesis conditional |
| How complete analysis? | R32 + actual100k/32 slicing; no infinite context | Bigger constant; chunk only; bounded hierarchical coverage/consolidation | Full captured evidence with retryable nodes and independent publication | Late cross-window correction lost despite coverage | O0/O6 | CONDITIONAL on capture/publication/semantic tests |
| Live default/scope? | BP-R01 owner reply | Per user/workspace, initially On | Persist scoped setting; Off disables preparation only | Shared machine scope unexpectedly changes another user | O3/O9 | RESOLVED policy; implementation/evidence pending |
| Conversation boundaries? | Owner explicitly requests stored-session continuation, r9 | New-only; resumable same ID; copied new session | Same history reference with new activity segments; no tool/history replay | Resume duplicates old ingestion | O4-H/O0 | CONTINUE for requirement, CONDITIONAL for coverage contract |
| Activate rules? | R11/R15/R16; BP-R02 owner reply | Automatic validated read-only activation | Writes/unknown effects inactive; current grants and final-input validation mandatory; no numeric threshold invented | Semantic match bypasses grant or pre-final boundary | O7/O8 | RESOLVED direction; validation/quality implementation pending |
| Retain/replay forgotten evidence? | BP-R03 owner reply | Retain history; suppress relearning | Scoped durable suppression across reviews/rebuilds; retained sources cannot resurrect forgotten facts | Rebuild resurrects deleted memory | O0/O7 | RESOLVED policy; suppression implementation pending |
| Numeric performance gates? | Owner near-perfect+speed; no thresholds/hardware/spend | Invent defaults; measure then accept; defer release | Paired measurements then Christian acceptance | Fast retrieval worsens answer/useful audio | O1/O9 | CONDITIONAL |

These unknowns do not authorize invented defaults or false completion. Provider
OAuth/model access is unknown, not a user permission question for current read-only
planning. No paid tests are needed to finish this conditional candidate.

## Delivery blocks and near-term contracts

Each outcome table row supplies scenario/owner, dependencies, deliverables,
positive/negative evidence, recovery and exit obligation; detailed feature plans
provide explicit stop conditions. Common scope: owned module only plus named narrow
adapters. Common exclusion: unrelated hosts/Background/new identities. Stop on
scope leak, lost evidence, early tool effect, unbounded work or mixed responsibility.
Exit requires real outcome evidence and acceptance, not files/tables produced.

First contracts to allocate after Phase02 review: (1) isolated capture+analysis
coverage/recovery, (2) existing-store indexed migration/query/embedding maintenance,
(3) bounded VoiceMem comparison experiment. Each names exact path allowlist, schema
identity, resource/test scope and rollback. Then revision/preference, conversation,
transcription/auth and procedural outcomes. Distant procedural SQL and activation
remain interface/schema proposals until their prerequisites are settled.

## Historical candidate validation/handoff — not current status

Baseline source tests from inventory:25 backend and11 frontend passed. Isolated
PostgreSQL/provider/audio validation not performed. Documentation checks: candidate
relative links, requirement references, branch identity and diff whitespace; exact
hash manifest captures saved content. These checks do not prove semantic feasibility
or installed entitlement. No plan-quality PASS or execution READY is claimed.

Next action: Phase02 review this exact candidate against original owner request,
grounding and source evidence first, especially modular seams, full-context semantic
coverage, scoped ANN underfill, OAuth entitlement and controlled response audio.
Stop at Phase01 now; do not implement based on this candidate. Later review changes
must update controlling artifacts and create new hashes; an old review becomes stale.

## Grounded Chat/history/attachments/tool expansion — requirements retained

Owner correction reopens Phase01 candidate; prior r2 hashes/reviews are stale.
[Chat research and overlap](../research/2026-10-05-chat-history-attachments-and-tools-research.md)
precedes [history plan](2026-10-05-chat-session-history-plan.md) and
[attachment/tool plan](2026-10-05-chat-attachments-and-tool-parity-plan.md).
D20–22 in grounding govern separate-page authority, ingestion coverage and tool
identity. R19 no longer means Home replacement. Active Voice mode/navigation
semantics are baseline regressions to preserve. Screenshot placement remains
provisional; functional requirements are binding.

| Outcome | Requirements/scenario | Dependencies/deliverables | Evidence/owner/capacity | Stop/recovery/exit |
|---|---|---|---|---|
| O4-H history continuation | R35; return to prior conversation and learn new turns once | O0 coverage/publication, O4 server history ports; scoped cursor list/read/context links/segments, no history copy | Resume/read repeated with zero ingestion; new fact/correction once; long legacy coverage unknown; concurrent/relogin/scope tests; maintainer with Christian retention acceptance | Stop on duplicated effects/learning or false full coverage; disable history adapter, preserve source/coverage; exit safe new-turn continuation |
| O4-A capture/import | R36; submitted image/document usable by model | O4 provider capability + private storage/input adapters; preview/tray/capture/import/extraction references | Actual image/file model trace, unsupported/partial truthfulness, scoped preview, remove/expired/error; maintainer scoped provider experiment and Christian format/retention choice | Stop on ignored file/scope leak; remove capture/input route, retain submitted references; exit real supported multimodal use |

Stage3 eight questions for added items: O4-H scenario/authority is owner's prior
session request; needed now in Chat scope; O0/O4 + evidence identity prerequisite;
maintainer operates cursor/history/coverage within measured DB capacity; smaller
same-ID/reference design instead of history copies/new store; test/reverse as row;
counterexample repeated reopen causes model/write calls, resolved by independent
call/publication counts. O4-A scenario/authority is owner capture/import request;
needed now; supported model/storage/limits prerequisite; maintainer scoped budget;
smaller typed attachment adapter/current storage instead of full document platform;
test/reverse as row; counterexample preview works but model never gets bytes,
resolved by actual model-input trace. Tool parity is O4 prerequisite rather than
future filesystem donor; follow existing grants, not their union.

Material gate additional decision: which UI mechanics? Authority R34 + inspected
React18 and assistant-ui docs; alternatives existing React/manual basics, compatible
headless primitives, hosted chat replacement. Candidate compatible headless primitives
behind Vault adapter for quality/speed of implementation; intended function reliable
scroll/composer/states. Counterexample incompatible runtime forces Node/cloud or
scroll jumps despite defaults. Dependents O4/UI tests. CONDITIONAL until pinned peer/
license/runtime experiment; hosted replacement excluded. No library installed.

Near-term Chat contract must cover every UX row, browser geometry and preserved
Voice navigation, durable tools/confirmation/evidence; history follows shared
coverage and attachment input follows supported model transport. These are added
planning scope, not permission to implement. Updated frozen candidate is r3/r9;
Phase02 review must use latest request/image and original constraints.

## Grounded assistant-ui selection — owner decision retained

Grounding r10 D23 records owner approval of open-source assistant-ui components;
MIT license verified. Library selection resolved, React18/version/adapter compatibility
remains technical prerequisite. No hosted assistant-cloud dependency or new backend.
Earlier r3 evaluation/selection uncertainty is superseded to this extent. Plan
remains conditional/unreviewed; no package installation or implementation.

## Historical Phase02 candidate r5 readiness partition — not current status

Plan review is conditional overall, with passing dependency-ready search foundation
only. LMD-C01 supplies SearchBackend/legacy adapter seam as first O2 foundation;
no live policy, provider/DB/retention decision required for its unchanged behavior.
Remaining O0/O2 migration/O3–O9 contracts stay DRAFT/conditional until each required
policy/capability/evidence exists. Dependencies are not waived by this scoped pass.
[Phase02 review](../reviews/2026-10-05-live-memory-phase02-review.md) owns findings,
traceability and assurance; contract review owns exact C01 readiness. Current source
and candidate identity manifests are separate from documents they fingerprint.

Preference API corrected to GET/POST, streaming requires explicit HTTP host adapter,
camera policy blocks camera until reviewed opt-in capability, typed metadata/epoch
adapters and deletion/worker cleanup are required dependencies. Assistant-ui npm
metadata checked2026-10-05: react0.15.23 peers React18 or19, markdown0.14.18 peers
react18 or19 + assistant-ui/react^0.15.0; declarations establish candidate compatibility,
not actual bundled integration. No dependency installed. Pin version/integrity in
later Chat contract; license notice retained. Candidate versions are measured source
facts rather than requirement to always install latest.
## Historical pre-build foundation review — superseded, not a work order

Owner continuation: continue getting ready to build, no implementation now. Exact
near-term contracts C01/r2, C03A/r1 and C17A/r1 are reviewed separately; current
review/manifest in PROJECT-STATE is authority for lifecycle. C03A removes C03/C08
identity cycle; C17A removes live SDK/activation requirements from pure mapping tests.
C01/C03A/C17A described here have since been built and boundedly verified.
This passage cannot authorize rebuilding them; register owns current status.

Current dependent review reuses actual outputs: C02(indexed SQL), C03 repair/C03C(capture),
C06(controller), C08(text execution), C09(UI), C14(inactive learner), C17B(live API),
C15(active policy) against implemented outputs, not imagined signatures. Existing
history, attachments, complete-memory analysis and voice outcomes retain their
contracts/acceptance. Production release defaults, paid tests, replay and automatic
activation remain later explicit gates, not build-foundation blockers.

| Material question | Authority / evidence and limits | Alternatives | Selected function | Counterexample | Dependents / result |
|---|---|---|---|---|---|
| Remove parent/capture circularity? | Owner exact wiring + actual absent identity; C03/r1 blocker | Freeze all together; Voice-only path; parent identity first | C03A private header/segment/final turn, C03B depends on verified output | Two stores created or provider session required for text | C03/C08; CONTINUE bounded contract, actual DB proof during build |
| SDK access required for parser? | Official choice schema and uv.lock mismatch, no endpoint proof | Upgrade first; pure mapping; pretend fake is real | C17A provider-neutral functional mapping; C17B separately live | Offline pass claimed as access/calibrated execution | C17; CONTINUE offline, live conditional |
| Retention/activation unresolved blocks all building? | Existing no-unsent-learning/no-grant invariants; no owner release policy | Invent policies; stop all; disable risky routes | No drafts persisted, no active rules/history replay, unmounted root slices | Build enables historical reconstruction or auto writes | C03A/C17A; CONTINUE root, release/replay conditional |

Capacity one maintainer/owner; no dates/spend commitment. Separate local tests may
start existing isolated DB only under reviewed C03A; production remains untouched.
Feature tests and teardown/rollback are contract-specific; fixtures are not endpoint
or production evidence. No contracts for distant details silently marked READY.
