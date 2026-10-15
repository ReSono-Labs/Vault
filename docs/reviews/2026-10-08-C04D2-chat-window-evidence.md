# C04D2 — resumable factual Chat window evidence

Subsequent C04F owner-directed correction supersedes the context-compaction
allocation in this dated checkpoint: [Voice-pattern handoff/evidence](2026-10-08-C04F-session-context-evidence.md).
Register r43 owns current status; C04D2 measurements below are unchanged.

Branch: `feature/live-memory-decisions`, existing dirty owner worktree preserved.
Scope: [reviewed contract](../contracts/2026-10-08-LMD-C04D2-chat-window-review.md).
This is one delivered slice, not a full-build/release claim.

## Actual wiring

`ChatMemoryLearning._read` pages sealed original turns/tool results, keeps original
assistant-final identity and fingerprints the complete ordered source.
`finalize` selects the window path for oversized sources or dense legacy output.
`analysis_windows.bounded_review` calls the SAME configured OpenAIMemoryReviewer
structured runner with explicit hasMore/excludedKeys, validates global citations
and checkpoints every successful page through `ChatMemoryLearning._analysis_step`.
No extra scheduler, worker, reviewer identity, transcript or memory store.

Necessary child table `vault_private.vault_chat_memory_analysis_steps` is owned by
existing Chat learning schema; its DDL participates in schema fingerprinting.
Composite ownership FK, source/input/provider/model/contract fences, bounded JSON
and existing segment advisory lock protect saved steps. Parent review keeps its
reviewed/completed checkpoint, with a small windowed manifest on this path.
Publication uses existing MemoryPipeline/canonical transaction, with exact original
IDs/hash/offsets. Model identity and current authority are checked again before
checkpoint/publication. Summaries do not become source evidence.

Exact canonical-key groups use bounded same-model consolidation with citation
union; later corrections are represented in original global source order.
Distinct keys remain distinct. Continuation exhaustion, invalid citations,
nonadvancing pages or oversized consolidation explicitly fail, never publish a
partial prefix as completed. Legacy bounded checkpoints remain compatible.

## Focused proof

Only synthetic models and isolated real PostgreSQL/pgvector at
`127.0.0.1:55436/resono_vault_test`. No installed/history database, paid provider,
deployment or donor writes.

- `tests/unit/test_memory_analysis_windows.py`, `test_openai_memory_reviewer.py`,
  `test_memory_publication.py`: **18 passed**. Dense continuation/resume, precise
  original spans, late cross-window correction, invalid/repeated/empty progress,
  summary-model mismatch before checkpoint, actual typed reviewer protocol and
  existing shared publication regressions.
- New mounted long-source test plus existing mounted Chat factual tests:
  **5 passed** (30.32s) before the extra tail-provenance assertion was added.
  Existing small-session save/vector/recall/idempotence, failed publication,
  invalid citation and revoked authority regressions remain covered.
- Final long-source scenario uses three actual captured Chat turns totaling
  >132k characters;40 dense initial facts plus one after the old100k boundary.
  Interrupted second page retains exactly one successful step and no canonical
  writes. Failed publication rolls back writes while preserving reviewed steps;
  retry saves41 records at version1 without any further model calls. Original
  oversized-source excerpts remain <=12000 characters with exact offsets. The
  tail fact is linked to the actual original excerpt containing its marker.
  Final focused run including that exact tail-provenance assertion:
  **1 passed in11.23s**. `git diff --check` reports no whitespace errors.

## Remaining boundaries

Conversational history compaction, procedural windows/continuation, Voice windows
and recovery, cross-key semantic alias quality, provider/microphone acceptance and
other audited seams remain open. This synthetic proof establishes plumbing,
coverage and transactional behavior, not production semantic quality. The schema
does not prove model completeness or user satisfaction. Register r42 owns status;
earlier audit absence statements for factual Chat windows are superseded only.
