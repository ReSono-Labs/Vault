# Change index

## 2026-10-08 — completion pass under existing contracts

The [current register](contracts/2026-10-05-live-memory-build-contract-register.md)
and first CURRENT section of [project state](planning/PROJECT-STATE.md) own status.
Existing C03A, C08A and C04D were amended in place for history/channel/input and
Voice recovery work. No new contract document was added. Historical absence
statements must not trigger duplicate implementation.

## 2026-10-07 — C13A canonical vector publication guard

[Reviewed contract](contracts/2026-10-07-LMD-C13A-atomic-vector-write.md) and
[build evidence](reviews/2026-10-07-LMD-C13A-build-evidence.md) preserve the
canonical write path, repairing reproduced read/upsert and snapshot-version races.
No schema/production cutover; register owns current lifecycle.

## 2026-10-07 — bounded VoiceMem/shared-context component

[Source review](reviews/2026-10-07-LMD-C05A-source-review.md),
[r2 contract](contracts/2026-10-07-LMD-C05A-C06A-live-component.md) and
[build evidence](reviews/2026-10-07-LMD-C05A-C06A-build-evidence.md) track actual
unmounted extraction, parallel recall/decisions and cancellation/worker proof.
Full C05/C06/production adoption not delivered; current register owns lifecycle.

## 2026-10-07 — C02 indexed SQL grouping / LC shared-context clarification

[C02 evidence](reviews/2026-10-07-LMD-C02-build-evidence.md) and
[contract](contracts/2026-10-07-LMD-C02-indexed-query.md) freeze actual SQL/index
proof without production cutover. [LC-R01–04](planning/2026-10-07-live-recall-context-grounding.md)
records one evolving memory/decision context and retained VoiceMem scope. Register
owns current lifecycle; original grounding and old frozen manifests preserved.

## 2026-10-07 — bounded C03R source repair

[Contract](contracts/2026-10-07-LMD-C03R-source-capture-repair.md) and
[build evidence](reviews/2026-10-07-LMD-C03R-build-evidence.md) cover only the
existing provider/transcript transaction seam. No new ledger or feature-wide
completion. Current status remains owned by the build-contract register.

## 2026-10-07 — grounded document authority consolidation

[One current document set](planning/2026-10-07-live-memory-document-authority.md)
preserves original October4–5 grounding; [correction review](reviews/2026-10-07-grounded-document-consolidation-review.md)
closes five alignment findings. Register owns build status; old checkpoints and
withdrawn parent/extra-event designs are historical. No runtime change in this correction.

## 2026-10-07 feature-by-feature validation checkpoint

[Feature index](reviews/2026-10-07-feature-validation-index.md) links eight complete
owned-plan/source reports. [Reconciled scope r2](planning/2026-10-07-live-memory-reconciled-build-scope.md)
updates master r10/module r7/analysis r6/register r3. Retain C01/C03A/C17A;
withdraw C03B duplicate-event readiness. Documentation only; no new runtime build,
production migration/provider call/history inspection or deployment.

[Frozen validation inputs](reviews/2026-10-07-feature-validation-source.sha256)
capture inspected runtime/frontend/tests and controlling plans/reports; verification
passed. Final focused regression: 197 distinct tests passed. This does not certify
production database/index state, historical evidence or provider access.

## 2026-10-07 — all-contract code audit; prior-build baseline hold

[Every contract/allocation](reviews/2026-10-07-LMD-all-contracts-code-audit.md)
compared with inspected main/current files, including untracked implementations.
180 focused tests PASS; full units443 PASS/four recorded failures. Existing Help,
uploads, memory/embedding/review/Voice/tool infrastructure explicitly retained.
Owner reports a later full build, not yet located: [discrepancy evidence](reviews/2026-10-07-LMD-completed-build-baseline-discrepancy.md).
No rebuilding, no remaining-count claim, no runtime changes. Historical C01 revisions
and C03/C17 parent instructions explicitly held/superseded.

## 2026-10-07 — duplication audit supersedes C03B READY

[Actual-code findings](reviews/2026-10-07-LMD-duplication-audit.md): repeated
conversation/Voice authorization predicate confirmed; proposed extra final-user
event necessity unproven. C03B READY withdrawn, builds halted. Existing memory
store/reviewer/vector infrastructure retained. Earlier counts/readiness are not
current implementation authority; remaining package reconciliation outstanding.

## 2026-10-07 — C03B/r1 bounded capture contract READY

[Contract review](reviews/2026-10-07-LMD-C03B-contract-review.md) corrects stale
identity ownership and freezes atomic final-turn evidence, exact SQL/scoped keys,
retry/rollback/pagination/erasure tests. Remaining full capture allocated C03C;
source completeness explicitly unestablished. Documentation only; next Phase03
C03B/r1. Internal review, no owner acceptance or production change.

## 2026-10-07 — C17A/r1 verified offline selector

[Build evidence](reviews/2026-10-07-LMD-C17A-build-evidence.md): immutable finite
mapping, strict official-shaped projection/parsing, no-op and stale/cancel/deadline
rejection.107 selector tests/181 focused regressions pass; broad suite retains four
existing failures. No live API/routing/learning activation. Next Phase02 C03B review.

## 2026-10-07 — C03A/r1 verified conversation foundation

[Build evidence](reviews/2026-10-07-LMD-C03A-build-evidence.md): unmounted private
conversation/segment/final-turn storage and account-erasure hook. 51 real database
tests,74 focused units/regressions and14 existing identity integrations PASS.
Internal review only; no production migration, chat UI or model execution.
Next staged contract C17A/r1, with dependent capture/chat review still required.

## 2026-10-07 — C01/r3 verified search boundary

[Build evidence](reviews/2026-10-07-LMD-C01-build-evidence.md): optional backend
injection and legacy delegation, preserved default behavior and callers. 41 focused
tests pass; four unrelated broader-suite failures reproduced with baseline service.
Internal self-review only. No HNSW/live/API/UI implementation; next Phase03 C03A/r1.

## 2026-10-07 — reviewed staged-build entry

[Split review](reviews/2026-10-07-decisions-split-contract-review.md), internal
self-review; C01/r3, C03A/r1 and C17A/r1 READY scoped roots. Exact current plan,
source and contracts/review identities in planning/2026-10-07-decisions-build-*.sha256.
Breaks capture identity and SDK/access circularities; includes tombstone-account
erasure proof obligation. No production mount, paid calls, active rules or build.

## 2026-10-07 — Phase02 code-grounded Decisions/evidence review

[Review](reviews/2026-10-07-decisions-plan-and-contract-review.md) LMD-DA-PR02-r1,
same-context self-review.11 findings; correction cycle1. Grounding amendment r2;
master r7/module r4/learning r4/selector r2. Exact corrected plan/source/review package
manifests linked in PROJECT-STATE. C01/r2 READY bounded foundation; C03/C17 drafted
but dependency-blocked; no whole-system READY or owner acceptance.20 baseline tests
pass; no code/schema/SDK/provider/history changes. Historical manifests preserved.

## 2026-10-07 — Phase01 Decisions/evidence candidate

Owner requested direct prompt execution. [Selector plan](planning/2026-10-07-decisions-selector-plan.md)
and updated owned plans cover DA-R01–12. Master r6/learning r3; current identity
planning/2026-10-07-decisions-plan-candidate.sha256. DRAFTED/CONDITIONAL, not reviewed
or build-ready. Existing manifests preserved; no implementation or session audit.

## 2026-10-07 — Decisions API and speculative evidence amendment

Documentation only: [grounding amendment](planning/2026-10-07-decisions-api-evidence-grounding.md),
LMD-DA-G-2026-10-07-r1. Original r11 unchanged; affected plans/review/register
marked for revalidation. Phase00 only, next Phase01. No Live migration, runtime
changes, history audit/publication, branch switch or provider calls.
Exact saved identity: planning/2026-10-07-decisions-grounding.sha256.

Links to change authorities and evidence. Current state remains in
[planning/PROJECT-STATE.md](planning/PROJECT-STATE.md); historical changes are
recorded in [CHANGELOG.md](../CHANGELOG.md). This index begins with the
2026-10-04 documentation checkpoint and is not an exhaustive past-change ledger.

## 2026-10-04 — modular live memory, learned decisions, and Vault chat

Primary type: `project` (review/grounding documentation; no feature shipped).

- Governing requirements/decisions: [change grounding](planning/2026-10-04-live-memory-decisions-grounding.md), `LMD-G-2026-10-04-r5`.
- Code inventory, primary-source research, self-review, checks and limits: [review](research/2026-10-04-live-memory-decisions-code-review.md), `LMD-REVIEW-2026-10-04-r2`.
- Product authority: [GROUNDING.md](../GROUNDING.md), change pointer only.
- Plan/build contract/implementation: none created in Phase 00.
- Operational protocols affected: none; no deployment or runtime operation changed.

Frozen file identities (SHA-256; entire linked file contents, excluding this
index and mutable project-state commentary):

```text
f32cc53b46b4c25e8732e740cfb7c24d8535f1aebb2a4812a88e33b76d2899a0  docs/planning/2026-10-04-live-memory-decisions-grounding.md
53d80e42082b77c6b076a077c8694155bdbb4f294b5c6b162f316e0e60ff1aef  docs/research/2026-10-04-live-memory-decisions-code-review.md
```

Recompute before dependent planning. A changed identity requires revalidation;
these hashes establish saved content, not semantic correctness or acceptance.

r2 incorporates the owner's reasoning-summary/text-model/parallel-context
clarification. Prior r1 inputs are superseded; downstream review must account
for the added requirements before relying on this checkpoint.

Grounding r3 additionally records live draft/Send handling, proposed hybrid
code/model selection and latency/cost/quality evaluation. Grounding r2 is
superseded; evidence review remains r2. No planning/build stage was started.

Grounding r4 resolves product mapping through owner confirmation: Vault is the
Link Personal/Business Agent package. Grounding r3 superseded. Evidence review
remains r2.

Grounding r5 records provisional permission to process partial drafts with
configured providers before Send for testing and later reassessment. Grounding
r4 superseded; evidence review remains r2. No implementation started.

## 2026-10-05 — research and current-memory review checkpoint

Branch: `feature/live-memory-decisions`. Type: documentation; no feature shipped.
Controlling grounding r7; Phase 01 IN PROGRESS. Prior r5 hashes remain historical.
Working drafts: [planning index](planning/2026-10-05-live-memory-delivery-plan.md).
Current inventory/overlap review: [review](research/2026-10-05-current-memory-implementation-review.md).
Owner requirements now include complete-session analysis, actual HNSW retrieval,
OpenAI live transcription and live-only switch, preserving canonical memory
agent/store/analysis/embedding and excluding the separate Background Agent.
No frozen complete plan, new build contract, runtime edits or deployment.

Saved artifact identity (SHA-256, checkpoint only; not review approval):

- `docs/planning/2026-10-04-live-memory-decisions-grounding.md`: `27fa18c0d62a6d01876b93f8944a76d7c083e2e34d0c9244c051dc38ee767b20`
- `docs/planning/2026-10-05-complete-session-memory-analysis-plan.md`: `0f2c5b512568af2e2e1d9406091c41aee96a6d6ab8ee041fca1418bf1b5c9cb6`
- `docs/planning/2026-10-05-decision-learning-plan.md`: `2a1f96f52f734bbfeca905107b7a9b9792faccca5972889ed66752ce91142678`
- `docs/planning/2026-10-05-live-memory-delivery-plan.md`: `28f0cd397584d8f198c52618cf3c31e9328485acb72c9303ca4eaec08e51647d`
- `docs/planning/2026-10-05-live-memory-evaluation-plan.md`: `a6e22d77ee3bd3bd0c6085723d9e24527afc0cabeaa49371d29a91933cb6a48d`
- `docs/planning/2026-10-05-live-memory-runtime-plan.md`: `361baa38db70e1da57304f4c8e2cce8df65d1a53e9d72caae6d7724587c633e2`
- `docs/planning/2026-10-05-vault-conversation-plan.md`: `b0183e8386b7b9c030f59654f5c0f7c97ea114393ffcab3ed9a12368b0723a7e`
- `docs/research/2026-10-05-current-memory-implementation-review.md`: `932302bf17f05502dbd4fe2beafdd2f946d8b1db80dfbb633b226824a4b73407`
- `docs/research/2026-10-05-live-memory-retrieval-research.md`: `6fce0284ec885a7867f5981d86567c57f07fbbe67726037d3c36a65a9ba4e1f8`

## 2026-10-05 Phase 01 frozen draft candidate

Grounding r8; master LMD-PLANNING-INDEX-r2. Exact saved planning and evidence
identities: [SHA-256 manifest](planning/2026-10-05-live-memory-plan-candidate.sha256).
Planning is conditional and unreviewed; no runtime implementation. Regrounded
from disk after compaction; explicit modular code seams, indexed pgvector upgrade,
full-session analysis and OpenAI transcription/OAuth capability boundary added.
Old hashes/review identities are historical and do not approve this candidate.

## Separate Chat expansion — r9 grounding/r3 planning candidate

Prior r2 candidate is preserved as historical hash manifest, superseded for this
expanded scope. Latest manifest includes separate Chat UX, history coverage,
attachments/tool parity and read-only research/static tool inventory. Voice page
replacement is withdrawn; no runtime edits. SHA-256 verifies saved candidate only,
not semantic review or acceptance.

## Component approval — grounding r10/master r4

assistant-ui MIT verified; owner open-source condition satisfied. Updated current
candidate hashes; preserved r3 historical manifest. No runtime/dependency changes.

## Phase02 review/contracts checkpoint — r11/r5/r3

Plan corrected against codebase; internal self-review only. LMD-C01/r1 READY
for search foundation; other outcomes conditional/unready. Exact review+contract
identities in [Phase02 manifest](planning/2026-10-05-live-memory-phase02-candidate.sha256),
which binds plan/source manifests; excludes itself/checkpoint/changelog. Runtime
sources separately fingerprinted; no implementation made. Prior r4 candidate
manifest preserved as historical identity; no old PASS approves new content.
