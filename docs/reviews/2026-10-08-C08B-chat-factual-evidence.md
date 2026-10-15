# C08B — ended Chat factual-memory wiring

Branch `feature/live-memory-decisions`. Internal self-review of the bounded C08B
contract, not independent acceptance, deployment or full-build completion.
Original grounding unchanged; register r34 owns current status.

## Wiring and ownership

- `composition.py` mounts `memory/chat_learning.py` after the canonical Chat
  runtime schema, outside `decision_review_enabled`. Factual learning does not
  depend on a procedural feature flag or active decision catalog.
- Existing authenticated end-session seals a segment; the existing bounded review
  worker runs factual memory and then procedural analysis independently. Normal
  procedural snapshot capture before dispatch remains. A procedural source-read
  failure cannot block factual learning; fallback reads the same explicit segment,
  never a newer continuation. A factual failure does not suppress Decisions.
- The factual adapter reads original completed Chat inputs, canonical tool results
  (existing redaction), and captured final answers, only from the sealed segment.
  It supplies stable entry indexes and original source identities to the same
  configured `OpenAIMemoryReviewer`/Voice factual factory, not a new reviewer/model.
  No drafts, retrieved memory prompts or fake Voice transcript rows are inserted.
- A session advisory lock reuses the existing runtime lock primitive, preventing
  competing model work. No row-lock transaction remains open during model analysis.
  Current session/membership/source is revalidated in the publication transaction.
  Missing/fabricated citations reject the result instead of silently dropping it.
- `MemoryRepository.reconcile_memory` gained only an optional internal connection
  seam; normal Voice callers are unchanged. The exact same canonical reconciliation
  and suppression logic runs inside the caller-owned transaction. All accepted
  records and the completed checkpoint commit together, or all roll back.
- `vault_chat_memory_reviews` is a scoped segment-FK checkpoint, not a factual store
  or transcript copy. It retains source fingerprint, factual contract/model, summary,
  canonical memory/version dispositions and original Chat evidence IDs. Canonical
  evidence uses the existing nullable transcript FK: Chat evidence is not Voice.
- Completed identical retries skip model/publication. Scoped embedding factory and
  canonical version-checked `store_embedding` build real vectors. Embedding failure
  leaves valid facts for existing maintenance. Safe scoped completion/failure logs
  contain identifiers/status, not session text, credentials or exception payloads.

## Evidence

Targeted mounted checks use the actual production composition and authenticated
end-session, real isolated PostgreSQL and synthetic model/embedding transports.
They cover canonical fact/vector save and recall, no Voice transcript copy, retry
without model duplication, factual operation with procedural module absent,
fabricated citation rejection, rollback after canonical write/before checkpoint,
continued procedural analysis after factual failure, and session revocation during
model work preventing save. Final C08B mounted file: **4 passed**; existing mounted
Chat procedural file after this integration: **3 passed**. Focused shared memory
contract/reviewer and procedural reviewer units: **33 passed**. `git diff --check`
passes. The revocation test uses the actual `status='revoked'` contract, not merely
the audit timestamp. No security predicate was weakened to make it pass.

Existing shared reviewer checks pass (23). Existing mounted Chat procedural checks
also passed after initial factual mount (3). No installed database or paid provider
was used. No broad suite/frontend churn was needed for this backend adapter.

## Remaining boundaries

Subsequent source review corrected duplicated candidate/vector loops: BOTH Chat
and Voice now use MemoryPipeline's extracted canonical methods. C04B adds a
reviewed-output stage to THIS existing checkpoint, so completed analysis survives
publication failure without repeated model work. [Current correction/proof](2026-10-08-scope-and-duplication-reconciliation.md)
supersedes this report's earlier completed-only retry description.

This closes bounded Chat factual wiring, not full C04. Oversized sources, >100k
review context and dense >32-candidate output still fail explicitly. Complete
windowing/consolidation, durable autonomous recovery and provider/tool confirmation
parity remain open. Failed factual work can retry the same ended segment, but no
new crash-recovery scheduler is claimed. Exact suppression is reused; broader
semantic paraphrase/rebuild suppression remains open. Voice runtime is unchanged.
