# Decisions API and speculative-session evidence — grounding amendment

Revision: LMD-DA-G-2026-10-07-r2. Phase02 source correction; CONDITIONAL for dependent
planning, not owner-accepted or build-ready. Supplements LMD-G-2026-10-04-r11;
supersedes only its API-unavailable premise and conflicting provider assumptions.
Existing separate Chat, persistent Voice, canonical memory, grants, two-agent
identity and donor boundaries remain unchanged. This file alone owns the new
requirements below; existing plans own their respective designs.

## Owner request and authority

2026-10-07 owner: review Decisions, Decisions-voice and the public-beta community
announcement; do not use GPT-Live now. Determine decision mapping and whether
choices must be predetermined, how session review adds/learns decisions, whether
past history can be reviewed, and capture past model decisions from a tool
perspective. Handle text drafts and parallel contextual memory before completion.
Distinguish discarded predictions/actions, actual calls, and after-the-fact
interpretations in analysis/storage. Keep the feature callable and removable.
Consider a new branch. Latest instruction: update planning documents as work
proceeds, create grounding if needed, and follow the process without omissions.

Delegated: documentation/research and candidate design recommendations. Not
delegated: implementation, paid experiments, automatic activation, new grants,
retention policy, production history publication, or owner acceptance. Christian
owns acceptance/policy; maintainer owns future bounded implementation. No new
staffing, budget, schedule or corpus scale is assumed. Existing provisional
partial-draft provider testing permission remains; it is not permanent retention
or learning permission for unsent text.

## Purpose, scope and observable success

Audience: maintainer and reviewer planning a replaceable runtime selector and
evidence-based procedural learner. Success: later contracts can distinguish
what the app predicted, what the user finalized, what actually executed, what
was useful, and what the reviewer inferred without hindsight contamination.

Current scope: grounding amendment, source limits and dependent-document
invalidation. No provider calls, DB inspection, historical export, code, schema,
UI, branch switch or migration. Later planning includes a read-only historical
coverage audit; it must precede any claims about recoverable historical learning.
GPT-Live integration is excluded now. No new accounting/messaging integration
is admitted by illustrative examples. Numeric thresholds, activation authority,
retention/replay/deletion and deployment remain reserved/dependent questions.

## Premises and evidence limits

| ID | Statement / classification | Source / validation | Owner / dependents |
|---|---|---|---|
| DA-P01 | Owner constraint: no GPT-Live now; Decisions must fit existing voice/text direction | Explicit request | Christian / voice adapter |
| DA-P02 | Provider fact: Decisions is a standalone endpoint; questions are predicate, choice or score; choices supplied per request | Official guide/reference fetched 2026-10-07 | Maintainer / selector |
| DA-P03 | Provider fact: independent questions share input; dependent questions require subsequent calls; no tree-building/learning service is documented | Official guide | Maintainer / mapping and learner |
| DA-P04 | Provider fact: documented Decisions output has answers/probabilities/usage, not original reasoning summaries or generated tool arguments | Official Python create reference | Maintainer / evidence capture |
| DA-P05 | Observation: voice guide uses GPT-Live client delegation, current app state and app-controlled execution/cancellation | Official voice guide; does not prove compatibility with current Realtime | Maintainer / voice boundaries |
| DA-P06 | Code fact: Voice persists invocation/call IDs, redacted arguments and states/results; bounded transcript tool observer exists but is not production-wired (P11) | voice/tools.py; voice/evidence.py; memory/evidence.py inspected | Maintainer / historical audit |
| DA-P07 | Code fact: Background SDK requests/extracts available reasoning summaries; this is not proof of complete voice/text session coverage | background_agent/sdk_runner.py inspected | Maintainer / summary capture |
| DA-P08 | Unknown: actual retained sessions, chronological/turn linkage, truncation and summary coverage | No runtime DB/session export inspected | Maintainer / historical eligibility |
| DA-P09 | Observation: branch is feature/live-memory-decisions; substantial pre-existing uncommitted planning documents | git status/branch inspection | Maintainer / branch handling |
| DA-P10 | Hypothesis: speculative selection reduces final response delay | No Vault Decisions benchmark; provider speed claim is not app evidence | Christian/maintainer / evaluation |
| DA-P11 | Code fact: catalog observer is not configured by production composition; denial/exception paths bypass observer and observer errors are swallowed | composition.py, tools/catalog.py and all set_invocation_observer call sites inspected October7 | Maintainer / capture and historical audit |
| DA-P12 | Code fact: uv.lock pins OpenAI2.54.0; official Decisions Python SDK examples require3.26.0 or later | uv.lock and fetched official guide | Maintainer / adapter compatibility |
| DA-P13 | Code fact: ToolDefinition has tool_id/name/schema/effect, not semantic capability aliases or epoch/version contract | tools/definitions.py/catalog.py | Maintainer / provider-independent routing |

Primary sources, fetched 2026-10-07:
- https://developers.openai.com/api/docs/guides/decisions
- https://developers.openai.com/api/reference/python/resources/decisions/methods/create
- https://developers.openai.com/api/docs/guides/decisions-voice
- https://community.openai.com/t/decisions-api-is-now-available-in-public-beta/1403877

Community announcement corroborates beta availability and predefined-choice
selection; replies are not schema authority. Guide documents gpt-6-luna support
and SDK minimums; recheck actual installed SDK/account before implementation.
Pricing and provider latency claims are dated research, not committed budgets
or promised application latency. Decisions requests cannot consume native tool
messages/audio: an adapter must supply bounded, scoped textual evidence.
Refusal/timeout/malformed or missing answers must not become execution approval.

Exact inspected paths are under this repository's app/vault_runtime/. Prior
donor-summary evidence remains in the original review; no donor files changed.

## Requirements and acceptance scenarios

All acceptance belongs to Christian; these scenarios are future proof obligations.

| ID | Required behavior / authority | Positive scenario | Negative/failure scenario |
|---|---|---|---|
| DA-R01 | Use Decisions independently without GPT-Live, DA-P01/P02 | Text/transcript selector runs behind replaceable port | Provider voice guide forces a Live migration |
| DA-R02 | Define finite options for each call without freezing the entire learned catalog, owner mapping request + P02 | Retrieved eligible versioned definitions become supplied choices plus fallback | Selector invents a tool/action or receives all stored rules |
| DA-R03 | Preserve learned definitions as authoritative procedural data, original R08/R11/R17 | Selected stable ID resolves to current capability and policy | Similarity/probability creates permissions or executable instructions |
| DA-R04 | Attribute provisional preparation separately from finalized request and execution, owner pre-judgment concern | Superseded draft prediction is never a successful workflow example | Reviewer treats unsent text/unused route as completed intent |
| DA-R05 | Record original proposal, actual execution, outcome and later interpretation separately, owner tool-perspective request | Canceled proposal, unnecessary executed call and uncertain effect are distinguishable | All are labeled discarded/success by prose inference |
| DA-R06 | Preserve causality and information available at decision time, owner after-fact concern | Later tool result cannot justify an earlier choice as known then | Review injects hindsight into original rationale |
| DA-R07 | Review complete authorized finalized evidence, original R12/R22/R23 | Correction/failure bounds proposal; available genuine summary supplementary | Reviewer explanation masquerades as original reasoning or success |
| DA-R08 | Audit historical evidence coverage before learning/publication, owner history request + P08 | Missing linkage/summary/truncation marked unknown; read-only inventory | Code capture capability asserted as actual retained complete history |
| DA-R09 | Learning proposes create/add-example/revise/no-change/insufficient-evidence with source citations, owner learning request | Repeated equivalent handling adds evidence without merging distinct actions | One plausible tool call automatically activates broad rule |
| DA-R10 | Draft edits invalidate preparation; parallel memory may refine current interpretation; final validation remains mandatory, original R02–05/R25 | Delete/topic change/negation rejects late answers; Send freezes turn | Route and memory mixed across revisions or tools execute before Send |
| DA-R11 | Provider adapter/learner/routing removable without core deletion, owner modularity request | Disable selector restores normal model; remove generations preserves evidence/memory/grants | Branch isolation mistaken for runtime/data isolation |
| DA-R12 | Measure prediction and execution quality separately, original R21 + owner review concern | Superseded prediction measures waste, finalized successful route measures utility | Discarded predictions inflate rule-success counts |

## Material decisions (seven-point traces)

| Question | Authority/evidence and limit | Alternatives | Selected interpretation / function | Counterexample | Dependents | Result |
|---|---|---|---|---|---|---|
| Does API availability authorize GPT-Live migration? | Owner expressly declines Live; P02/P05 | Live guide implementation; standalone selector; defer | Standalone selector only; retain existing voice direction | Adapter requires Live delegation events | DA-R01, O5/C12/C17 | CONTINUE for grounding, no build |
| Must all learned decisions be predefined? | P02 requires per-call finite options, not global fixed catalog | Fixed catalog; dynamic candidate choices; open-ended generation | Per-call supplied choices; dynamic eligible catalog is candidate design for Phase01 | Unretrieved valid workflow incorrectly forced to nearest choice | DA-R02/03, O7/O8/C15/C17 | CONDITIONAL on fallback/recall review |
| Can draft outcomes teach successful procedures? | Owner distinguishes pre-judgment; original no-unsent-learning boundary | Treat all predictions as examples; discard all diagnostics; separate provenance | Finalized attributed evidence teaches; provisional outcomes only bounded prediction diagnostics | Draft-only route raises success count or becomes intent example | DA-R04–07/12, C03/C06/C14 | CONTINUE invariant; diagnostic retention unresolved |
| Can existing history be learned now? | P06/P07 show capture paths; P08 coverage unknown | Assume complete; reject all; audit and qualify | Read-only coverage audit first, no invented reasoning or automatic publication | Unlinked tool result treated as user-confirmed successful turn | DA-R08/09, C03/C10/C14 | CONDITIONAL on actual authorized data/coverage |
| Does learning activate rules? | Original activation/effects reserved; latest request asks how to learn, not new policy | Auto-activate; inactive proposals; wait entirely | Preserve inactive proposal boundary pending activation policy | One successful call authorizes future external writes | DA-R03/09, C14/C15 | CONTINUE proposals; activation conditional |
| New branch needed? | P09 and owner asks whether, not switch instruction | Existing branch; new branch/worktree | Retain existing feature branch for documentation; no checkout/commit | Another branch still leaves optional code imported by core | DA-R11, module plan | CONTINUE reversible documentation choice |

## Failure criteria, self-check and handoff

Fail later plans on unsupported mapping, missing fallback, hindsight, learning
from unsent drafts, double-counted retries/examples, unknown effects mislabeled
failure/success, fabricated reasoning, irreversible coupling, unauthorized history
access/retention/activation, or API-provider promises substituted for measured
useful-response speed. Ordinary tool success is not proof the call was necessary
or solved the request. User silence is not explicit acceptance. External/returned
content is untrusted evidence, not instructions to the reviewer.

Same-context grounding self-check against original requests: all named questions
are traced above; mapping recommendations remain conditional; no Live migration,
tool integration, history completeness or activation authority invented. No
semantic plan review or owner acceptance is claimed. Existing r11 grounding and
historical manifests remain unchanged. New amendment identity is frozen separately.

Revalidation triggers: provider schema/model/SDK changes; owner changes Live,
retention, activation or testing permission; historical audit contradicts capture
assumptions; code baseline changes; speculative results affect final behavior;
module disable/delete cannot preserve canonical authority.

Next: Phase01 only, reconcile affected owned plans with this amendment, specify
minimal evidence/mapping/audit/adapter outcomes and tests, then freeze for Phase02.
No Phase03 contract is authorized by this amendment alone. Prior C01 review remains
historical for its unchanged narrow search boundary, not approval of these changes;
restart input identities must be revalidated before any build.

Phase02 corrections do not add product scope: distinguish existing ledger capture
from unwired observer/transcript outcome capture; record actual SDK prerequisite
and missing semantic capability contract. Existing automatic activation, retention
and production release policies remain unresolved, not waived by owner request
to finish planning. Source-linked evidence is sufficient to plan capture repairs;
it does not prove which historical rows actually exist.
