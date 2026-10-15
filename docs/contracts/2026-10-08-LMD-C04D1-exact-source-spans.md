# C04D1 — exact factual source-span prerequisite

Authority: original R31/R32 and C04D source review. Scope is a prerequisite, not
complete-session windowing acceptance. Internal same-context review below.

REUSE absolute Vault `/home/christian/Documents/Projects/ReSono-Labs-Vault/app/vault_runtime/memory/`
`chat_learning.py`, `pipeline.py`, `repository.py`, `schema.py`, existing source
fingerprints, publication transaction, authority and suppression. NEW pure
`analysis_spans.py` partition/validation only. No donor edits or new worker/store.

Decision: persist optional exact source references on canonical evidence, rather
than copying Chat into Voice transcripts or overloading evidence_kind. Reference
contains original source ID, role, SHA256 of entire original text, character
start/end and original length. Excerpt must match range length and stay <=16384.
The producer validates exact source text before passing this trusted repository
port. Repeated local indexes are mapped by explicit source refs, not ordinal alone.
Legacy callers omit metadata and retain their existing contract.

Pure planner partitions all entries into contiguous spans <=12000 characters;
packs formatted windows <=60000 characters, with globally unique citation indexes.
Empty entries are represented. No provider calls, persistence or publication from
the planner. Validate every span against the original source; missing/overlapping,
reordered, changed and fabricated ranges fail. Coverage is not semantic learning.

Mounted delta: existing bounded Chat review publishes whole-entry source refs
through the same canonical reconciliation loop. Do NOT remove current overflow
guards until resumable steps, overflow protocol and cross-window consolidation
are implemented and reviewed. No fake long-session success.

Compatibility: nullable JSONB additive upgrade, no historical backfill. Existing
Voice/Chat tests remain valid; return sourceRef only when present. The metadata
is deleted with canonical version/evidence under existing ownership. No broader
retrieval or grant. Suppression still receives unchanged four-field evidence.

Counterexamples: wrong text with a matching length, lost entry at a boundary,
source IDs crossing sessions, a reference claiming a larger excerpt, forgetting
recreated under a paraphrase. Planner rejects first three source inconsistencies;
producer/scoped source reader owns identity; repository rejects invalid shape and
length. Semantic forget suppression remains open, not solved by a reference.

Review result: CONTINUE for bounded source provenance/partition prerequisite.
Parent C04D remains NOT READY for full windows. Required proof: long/oversized
partition losslessness, tampered spans, boundary citations, mounted Chat canonical
sourceRef, existing publication behavior. No paid provider/installed DB access.
