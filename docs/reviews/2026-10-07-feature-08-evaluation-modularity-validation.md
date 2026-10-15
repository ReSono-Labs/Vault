# Feature 08 — measured acceptance, modularity and removal

Validation date: 2026-10-07. live-memory-evaluation-plan r2 and modular-codebase-integration-plan r6 were read in full. Earlier isolated build evidence is considered only for its named component.

Verdict: three isolated foundations exist; integrated evaluation and full module removal/lifecycle guarantees are NOT implemented or demonstrated.

| Required outcome | Evidence / disposition |
|---|---|
| Search engine boundary preserves canonical callers | C01 MemorySearchBackend.retrieve/default legacy adapter and unit tests implemented; planned `search(...)` signature is not current code |
| Immutable conversation identities without fake Voice sessions | C03A implemented, unmounted; consume existing schema rather than repeat it |
| Optional finite selector without SDK/startup requirement | C17A implemented, unmounted; no live adapter imported |
| Live/VoiceMem/transcription/learner/history/attachment/tool modules behind small ports | Proposed modules/ports not mounted or implemented; no integration removal proof |
| Shared host contains only auth/delegation/composition | Existing host does not contain the proposed runtime; future allowlists are not blanket build permission |
| Independent Off controls, epochs, current scope checks and worker accounting | No live preference/controller/new worker lifecycle; not implemented |
| Stop/logout/revoke/erase invalidates pending requests and caches | New runtime absent; existing cleanup cannot prove future workers stop |
| Canonical memory/Voice still work after optional generation/module deletion | Foundations have bounded compatibility proof; integrated deletion/removal acceptance absent |
| Frozen corpus, model/index/source identity and semantic gold/tuning split | No executed comparative experiment documented |
| Final-only vs indexed vs VoiceMem comparison | Not executed; no SQL index delivery or VoiceMem integration to compare |
| ANN recall vs exact SQL separate from semantic relevance | Not executed; cosine unit tests are neither benchmark |
| Prefix shifts, trailing negation, delete/paste/IME/ABA/rapid Send | No mounted draft flow or integrated race suite |
| Aliases, temporal contradictions, evidence combinations and abstention | No integrated held-out acceptance evidence |
| Revoke/delete/generation switch/Off mid-job | No new integration acceptance evidence |
| Outages, slow/noncancellable workers, concurrency and bounded waste | No runtime load/cost evidence |
| Voice unordered events, commit/barge-in and controlled context handoff | Existing Voice tests do not demonstrate proposed experimental path |
| Monotonic stage timings and clock-safe useful played audio | No paired end-to-end timing corpus; first token/filler is not accepted useful response |
| p50/p95/p99, sample counts, confidence intervals, warm/cold, costs/reuse | Not measured for this feature |
| Browser Chat geometry, persistent Voice navigation, history zero-call reads | No Chat UI/history path; no corresponding browser acceptance |
| Actual model image/file input and authorized write/effect-unknown recovery | No submitted attachment/Chat tool path or real-provider acceptance |
| Prediction stability vs final route/execution/usefulness; hindsight/injection fixtures | No integrated reviewer/controller; parser tests cannot substitute |
| Representative operating acceptance and approved numerical limits | Not supplied/accepted; no threshold is invented by this audit |

Preserve existing component proof. Do not call absent runtime 'modular' solely because plans name directories. Build contracts must identify actual injection, cleanup and erasure callers, plus meaningful behavior/removal tests, before implementation. No production default or READY release follows from this inventory.
