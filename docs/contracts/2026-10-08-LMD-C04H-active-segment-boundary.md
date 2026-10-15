# C04H — continuous Chat activity boundary

Requirement: a never-idle Chat must not grow one model-input segment forever.
REUSE the existing scoped `ConversationRuntimeStore.end_session` transaction,
review queue, runtime workers, original history and C04F context handoff.
Exact sources are `/home/christian/Documents/Projects/ReSono-Labs-Vault/app/vault_runtime/conversation/runtime_store.py`
and `runtime.py`. NEW glue checks completed segment size at the existing turn
cleanup boundary. No scheduler, model, schema or transcript copy is added.

Decision gate: idle-only leaves continuously active Chat unbounded; rejecting the
next request loses usability. Select automatic same-conversation segmentation
at 32 turns or 48,000 UTF-8 input plus captured-event bytes, after an entire response finishes.
CONTINUE under the owner's continuous-Chat/Voice-reuse requirement. The threshold
is an operational initial bound, not proof that arbitrary individual tool results
or a single huge turn fit procedural/model source limits. Those remain explicit.

Check size and absence of running turns under the same conversation/segment locks
as normal sealing. Do not advance history_version: segment rotation is not a new
user message. Queue both configured consumers using the existing durable intent.
Release the completed turn's worker slot before starting review. Authority loss
or a racing response must prevent rotation, never bypass authorization. Saved
originals remain intact; next turn gets only its new segment plus an available
completed prior summary and existing selected memory.

Acceptance: mounted Chat crosses the byte threshold, seals once, continues in the
same conversation without stale-version failure or replay, and excludes old full
text from the next actual model request. Internal proof only; no provider calls.
