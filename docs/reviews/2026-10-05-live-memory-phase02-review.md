# Phase02 — plan attack, corrections and dependency partition

2026-10-07 applicability notice: historical review only. The
[Decisions/evidence amendment](../planning/2026-10-07-decisions-api-evidence-grounding.md)
requires renewed planning/review of affected evidence, draft attribution, history,
mapping, learning and provider boundaries. This review does not cover the amendment
or approve its candidate recommendations. Frozen October5 manifests are retained.

Review ID LMD-PR02-r1. Reviewer type: same-model/context INTERNAL SELF-REVIEW.
No independent or external review, no owner acceptance inferred from component
approval. Input candidate master r4/grounding r10 is preserved in r4 hash manifest.
Corrected candidate master r5/grounding r11/module r3 bound by current manifest.
Source files bound by review-source manifest; runtime base ea39a6f9da89a2999c4f7e14f686428d2088f480.

## Frozen scope / independently reconstructed purpose

Read original user requests and current grounding/source inventory before plan
rationale. Required outcome: clean modular optional live context that improves
correct retrieval AND useful response timing; actual pgvector/HNSW; preserved
canonical memory agent+embeddings and complete captured-session review; separate
Chat with reliable UX/history/attachments/full authorized tools, existing Voice
mode persists; actual available reasoning evidence; no third agent/permission
store; Decisions API deferred. Assistant-ui MIT components selected by owner.
No token access/model entitlement, unlimited context, production retrieval speed,
perfect recall or automatic rule-activation authority inferred from these requests.

Failure criteria: mixed host/new-module responsibility, scope leak, stale final
context, duplicate learning/tool effects, truncation hidden by counters, UI proxy
for working model input, unbounded workers/cost, unsupported provider entitlement,
missing recovery/erasure, premature readiness. Owner handles retention/defaults/
activation/numeric release commitments; maintainer future capacity not unlimited.
Research can invalidate candidate but doesn't grant new behavior.

## Findings and classifications

| ID | Severity / exact evidence | Violated requirement | Dependents | Class | Resolution |
|---|---|---|---|---|---|
| F01 | Major: module plan proposed GET/PATCH; local_api/server.py has GET/POST/PUT/DELETE only | Executable interface consistency, R30 | Preference API | Correction | Use GET/POST; corrected governing/module plan |
| F02 | Major: LocalApiResponse only payload/body; server._send encodes complete bytes/Content-Length | R24/R34 actual streaming/pending | O4/O5 | Correction | Explicit owned streaming iterator/cancel/replay+HTTP host adapter prerequisite; no assumed support |
| F03 | Major: static server Permissions-Policy camera=() | R36 actual capture | Camera mechanism only | Correction | Camera conditional reviewed self-only capability; paste/file/screen paths independent |
| F04 | Major: models.MemoryRecord lacks epoch; TranscriptEntry lacks metadata, despite proposed columns | R04/R18/R22/R32/R35/R36 | Final validation/source analysis | Correction | Explicit batch typed loaders/metadata/citation mapping prerequisites |
| F05 | Major: jobs/blobs/provider refs/cache need deletion/stop owners; app.close currently stops Background/A2A only | R01/R18/R31/R35/R36 | All new persistence/workers | Correction | Register own cleanup/stop through narrow adapter before activation; cascade not sole proof |
| F06 | Major: per-snapshot completed fingerprint doesn't dedupe continued-history candidates; repository append index conflict ignores changed payload | R32/R35 | Analysis/history | Correction | Contributions+coverage atomic canonical unit-of-work; conflict payload rejection and legacy coverage unknown explicitly retained |
| F07 | Major: voice/tools.py claim requires live Voice session; memory.tools remember/confirm requires Voice entry; one catalog observer | R37/R13/R31 | Chat tools/evidence | Verification/correction | Separate conversation claims/confirmation + composed observer; no fabricated microphone session or grant union. Earlier plan already named requirement; inspect actual behavior in later contract |
| F08 | Blocker-dependent: no verified OAuth transcribe entitlement or controlled response/audio handoff | R05/R29 | Dedicated OAuth O5 only | Verification | Remains conditional; not solved by existing bearer call or reconnect. Does not block C01/chat planning |
| F09 | Blocker-dependent: retention/forget replay/activation/default scope+numeric quality budgets unresolved | R11/R16/R21/R30/R35 | Historical rebuild, release, procedural routing | Verification | Reserved, no invented defaults; unaffected small foundation can proceed |
| F10 | Minor evidence gap: assistant-ui peer/version compatibility unestablished | R34 selected component | O4 install/runtime contract | Verification | npm latest metadata obtained: react0.15.23/react-markdown0.14.18 MIT and React18/19 peers; no bundled/runtime validation claimed |
| F11 | Major readiness ambiguity: “everything covered” could imply all build contracts ready | Protocol readiness, R26 | Delivery | Correction | Explicit partial plan pass and C01 foundation; all other dependent contracts remain unready |

Cycle1 corrections governing r11 then dependent plans propagated and rehashed.
Re-review source mismatches F01–F05: corrected statements match source constraints;
no runtime fix claimed. F06/F07 counterexamples remain mandatory tests/build seams,
not proven by prose. F08/F09 retained blockers on dependent outcomes. No second
cycle needed; no issue waived to reach a universal PASS.

## Requirement trace (all37; outcomes acceptance by Christian)

Each row connects original authority in grounding → D gates/module ownership →
outcome/design → positive/negative proof → operating evidence/rollback. Exact
feature tests and recovery are in linked owned plans; this table is not duplicate
policy. Planned tests for absent features were not executed.

| Requirement | Outcome / deliverable | Positive / negative proof | Evidence / recovery |
| R01 | O2/C01 + O3/O6 modules | Replace backend/disable optional component; reject mixed host duty | C01 parity+dependency review; legacy/no-op adapter |
| R02 | O3/O5 revisions | Normalize delta/edit; reject wrong item/final | Revision/voice traces; disable adapter |
| R03 | O3 scheduler | Bound/coalesce work; noncancellable request retains budget | Load/waste metrics; stop preparation |
| R04 | O3 epochs | Current result only; reject ABA/delete/revoke | Race tests; invalidate/final search |
| R05 | O3/O5 final handoff | Validate before reply; reject changed-final reuse | Actual final/context/audio trace; final fallback |
| R06 | O2/C01 canonical SearchPort | Preserve scope/evidence; no second store | Default parity then scoped DB proof; legacy search |
| R07 | O2/O7 indexed queries | Actual SQL HNSW; reject unused index/Python scan | EXPLAIN/exact recall; query flag |
| R08 | O7 definitions/examples | Version-linked examples; never executable similarity | Procedural schema/evidence; inactive generation |
| R09 | O8 scoped rule eligibility | Collapse valid candidates; deny unscoped/underfill proxy | SQL+runtime negative tests; model fallback |
| R10 | O8 selector/fallback | Selector absent ordinary model; no guessed API | Adapter absence tests; disable selector |
| R11 | O4/O8 current grants | Authorized tool works; revoke before call denies | Real call/confirmation trace; no action replay |
| R12 | O0/O6 final evidence | Correlate outcomes; drafts not sources | Evidence replay/crash; preserve accepted source |
| R13 | O0/O6 independent consumers | Procedure fails memory survives; no duplicate publication | Recovery transaction tests; disable procedure |
| R14 | O7 dedup | Paraphrases merge; invoice/account actions stay distinct | Held-out semantic cases; inactive proposal |
| R15 | O7/O8 confidence | Observed outcome/ambiguity defer; similarity not permission | Outcome/counterexample labels; ordinary model |
| R16 | O7 generations | Atomic rebuild pointer; no forgotten fact/source deletion | Crash/deletion tests; prior generation |
| R17 | O8 capabilities | Current provider resolves; removed tool ineligible | Catalog-change tests; rule retained inactive |
| R18 | O2/O3/O7 epochs | Valid scoped cache; deny stale metadata/grants | Batch invalidation tests; clear derived cache |
| R19 | O4 separate page | Chat navigation works Voice persists; no hero replacement | Browser active Voice navigation; unmount Chat |
| R20 | O4/O8 local runtime | Works without Link; rules dont grant connectivity | Standalone test; retain existing authority |
| R21 | O1/O9 useful speed | Paired useful response gain; reject filler/database proxy | Representative timing/cost; Live Off |
| R22 | O0/O4/O5 summaries | Actual available summary correlated; absent truthful | Provider response evidence; preserve raw final outcome |
| R23 | O6 reviewer evidence | Failed/corrected tool bounds summary; no inference-as-original | Procedural semantic cases; inactive proposals |
| R24 | O4 text model | Text/memory/tools without mic; no Help misuse | Actual stream/turn trace; unmount Chat |
| R25 | O3/O4 parallel preparation | Draft+memory reconsider; stale branch discarded | Revision tests/overlap metrics; normal final |
| R26 | All, phased contracts | Branch/docs precede contracts/build; no accidental scaffold | Git/source manifests; stop phase |
| R27 | O1 research-first | Pinned primary source and same corpus; no starcount-as-proof | Research+controlled experiment; baseline engine |
| R28 | O1/O3/O9 quality+speed | Strong labels+useful timing; reject good recall slow audio | Paired semantic/latency evidence; reopen choice |
| R29 | O5 OpenAI transcription | Live deltas before commit; no donor ASR | Actual model/access trace; existing voice |
| R30 | O3 live-only switch | Off stops drafts not learning/final search | Switch/race/removal; final search intact |
| R31 | O0/O2 store+agent retained | Canonical IDs/analysis survive; no Background ownership | Repository/role regression; existing authorities |
| R32 | O0 full history | Tail/many-fact/correction captured; counter insufficient | Semantic long-session+coverage jobs; truthful incomplete |
| R33 | O2 indexed execution | Authorized nearest neighbors SQL; no fetch-all Python | EXPLAIN+recall/restore; legacy flag |
| R34 | O4 complete UX | Scroll/IME/wait/mobile correct; no rushed textarea | Real-browser geometry/accessibility; unmount Chat |
| R35 | O4-H incremental learning | Resume old context/new once; no history/tool replay | Coverage/relogin/concurrency tests; disable continuation |
| R36 | O4-A multimodal input | Model gets image/file; no preview-only success | Actual model-input/capture/limits; remove adapter |
| R37 | O4 tools parity | Authorized writes; no grant union/fake Voice session | Catalog+claim/confirmation tests; existing runtime unchanged |

## Decision and permitted next action

Decision: PASS for dependency-ready O2 foundation/C01 only; overall plan CONDITIONAL
with F08/F09 and downstream integration proofs open. This partition is outcome-
specific, not universal execution readiness. Corrections are authorized by existing
requests, not new scope or acceptance of material risk. No grant/retention decision
made. Contract C01 is separately reviewed and can progress without those blockers.

Baseline rerun2026-10-05:23 focused memory/contracts/reviewer/evidence/voice schema/
scoped catalog/tool tests passed0.88s. This is existing source behavior, not evidence
of new module/HNSW/live/UI. npm metadata read only; no package installed. Relative
links/hash/whitespace checks separately recorded; no production DB, destructive
fixture, live OAuth/model/audio, visual browser or independent reviewer executed.
First contract review frozen against corrected inputs; exact review hashes live in
Phase02 manifest outside reviewed content. Next route Phase03 C01 only; stop after.
