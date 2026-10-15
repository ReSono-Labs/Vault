# Original grounding versus reconciled documents

Date: 2026-10-07. **Internal self-review; CONDITIONAL document alignment, not build readiness or owner acceptance.** Requested by Christian after the feature audit. No runtime implementation, external research, private-history inspection or provider call performed. The original grounding was not edited.

## Source authority and review boundary

The original change record is [October 4 grounding](../planning/2026-10-04-live-memory-decisions-grounding.md), currently r11. Its October 5 continuations add R26–37 and correct the earlier Home replacement into separate Chat while preserving Voice. This review read that entire saved record, including original request, premises, decisions and unknowns—not merely the October 7 audit. The file includes later amendments; this is not a claim to have recovered an immutable October 4-only snapshot.

Also read: product GROUNDING.md, SKILLS.MD, anti-drift protocol, borrowing matrix, feature donor map, [October 7 bounded amendment](../planning/2026-10-07-decisions-api-evidence-grounding.md), reconciled scope r2, contract register r3, feature index and all eight feature reports. Relevant residual instructions in master/module/analysis plans were checked directly. Prior source validation remains separate evidence, not proof the goal is correct.

The [reconciled scope](../planning/2026-10-07-live-memory-reconciled-build-scope.md) is reviewed as missing implementation deltas, not a replacement requirements document. Original requirements remain authoritative. The October 7 amendment admits standalone Decisions and causal/history refinements, not GPT-Live, another agent or another canonical store.

## Goal check

The original goal is still represented: while permitted voice/text input evolves, prepare relevant scoped memory and likely handling in parallel; reject superseded work; validate the actual submitted request before responding or acting; review finalized session evidence afterward to improve canonical memory and separately learned procedural handling. New behavior must be independently removable, preserve existing authorities, and prove useful-response quality/speed rather than merely fast SQL or passing isolated units.

No original core outcome is deliberately removed from reconciled scope. However, preserving a requirement in scope is NOT proof it is implemented, and superseding headers do not make conflicting instructions safe build inputs. Findings below must be resolved before affected contracts become READY.

## Original requirements — individual trace

“Retained” means the current scope/audit still requires the grounded outcome; it does not mean code is complete. C IDs identify existing allocation, not newly authorized modules or tables.

| Original ID | Grounded outcome checked | Current trace / disposition |
|---|---|---|
| R01 | Independently replaceable components/fallback | C06/C14/C15/C17B/C16; audit08; retained |
| R02 | Shared voice/text revisions with final marker | C06/C12; audits02/03; retained |
| R03 | Meaningful debounce and bounded work | C06; audit02; retained; no fixed 200–300ms SLA invented |
| R04 | Stale/delete/abandon/scope/session rejection | C06/C07; audit02; retained |
| R05 | Prepare before finalization; validate before response/action | C06/C08/C12; audits02/03/04; retained |
| R06 | Canonical hybrid memory/evidence preserved | C02/C13 plus existing memory; audit01; retained |
| R07 | Real HNSW for memory AND procedural examples | C02/C13 and C14/C15; audits01/07; retained, not Python scoring or JSON-only matching |
| R08 | Authoritative definitions and version-linked embedded examples | C14; audit07; retained; vectors do not define behavior |
| R09 | Collapse rule hits, SQL scope, current eligibility | C14/C15; audit07; retained |
| R10 | Known rules/finite selector/reasoning fallback separable | C15/C17B with C17A reuse; audit07; retained |
| R11 | Current grants/confirmation/tools at actual execution | C08/C15 and existing authority; audits05/07; retained |
| R12 | Final route/model/tools/outcomes/corrections as evidence | C03 repair/C03C/C08/C14; audits06/07; retained despite withdrawn extra user-final row |
| R13 | Independent memory and procedural review updates | C04/C14; audits06/07; retained; no third agent |
| R14 | Merge without conflating distinct actions | C14; audit07; retained |
| R15 | Qualified observed outcomes/confidence; uncertain fallback | C14/C15; audit07; retained; activation policy not invented |
| R16 | Rebuild derived generations without destroying core/source | C14/C15/C16; audits07/08; retained; forgetting/replay policy still conditional |
| R17 | Stable capability references/current providers/unavailable rules | C14/C15; audit07; retained, but exact allocation needs clarity (F03) |
| R18 | Scoped version-valid caches; DB authoritative | C06/C13/C15; audits01/02/07; retained |
| R19 | Separate Chat; persistent unchanged Voice; right-side small voice control | C08/C09; audit04; retained; follows October5 correction, not initial Home replacement |
| R20 | Link connectivity separate from local intelligence | Reconciled boundary exclusions/C14/C15; audit07; retained; no required hosted Link authority |
| R21 | Truthful speed/cost/degradation evidence | C05/C16; audit08; retained; useful response, not first token |
| R22 | Genuine available per-call summaries with missing/truncated status | C03C/C08/C12; audit06; retained; existing helper is not complete capture |
| R23 | Review summaries together with actual final evidence/outcomes | C03C/C14; audits06/07; retained; no invented retrospective reasoning |
| R24 | Real scoped text model/tools independent of microphone | C08/C09; audit04; retained; Help is not substitute |
| R25 | Dynamic draft interpretation plus parallel context, revised as either changes | C06/C08/C15; audit02; retained; not route-only preparation |
| R26 | Modular NEW behavior; narrow hosts; no duplicated authority | Reconciled no-duplication gate and module r7; audit08; retained; residual designs need cleanup (F01/F05) |
| R27 | Live Memory setting controls preparation ONLY | C07; audit02; retained; normal retrieval/learning continue Off |
| R28 | Relevant retrieval AND faster useful response, evolving-input tests | C05/C16; audits02/08; retained; no numeric gate or speed guarantee invented |
| R29 | Concern-separated plans/research/evidence | Owned plans versus reports/register; retained; overlapping stale instructions remain F01/F02 |
| R30 | OpenAI transcript updates correlated through corrections/finalization | C12/C06; audit03; retained; conditional access is not cancellation of voice outcome |
| R31 | Preserve existing memory/embedding/reconciliation; evaluate retrieval-only VoiceMem | Existing owners plus C05/C06; audits01/02/06; retained; no donor store/ASR/persona adoption by inference |
| R32 | Complete retained-session review without dropped tail/candidate overflow | C03C/C04/C10; audit06; retained; increasing constants alone insufficient |
| R33 | Replace Python scan with actual index-compatible pgvector queries | C02/C13; audit01; retained; declared vector column does not complete migration |
| R34 | Shared-memory Chat with complete scroll/composer/stream/error/stop/mobile UX | C08/C09/C16; audit04; retained; approved assistant-ui selection retained |
| R35 | Scoped history/resume; no copied history/replayed effects/duplicate learning | C10/C04; audit04; retained |
| R36 | Supported actual model image/document input, preview/citations/failure | C11/C08; audit05; retained; camera access remains conditional technical mechanism |
| R37 | Authorized general/read/write/delete/imported tools and confirmations | C08/C11; audit05; retained; no Background grant union or replacement filesystem |

## October 7 extension — bounded, not replacement goal

| ID | Current trace | Review |
|---|---|---|
| DA-R01 | C17B; audit07 | Standalone Decisions only; GPT-Live excluded |
| DA-R02 | C14/C15/C17A/B; audit07 | Finite supplied choices per call, not fixed entire learned catalog |
| DA-R03 | C14/C15; audit07 | Definitions/capability/current policy authoritative |
| DA-R04 | C06/C03C/C14; audits02/06/07 | Provisional preparation cannot become successful final workflow evidence |
| DA-R05 | C03C/C08/C14; audits06/07 | Proposal/execution/outcome/inference separate |
| DA-R06 | C03C/C14; audits06/07 | Actual causal links/available-at-decision evidence, not hindsight |
| DA-R07 | C04/C14; audits06/07 | Complete authorized final evidence and truthful summary availability |
| DA-R08 | Selector plan O-DA-A and learning-plan historical audit; audit07 | Retained, but explicit register allocation missing (F04) |
| DA-R09 | C14; audit07 | Cited inactive proposals; not implicit activation |
| DA-R10 | C06/C15; audit02 | Immediate edit invalidation, parallel context, final validation |
| DA-R11 | C14/C15/C17B/C16; audit08 | Runtime/data removability, not merely separate Git branch |
| DA-R12 | C16; audit08 | Prediction waste/stability separate from final route/outcome/usefulness |

## Findings — not waived by goal coverage

### F01 — conflicting source-ledger instructions (material, HOLD affected capture contract)

Reconciled scope and module/analysis headers correctly withdraw C03B's extra user-final row pending necessity proof. But module plan's final “Reviewed foundation allocation” still says C03B adds the ledger and C08 uses C03A/C03B; analysis “Phase02 canonical evidence storage” still declares vault_conversation_events the one canonical final ledger. These are candidate design commitments, not historical quoted requirements. A header override alone leaves two consequential build interpretations.

Required correction before READY: resolve those exact body dependencies and proposed DDL against existing source owners. Preserve R12/R22/R23/R32/DA-R04–07 coverage, ordering/recovery and causal metadata. Do NOT infer that withdrawing one redundant user event removes the need to capture missing model/tool/selection evidence. Do NOT silently choose either an unconditional new ledger or no new metadata.

### F02 — stale next-build instructions (material, HOLD restart instructions)

Master r10 top says C01/C03A/C17A built and next source-repair review; its “Ready-to-build sequence clarification” still says next sequential build C01. Earlier PROJECT-STATE/README sections also retain CURRENT/READY wording. The top override prevents authorization, but the documents are not yet clean restart instructions.

Required correction before build handoff: explicitly mark superseded lifecycle passages historical and remove them from active entry paths. Preserve old evidence/manifests; don't rebuild foundations or rewrite historical proof to appear current.

### F03 — stable capability mapping is required, representation remains undecided (trace clarification)

Original R17 and controlled terms require provider-independent semantic operation mapping. Audit07 and the October7 amendment establish it is not supplied by present tool_id fields. Reconciled boundary rule6 still asks whether additional semantic capability descriptions are needed. Need for the behavior is settled; only minimal representation/reuse is open.

Required contract clarification: C15 must own and prove explicit semantic capability-to-current-tool/schema/effect resolution, including unavailable/ambiguous providers. Reuse ToolCatalog/current grants. No parallel grant engine or guessed model equivalence; no additional integration is authorized by invoice/SMS examples.

### F04 — historical read-only qualification needs an explicit execution allocation (trace gap)

The original history/continuation goal is present in C10. The October7 extension separately asks whether retained old evidence can teach procedures; its O-DA-A read-only qualification remains in selector/learning plans, but register r3 has no explicit delivery allocation for it. This is not permission to inspect private history now or a reason to block new truthful capture.

Required clarification: attach O-DA-A to an existing source/history contract or separately bounded read-only evidence task. Specify authorized scoped access and truthful missing-link/truncation reporting. No old tool replay, inferred reasoning, reviewer publication or production export by default.

### F05 — repository-wide donor/NEW entry incomplete (process gate)

The feature donor map read for this review has no live-memory/Chat/Decisions change row linking the current grounding, exact reusable paths and NEW gaps. Reconciled scope/individual contracts identify reuse and NEW behavior, but do not replace the repository's required donor-map gate. This finding does not establish a new donor or license approval.

Before another build: reconcile that map with inspected sources/approved assistant-ui and pinned VoiceMem research; distinguish existing ported memory/Voice authority from new controller/procedural/adapter behavior. No blanket “NEW” label authorizes rewriting existing features. This is a documented prerequisite, not a new product requirement.

## Material decision gate and conclusion

Question: does reconciled work still serve the October4–5 goal, or may remaining gaps be dropped/replaced? Authority: original request/R01–37 and explicit bounded October7 extension; actual revised documents above. Alternatives: declare whole plan READY from coverage; discard old goals to match implemented foundations; preserve all outcomes and hold affected ambiguous instructions. Selected: preserve the full grounded outcome, keep existing code, and record correction/trace gaps before READY. Counterexample: a build reimplements C01, removes voice/VoiceMem scope, skips causal capture after withdrawing C03B, or treats known tool IDs as semantic mappings. Dependents: capture/source, C08/C14/C15, restart and donor gates. Result: **CONDITIONAL alignment; affected build instructions HOLD.**

No missing original core goal was found in reconciled scope. No new product, hosted dependency, agent identity, grant, model/retention policy, fixed taxonomy or guaranteed latency was authorized. Adoption of a specific VoiceMem subset, OAuth entitlement, activation and numerical acceptance remain the same dependent questions as the original grounding. Source repair is a dependency review supporting lossless evidence—not a replacement end goal or permission for a broader rewrite.

Next authorized work is document/contract correction of F01–F05, then review the bounded delta against current source. This review does not reopen the original goal or ask Christian to choose it again. It does not certify feasibility, implementation, production state, or owner acceptance.
