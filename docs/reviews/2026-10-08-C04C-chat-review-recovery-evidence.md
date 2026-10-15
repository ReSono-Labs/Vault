# C04C acceptance evidence

Branch: feature/live-memory-decisions. Seven existing mounted Chat factual and
procedural checks passed (44.43s). One focused isolated-DB recovery check passed
(7.44s): ending with all worker slots occupied preserves queue intent; a held
session advisory lock rejects a competing owner; a fresh ConversationRuntime
discovers queued/running metadata and dispatches the configured factual reviewer;
publication completes once; an interrupted third attempt becomes exhausted rather
than looping forever; explicit retry requeues; revoked authority rejects claim.
All providers/embeddings synthetic. Only exact isolated test Postgres used.

Scheduling metadata lives on existing segments. Existing factual/procedural
checkpoints remain authoritative for analysis/publication; no tool replay or
historical automatic backfill. Safe logs include scoped IDs and completion state,
not raw history, credentials or exception content. Runtime close stops dispatcher.

Boundaries: Chat only. Voice recovery, full-session windows and semantic-quality
live evaluation are not established by this evidence.
