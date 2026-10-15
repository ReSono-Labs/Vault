# Scope and duplication reconciliation — October8

Branch `feature/live-memory-decisions`. The original r35 audit below is historical
source evidence, not a current absence list or implementation order. Current scope
and status belong only to register r48 and the first CURRENT project-state section.
Original October4/5 grounding is unchanged. This evidence is not another plan.

The completion pass amends existing C03A/C08A/C04D in place. Both channels still
publish through MemoryPipeline; Chat memory confirmation reuses the pending-action
owner; Gemini uses the shared SDK runner; private inputs reuse managed storage;
Voice recovery uses the existing review bridge/dispatcher. The bridge FK is now
installed by one shared schema helper even without procedural review enabled.
There is no new contract document, system agent, permission authority, canonical
memory store or parallel model/tool runtime in this pass.

Current technical verification is being completed against the newer worktree.
Prior deployment evidence remains a record of the older package. Full feature and
release gaps remain explicit in register r48 rather than being hidden by build
success. The dated proof below retains its original limits.

## Concrete duplication found and corrected

C08B reused canonical storage but repeated the Voice pipeline's candidate-save and
embedding loops in its Chat adapter. This was real code overlap, not a second DB or
model. Extracted those exact loops into `MemoryPipeline.reconcile_review` and
`embed_records`; BOTH existing `MemoryPipeline.finalize` (Voice) and
`ChatMemoryLearning.finalize` now call them. Channel adapters own source projection,
source qualification and their existing checkpoint/ingestion transactions only.
No second reconciler, embedding provider, semantic scorer or grants system exists
in this correction. All candidate citations are checked before publication.

Inspection also found the existing Voice claim-denial fallback accepting summary
presence as completion. It now additionally requires `ingestion_completed`; partial
summary is not successful review. This does not claim recovery of every old partial
Voice ingestion.

## Recovery implemented without duplicating checkpoints

C04B extends the EXISTING `vault_chat_memory_reviews` row with `state`, `provider`
and `review_json`. Old rows default to completed. New successful analysis is saved
as reviewed only after source/scope/citations/model binding validation. Publication
and state=completed remain one canonical transaction. Explicit retry after failed
publication uses stored validated review and makes no second model call. Source,
review contract and current provider/model must match. Existing session advisory
lock is reused; no new worker, table, lease framework or agent is introduced.
Automatic process-restart recovery and complete source windows are NOT delivered.

## Source-backed build boundaries

| Concern | Actual existing implementation to preserve | Missing delta, not a replacement build |
|---|---|---|
| Chat/live display | `conversation/runtime.py`, frontend conversation module, `live_memory/chat_runtime.py`, shared VoiceMem/ParallelPreparation | Voice partial-transcript host; remaining parent UI/channel acceptance |
| Indexed memory | `memory_search/` SQL/HNSW/startup maintenance, `memory/service.py`, real scoped embedding store | Full release corpus/rollback acceptance, not another vector store/index implementation |
| Factual review/save | Existing configured `OpenAIMemoryReviewer`, shared `MemoryPipeline`, `VoiceMemoryLearning`, ended Chat adapter | Full bounded-window/dense-candidate/cross-window consolidation; current reviewer still rejects >100k/>32 |
| Procedural review | Existing shared model runner, `decision_learning/{voice_review,repository,reconciliation}.py`, Chat source/publisher/activation, scoped indexed examples | Full Voice source qualification/publication and complete-session procedural partitioning/recovery |
| Retry/completion | Procedural stage leases/checkpoints; factual Chat reviewed/completed row; canonical Voice ingestion records | Autonomous resume/complete source processing where missing; do not copy procedural leases into another equivalent store |
| Permissions/forget | Existing tool catalog/grants, final guards and canonical suppression | Remaining semantic/rebuild policy enforcement; no learned-rule permission bypass |

This is a focused reconciliation of the paths inspected, not a claim of exhaustive
semantic duplication analysis across the entire application. Existing attachments,
provider/confirmation parity and historical-audit allocations remain in register;
they are neither newly added here nor silently counted complete. No new features
were added to the original goal.

## Objective evidence and limits

- 15 actual isolated PostgreSQL checks passed: mounted Chat factual learning plus
  existing canonical memory/Voice pipeline suite. The failed-publication case now
  proves reviewed output remains durable, zero partial canonical facts, then one
  retry publishes with original model call count still one.
- 20 focused units pass: shared publication, original factual reviewer/contracts;
  covers pre-write citation rejection, suppression, original evidence/transaction,
  no fake vectors and summary-without-completion rejection.
- After the false-completion correction, the two actual canonical Voice pipeline
  persistence/vector checks were rerun directly and both passed (9 unrelated
  canonical memory checks deselected rather than repeating the whole suite).
- Existing completed Chat retry, real vectors/recall, session revocation and
  procedural independence remain covered in the actual mounted checks.
- `git diff --check` passes. No paid calls, installed database tests, donor edits,
  frontend redesign, deployment or new agent registration.

Historical child statuses saying “unmounted/next” were being read like current
instructions. Register header now explicitly resolves them through later mounted
children. Reconciled scope inventory carries a dated-observation warning. Historical
proof/manifests are retained, not rewritten as new evidence. Earlier “almost done”
descriptions were not a validated full-build completion estimate and must not drive
remaining work or cause verified code to be rebuilt.
