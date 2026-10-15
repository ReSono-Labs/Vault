# Decisions/evidence Phase02 review and contract gate

Review LMD-DA-PR02-r1. Type: same-model/context INTERNAL SELF-REVIEW, not independent
or external review, not owner acceptance. Owner request: finish tight code-grounded
planning and review BEFORE implementation. GPT-Live excluded. Existing separate Chat,
current Voice, canonical memory and grants preserved; no new agent identity.

## Exact scope and reconstructed requirements

Input authored candidate: 2026-10-07-decisions-plan-candidate.sha256 verified all15
entries before correction. Original r11 plus amendment r1. Required behavior:
dynamic finite choices, revision-sensitive parallel memory, no pre-final tools,
source-attributed learning with hindsight/throwaway distinction, scoped real HNSW
and authoritative tables, history audit, removable modules and truthful fallback.
Code baseline ea39a6f9da89a2999c4f7e14f686428d2088f480 unchanged.
Correction cycle1: source amendment r2 -> selector r2/learning r4/module r4/master r7,
analysis evidence-storage refinement and new draft contracts. Corrected immutable
input set: docs/planning/2026-10-07-decisions-reviewed-plan.sha256;
actual code identities: docs/planning/2026-10-07-decisions-review-source.sha256.
These bind saved files, not production behavior. Old manifests remain historical.

| ID | Severity / exact independent evidence | Violated authority / dependents | Class | Resolution/re-review |
|---|---|---|---|---|
| F01 | Major: selector r1 says existing port; no decision_routing runtime module exists | No invented code, DA-R11/C17 | Correction | Proposed port terminology; typed adapter mapping now explicit |
| F02 | Major: uv.lock OpenAI2.54.0 vs fetched official guide Python3.26.0 minimum | DA-R01/provider compatibility/C17 | Verification/correction | Grounding P12; adapter unready until pinned SDK+Agents compatibility/account proof; no forced install |
| F03 | Major: ToolCatalog.invoke returns before observer for denials/schema rejection, raises on handler exception, swallows observer failure; production has no set_invocation_observer call | DA-R05/07/08; C03/history | Correction | Grounding P11/P06 corrected; runtime-around-invocation capture plus gap/recovery requirements; history availability unknown |
| F04 | Major: voice/events.py records provider event then separate transcript transaction; duplicate accepted=False bypasses repair | DA-R07/R32/C03 | Correction | Analysis plan atomic append/shared connection or reviewed outbox; explicit crash+duplicate-repair tests; C03 blocked prerequisites |
| F05 | Major: learning proposed execution_evidence duplicates canonical event responsibility and could couple source to derived generations | DA-R11/R16; C03/C14 | Correction | Read-only projection; canonical selection table owned by evidence, generation identity snapshot without destructive cascade |
| F06 | Major: ToolDefinition lacks semantic capability aliases/schema epoch contract | DA-R03; C15 | Correction | Explicit proposed CapabilityResolver and mappings; no model-invented equivalence/provider interchangeability |
| F07 | Major: broad table/JSON names don't enforce same-scope relationships or immutable versions | DA-R03/07/11; C03/C14 | Correction | Exact field types/keys/composite scoped FKs, immutable versions, pointer CAS, source erasure and index predicates documented |
| F08 | Major: complete() succeeded can carry result.is_error; bounded payload[:16384] can truncate JSON; observer does not prove useful resolution | DA-R05/09/12; reviewer/audit | Correction | Independent state/tool-report/usefulness axes; legacy projection; unknown/truncated source; no count by succeeded alone |
| F09 | Major: early selection can depend on memory that arrives later; final text equality alone insufficient | DA-R04/06/10; C06/C17 | Verification/correction | Context-gated selection, fingerprints/reconsideration, final grants/capability/generation validation; fake and real race proof required |
| F10 | Blocker-dependent: no authorized historical data inspected, no retention/forget replay or activation policy, no numerical budget/threshold commitments | DA-R08/09/12; historical rebuild/active routing/release | Verification | Explicitly conditional; no historical learner run, no automatic activation/release READY; does not block unchanged search foundation |
| F11 | Major readiness: candidate signatures/tables could be taken as full system READY | Protocol/user exact-plan concern/all | Correction | C03/C17 contracts detailed but dependency-blocked; sole next READY bounded C01; exact rest-of-system prerequisites registered |

Re-review affected source premises against actual files and fetched API reference:
wire choices.value string/bool, response choice/confidence/probabilities, refusals,
unsupported audio/tool roles and absent summary all respected. We use string IDs
only with reserved fallback. No implied generated tool args or magic confidence.
Missing mapping/SDK/identity is a blocker, not hypothetical capability proof.
No second correction cycle on same issue or unapproved redesign used.

## Requirement trace for new scope

| Requirement | Decision/owned deliverable | Positive / invalidating evidence | Exit/rollback/acceptance |
|---|---|---|---|
| DA-R01 | Grounding no-Live gate; selector r2/C17 | Documented request projection; reject Live events/unsupported SDK | Optional fallback; owner acceptance after endpoint proof |
| DA-R02 | Dynamic mapping gate; selector r2/O-DA-C | Known supplied ID; absent correct candidate falls back | No all-catalog prompt; measured recall; disable selector |
| DA-R03 | Learning immutable definitions; resolver/C15 | Current capability resolves; grant/schema change blocks | Current ToolCatalog authority, no activation until policy |
| DA-R04 | Learning phase/disposition; runtime/C06 | Superseded prediction excluded; final reuse attributed | Transient speculation, no unsent examples |
| DA-R05 | Evidence/runtime capture/C03 | Denied/unneeded/error/unknown/replay distinct | Durable real effect preserved; no rerun |
| DA-R06 | Causal parent + available-source refs | Later result not available at earlier choice | Reviewer inference separated; unknown linkage truthful |
| DA-R07 | Summary/capture/review windows | Genuine call summary; failed/truncated evidence can't claim success | Independent consumers; source preserved |
| DA-R08 | Audit O-DA-A/history/learning | Scoped coverage report; unwired observer/old incomplete sources remain unknown | Read-only first; no tool replay/publication |
| DA-R09 | Reviewer create/add/revise/no-change/insufficient | Citation/dedup/correction; synthetic/retry not observed success | Inactive proposals; prior generation retained |
| DA-R10 | Runtime parallel context/final validation | Edit/delete/IME/attachments/context/generation races | No pre-final tools; normal final fallback |
| DA-R11 | Module dependency+storage cleanup | Remove selector/learner/generation preserves memory/history/grants | Ports/no-op; only scoped derived deletion |
| DA-R12 | Evaluation O-DA-D | Held-out selection/recall/usefulness and paired latency/cost | No provider claim as app proof; owner numeric release acceptance |

Original R01–37 trace remains October5 review plus corrected owned plans; this
review does not certify all historical UI/audio/storage claims. New changes affect
R01–05/07–18/21–25/31–37; applicable tests are named in owned plans/contracts.
Source-grounded call graph now names hosts, ports, transaction owners, payload
origins and refusal/fallback. Per-contract file allowlist prevents host mixing.

## Contract review

C01/r2 is unchanged semantic scope from r1: MemoryService injection + existing
legacy retriever; no schema/provider/Voice/Chat execution. Compare actual constructor,
search factory/repair branches and retrieval result/callers: protocol remains
compatible. All original source manifest entries verified unchanged.20 existing
focused tests pass in0.21s; new boundary tests remain Phase03 obligation. Module
imports memory.retrieval/repository but never MemoryService, preventing new cycle.
No DB/account/retention/activation prereq for this slice. Allowed files contain
no SQL/scheduler/model calls. Failure propagation/default parity explicitly tested.
Decision PASS for exact C01/r2 after corrected identity freeze; lifecycle READY.
Does NOT demonstrate HNSW, live speed, session review, API or completed feature.

C03/r1 reviewed against evidence source: planned typed event identity/append scope,
atomic recovery, negative tests and edit ownership present; parent conversation/
Voice-source identity, transactional repository seam, migration/isolated DB and
erasure prerequisites absent. Decision BLOCKED, no scaffold permitted. Refine into
reviewable identity/capture slices before readiness; do not implement circular C03/C08
dependencies together without reviewed parent-identity foundation contract.

C17/r1 reviewed against official types and current SDK: mapping/fallback lifecycle
explicit; SDK compatibility/access/budget, controller and activation absent.
Decision BLOCKED for active adapter integration. Standalone diagnostic test-only
slice would need separate contract; not silently implemented under C17.

## Verdict, checks and limits

Plan decision: PASS FOR BOUNDED C01 FOUNDATION; CONDITIONAL OVERALL. No assertion
that all feature contracts are READY. Source-informed storage/typed mapping/causal
capture design reviewed; distant exact executable DDL/signatures frozen only when
parent contracts/deployed DB evidence exist, per protocol. Inventing that proof to
call all implementation ready would violate owner's no-making-things-up request.

Checks: original candidate/source hashes verified; code/UI/schema inspection,
official API fetched; baseline20 unit tests; whitespace checks; final corrected
hashes and local link checks. Not performed: live endpoint/account/SDK upgrade,
Postgres migration/EXPLAIN/restore, actual historical sessions, new implementation
tests, browser/audio, external/independent review. No code/DB/provider changes.

Permitted next action if owner authorizes implementation: Phase03 C01/r2 only.
Owner asked review before implementation, not implementation now: stop here.
Other contracts remain in Phase02 until named prerequisites/policies are resolved.
Acceptance owner Christian; current self-review cannot create owner acceptance.
