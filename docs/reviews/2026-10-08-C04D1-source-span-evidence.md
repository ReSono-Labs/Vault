# C04D1 — exact source provenance and lossless partition prerequisite

Branch `feature/live-memory-decisions`. Existing canonical reviewer/publication,
Chat checkpoint/recovery and source IDs are reused. No duplicate session, model,
queue or memory authority. Contract/source review precedes implementation.

Actual mounted chain: ended sealed Chat → existing configured factual reviewer →
current-source revalidation → shared MemoryPipeline → canonical memory evidence
with original Chat source ID, SHA256, role and exact character offsets → existing
embedding/recall → repeated finalization without another analysis or version.
Source metadata is optional; legacy callers keep existing result shape.

Focused proof: source planner covers 270 oversized entries (>4.5 million
characters), including the final fact, with contiguous bounded spans and global
citation indexes. Missing/reordered/overlapping/tampered/fabricated ranges fail.
Empty entries and Unicode are preserved; source/header budget overflow fails.
Publication validates all cited references before its first write.

15 source-span/publication unit checks pass. One actual mounted Chat factual
save/vector/recall/retry test passes on isolated `resono_vault_test` (7.63s), and
asserts canonical persisted original-source provenance. Synthetic provider/vector;
no paid calls, installed DB, deploy, historical backfill or donor edits.

Limit: the pure planner is not yet a mounted windowed review coordinator. Existing
oversize guards deliberately remain. Resumable window outputs, explicit dense
candidate overflow/continuation, source-order cross-window consolidation and full
Voice adaptation remain C04D work. This prerequisite does NOT establish complete
session analysis or semantic forget/rebuild suppression.
