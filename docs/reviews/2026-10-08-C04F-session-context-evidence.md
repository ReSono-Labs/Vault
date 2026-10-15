# C04F — shared Voice/Chat session handoff evidence

Branch `feature/live-memory-decisions`; internal same-context review, synthetic
providers/isolated PostgreSQL only. [Contract](../contracts/2026-10-08-LMD-C04F-chat-session-context.md).

## Source finding and actual implementation

`voice/context.py::VoiceContextBuilder.build` already starts a new provider session
with scoped profile memory and a previous completed summary bounded to4096 chars.
This is session handoff, not a recurrent transcript-compaction model. Extracted
its unchanged `previous_summary_context` formatter in that SAME module; Voice and
Chat now call it. No new provider/model identity, canonical store or worker.

`ConversationRuntime._work` calls the SAME `store.history` assembler with the
actual current `segment_id`; SQL selects only that scoped segment before applying
existing payload/turn budgets. The default display-history call is unchanged.
Existing live/final memory selection remains unchanged. Chat learning loads the
latest already-completed earlier summary from the SAME conversation/workspace.
It never runs inference just to assemble context and does not block for pending
review or substitute another conversation's summary. The bound matches Voice.

Version3 context events capture actual supplied segment, original history IDs/hash,
optional completed review reference and bounded summary text. Procedural source
qualification reconstructs that segment prefix and verifies the supplied summary
against its original completed scoped review. New captures therefore do not require
an unrelated full historical prefix to qualify. Version2 keeps original prefix
verification; no retrospective metadata rewriting or fabricated original reasoning.
History/tool/source ownership, once-only execution and current grants are unchanged.

## Focused checks

- `tests/unit/test_chat_decision_source.py`: **14 passed**. Existing proposal/tool/
  reasoning attribution plus version3 segment binding, exact summary-reference
  comparison/tamper denial and shared4096-character Voice formatting.
- Existing mounted procedural/runtime tests: **6 passed in45.98s**. Actual capture,
  independent review/publication, source invalidation, tool dispatch/SSE/idempotence,
  continued segment observation identity and existing failures remain covered.
- New `tests/integration/test_chat_session_context_postgres.py`: **1 passed in15.61s**.
  Six actual submitted/captured turns in six sealed segments;>275k original input
  retained. Each model call contains its actual segment only; preceding completed
  summary is supplied without an extra model call. Final small segment qualifies
  despite the oversized unrelated historical prefix. Original rows/bytes remain;
  tampering captured prior-summary text makes qualification unknown.

No paid calls, installed history/DB, donor writes or deployment. Tests are serial
on the allowlisted `resono_vault_test` database, not an installed Vault database.

## Exact remaining boundaries

This does NOT solve large uninterrupted active segments: their existing256-turn/
262144-byte guards still fail explicitly. The display-history API retains its
existing full-history guard and still needs scoped pagination for large histories.
Procedural review within a single large segment retains its100k evidence budget;
full procedural windows remain open. Pending/failed earlier review yields no prior
summary; prompt explicitly identifies partial history and requires lookup or asking
rather than inventing context. A previous summary is lossy recalled context, never
original tool/outcome evidence or proof of satisfaction. Existing full semantic
forget/rebuild suppression limitations are not resolved by this handoff.

Do not allocate a separate summary/compaction service based on older parent rows.
Bounded-session context handoff is now implemented by reuse. Register r43 owns
status; this evidence does not claim all Chat history, Voice learning or build work
complete.
