# C08B — sealed Chat factual learning through canonical memory

Owner authority: original complete memory/Chat goal and request to finish existing
scope. REUSE absolute `/home/christian/Documents/Projects/ReSono-Labs-Vault/`:
`app/vault_runtime/memory/{voice_learning,openai_reviewer,repository,contracts}.py`,
`conversation/{runtime,repository}.py`, `composition.py`. NEW channel adapter
`memory/chat_learning.py` only. No copied Voice transcript, synthetic Voice session,
second factual reviewer/store, new agent, tools, grants or provider.

CONTINUE internal prebuild review: independent factual adapter reads finalized user
input, final assistant answers and canonical tool results for the sealed segment.
Prior segments are not republished. Explicit stable entry indexes map to original
Chat source identities; persisted evidence remains in canonical memory evidence,
with nullable transcript FK (Chat is not a Voice transcript). Model classifies via
the SAME configured factual review factory as Voice. New segment-owned checkpoint
records fingerprint/model/summary/dispositions, not a duplicate transcript/history.
Use existing reconciliation with a caller-owned transaction so accepted canonical
writes and completed checkpoint commit atomically. Scoped authority/source is
revalidated before publication; forged/missing citations fail, no silent candidate
drop. Suppression guard applies. Embeddings reuse scoped factory/store and version
checks; failure remains eligible for existing maintenance, not failed factual save.

Mount at existing ended-segment worker, independently from procedural analysis and
its feature flag. Factual failure cannot suppress procedural review or undo Chat
answers, and procedural failure cannot undo committed factual memory. Session-scoped
advisory lock prevents competing model work; completed identical segment retry skips
model/publication. No model work in a row-lock transaction. Sealed-source erasure or
session revocation during model work prevents save. No external tools during review.

Counterexamples: one fact saved twice after retry, old segment correction replayed,
fake citation accepted, cross-scope source read, provider failure suppresses decisions,
or unsent draft retained. Targeted actual mounted isolated DB checks with synthetic
provider only. Unchanged reviewer 100k/32 limits fail explicitly; complete windowing,
automatic crash recovery and semantic forget/rebuild remain C04/parent work, not
claimed delivered here. Existing short-session Voice behavior stays unchanged.

## Duplication correction — shared pipeline publication

Owner requires no duplicated work/code. Internal review observed candidate and
embedding loops duplicated in the new Chat adapter despite shared storage.
CONTINUE correction, not new scope: extract those exact existing loops into
`memory/pipeline.py` methods, with typed source-index/evidence projection supplied
by channel adapters. Voice and Chat both call them. Preserve Voice ingestion and
Chat atomic completion boundaries, suppression, version-checked vector writes and
provider failures. Validate all citations before publication (never silently skip
an invalid candidate). No new module, schema, model, store or workflow. Existing
mounted Chat and canonical Voice pipeline evidence must remain valid.
Same review found an existing Voice false-completion fallback: a stored summary
without completed ingestion could be labeled alreadyCompleted after claim denial.
Require actual completed ingestion and validate citations before claim/summary write.
This corrects the shared publication invariant; it is not full Voice crash recovery.
