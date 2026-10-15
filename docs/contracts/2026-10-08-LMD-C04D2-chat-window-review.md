# C04D2 — resumable bounded factual Chat analysis

Authority: original R31/R32, C04D source review, C04D1 exact spans, C04E idle
worker and owner completion instruction. Internal same-context review. This
slice delivers factual analysis, NOT conversational-history compaction, procedural
windows or Voice recovery. No permission to treat a summary as original evidence.

REUSE absolute Vault `/home/christian/Documents/Projects/ReSono-Labs-Vault/`
`app/vault_runtime/memory/{chat_learning,analysis_spans,openai_reviewer,pipeline,contracts}.py`,
canonical evidence/source scopes and existing segment worker/advisory locks.
NEW `memory/analysis_windows.py`: bounded model-step coordinator only. Add one
necessary segment-scoped checkpoint child table in existing Chat review owner;
existing parent review row retains reviewed/completed publication. No new job,
scheduler, reviewer identity, transcript or memory store; donors unchanged.

The factual source reader pages all sealed original turns and tool evidence;
fingerprint includes the complete ordered source, not a prefix. Use C04D1 spans
and global citation IDs. Each source window <=60000 characters. Window output
extends original taxonomy with explicit hasMore; each page <=32 candidates.
Continuation supplies previously emitted stable keys within a 20000-character
budget, maximum128 pages/window. Repeated/nonadvancing/oversized continuation
fails incomplete; never publishes a prefix or silently first32.

Checkpoint each validated window page before another call, bound to entire source,
provider/model, input hash and analysis contract. Recheck scoped source/authority
and model before reading/saving outputs. Reuse valid steps on retry/restart through
the existing worker; no tool replay. Parent saves a small step-manifest marker,
not an unbounded aggregate review payload. Reviewed marker and canonical writes
remain transactional; retry reconstructs results from immutable steps.

Before publication, group candidates by exact canonical subject/domain/type/key
and consolidate duplicate/corrected groups in bounded structured calls through the
SAME reviewer runner. Preserve original citation union; output citations must be
within supplied candidates. Resolve explicit later corrections by source order;
uncertain contradictions stay conflicts. Different keys are retained, not silently
discarded. Cross-key semantic alias resolution remains semantic-quality acceptance,
not proven by coverage or grouping. Consolidation cannot invent new source or
cross subject/domain/key. One group too dense to consolidate fails explicitly.
Bounded summary consolidation is display context only, never citation evidence.

Legacy bounded reviewed/completed checkpoints preserve their exact path. New
production reviewer supports paged protocol; injected legacy test reviewers keep
old bounded behavior, never receive fake long-session support. No historical
backfill. Existing suppression runs on the canonical transaction, its known
semantic/provenance limitations stay open. Canonical evidence uses exact spans.

CONTINUE bounded implementation. Proof: real mounted >100k tail, oversized entry,
>32 facts, page resume after failure without repeating successful calls, failed
publication retry, correction across windows and invented citations. Provider/
source revocation must deny publication. Failure never marks consumer complete.
No paid calls/installed DB. Rollback retains checkpoint/source and rejects long
input instead of falling back to truncation. Full C04 parent remains partial.

Completion checkpoint: bounded factual Chat implementation and focused proof are
recorded in [C04D2 evidence](../reviews/2026-10-08-C04D2-chat-window-evidence.md).
This closes this child slice, not the remaining C04 parent or full build.

Official structured-output schema/refusal/incomplete handling consulted October8:
https://developers.openai.com/api/docs/guides/structured-outputs . Existing SDK
runner remains responsible for actual provider completion; explicit page status
is application-level coverage, not a claim that JSON schema proves semantics.
