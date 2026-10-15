# C04D — complete-session windowing source review

Status: PARTIAL parent. Register r48 owns current allocation. The October8
completion amendment at the end extends existing factual Voice analysis/recovery;
full procedural windows/qualification remain open. Original complete-session
requirements and existing C04A/B/C recovery remain binding. The source inspection
below is historical rationale, not a renewed absence audit.

## Existing implementation to extend

- `memory/chat_learning.py::_read` rejects more than 256 turns, more than 256
  tool results per turn, and entries longer than 16,384 characters. It fingerprints
  canonical final inputs, redacted tool results and original final answers.
- `OpenAIMemoryReviewer.review` rejects inputs above 100,000 characters. The
  existing parser rejects more than 32 candidates; neither is pagination.
- `ChatMemoryLearning.finalize` retains one validated review in the existing
  segment row, limited to 150,000 serialized characters. Model/provider/source
  bindings and publication/completion are checked transactionally.
- `MemoryPipeline.reconcile_review` owns canonical publication for both channels;
  `embed_records` owns best-effort embedding. Preserve these shared seams.
- `ConversationRuntime` and `ConversationRuntimeStore` already own bounded review
  dispatch, advisory locks, authority resolution, three attempts and restart.
  No second queue, worker, lease framework or Background agent is justified.
- `MemoryRepository.reconcile_memory` currently stores `excerpt[:16384]` after
  checking authority/nonempty text, without rejecting excessive excerpt length.
  Chat's current producer guard prevents that path for its bounded entries; a
  new source-span adapter must not pass an oversized original excerpt and claim
  that the whole cited evidence was preserved.

## Proposed delta and required review decisions

1. Page canonical sealed source by stable turn/tool ordering, using existing
   authority and snapshot fences. Replace the bounded-reader rejection only when
   a complete manifest can account for every retained source entry. Do not treat
   a paged prefix as a complete fingerprint.
2. Represent oversized entries as exact original source IDs plus character spans
   and source fingerprints. Map reviewer citation indexes reversibly to those
   spans; repeated local indexes cannot identify unrelated original entries.
   Bound each canonical evidence excerpt and preserve its span identity before
   publication. Review necessary persisted metadata rather than adopting the
   older four-table proposal automatically.
3. Extend the existing factual checkpoint with resumable window/consolidation
   outputs. Determine bounded row versus necessary child rows from real payload
   sizes; successful windows must survive restart without another model call.
   Reuse current dispatch and explicit exhausted-work retry.
4. Define explicit candidate-overflow/continuation semantics through the existing
   structured reviewer execution. A single dense entry cannot be solved merely
   by splitting at turn boundaries. No successful first-32 result or infinite
   recursive subdivision is permitted.
5. Consolidate all candidates in bounded batches with source-order corrections,
   authority and exact citations preserved. Do not publish window candidates
   before cross-window correction resolution. Reuse canonical reconciliation,
   suppression and atomic publication/checkpoint completion.
6. Keep factual and procedural results independent. This first contract must
   specify factual coverage only; it cannot label the procedural bounded source
   reader or Voice recovery complete. Existing small-session behavior and saved
   reviewed checkpoints need explicit compatibility rules.

## Required acceptance before VERIFIED

Actual mounted cases must cover a required fact after character 100,000; more
than 32 durable facts including dense single-entry evidence; more than 256 turns
and tool results; an oversized entry with a fact after character 16,384; late
correction across windows; restart after successful analysis; and retry after
failed publication without another successful model call or duplicate version.
Missing source spans, invented citations, source erasure, session revocation,
provider/model changes and retained-history forget suppression must fail safely.
Coverage counters alone do not establish semantic completeness.

Remaining before READY: exact source-span/checkpoint representation, bounded
consolidation/overflow protocol, compatibility and transaction/recovery review.
No runtime, schema, provider calls or historical backfill changed by this review.

Baseline: `.venv/bin/python -m pytest tests/unit/test_memory_publication.py
tests/unit/test_openai_memory_reviewer.py -q` — 10 passed. This baseline does not
exercise or prove the proposed window coordinator.

## October8 completion amendment — reuse Voice ingestion/checkpoints

Voice factual finalization now saves validated analysis and bounded window steps in
the EXISTING ingestion row, bound to original transcript fingerprint/provider/model.
Session advisory ownership serializes attempts. Successful analysis survives failed
canonical publication; summary, facts and completed-ingestion state commit atomically.
The same bounded factual reviewer/source-span coordinator used by Chat processes
Voice source windows; no copied transcript, new model, queue or publisher is added.

Voice close/finalize persist retry intent in the existing reference-only review
conversation/segment bridge. The existing dispatcher revalidates the original local
session and runs independent consumers with bounded attempts. A completed factual
consumer is not modeled again when procedural review fails. Unknown Voice causal
coverage remains analysis-only; recovery never turns unknown evidence into complete
publication qualification. This does not close the separate procedural source-input
window or real-provider acceptance requirements.
