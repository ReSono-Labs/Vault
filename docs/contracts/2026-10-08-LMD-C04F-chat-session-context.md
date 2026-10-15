# C04F — reuse Voice session handoff for Chat context

Owner clarification: reuse existing Voice session logic; do not introduce a
separate long-history compaction service. Original R01/R31/R35 and current owner
continuation govern. Internal same-context source/reuse review.

Observed source: `/home/christian/Documents/Projects/ReSono-Labs-Vault/app/vault_runtime/voice/context.py`
`VoiceContextBuilder.build` loads scoped memory and a previous completed session
summary, supplies at most4096 summary characters, and starts a fresh provider
session. It does not resend all past transcripts. `memory/chat_learning.py`
already produces/stores a summary on completed factual review. Chat runtime
currently calls `conversation/runtime_store.py::history` across all segments.
Idle review boundaries alone therefore do not bound the next model's history.

Decision CONTINUE: reuse Voice's bounded summary-context formatting (extract
unchanged helper in existing context owner); Chat supplies original turns from
its active segment and the latest already-completed earlier Chat summary in the
same conversation, plus its existing scoped live/final memory selection. No
new summary inference, compaction model, canonical summary store, worker, fake
Voice identity or deletion. Missing/pending prior review means no summary, not
a blocking model call or invented completion. Do not substitute another Chat's
summary. Selected provider/tools/grants remain current.

NEW minimal channel adaptation only in existing absolute Vault sources above,
`conversation/runtime.py`, `decision_learning/chat_source.py`; preserve the
single canonical `history_projection.assemble_history` and fingerprint helper.
Retained display history and full-source factual analysis remain unchanged.
Existing active-segment safety budgets remain explicit, not silently truncated.
This slice does not solve arbitrarily large uninterrupted active segments or
paginated history UI; do not claim otherwise.

Capture version3 records actual segment ID, exact supplied history IDs/hash,
and optional original completed review reference/bounded text. Version2 remains
validated by its original whole-prefix logic; never rewrite legacy events.
Procedural qualification must reconstruct the exact supplied segment prefix,
validate the referenced prior summary against its original completed scoped
review, and remain unknown on missing/tampered context. Summary is untrusted
context, not a replacement for original tool/outcome evidence. Prior-summary
use must not be mistaken for new user instructions or a success signal.

Counterexamples: idle boundary loses saved transcript; summary from another
user/conversation; old completed context represented as current-segment evidence;
reviewer qualifies a fabricated history/summary; read triggers model/tool work;
new large-prefix conversation fails despite small active segment. Prove bounded
actual mounted continuation, unchanged originals, source reference tamper denial,
and existing publication/retry regressions. Isolated DB/synthetic provider only.

Alternative rejected: new recurrent summarization/compaction model or copied Voice
transcripts. Alternative retained: current unbounded-prefix behavior for legacy
capture verification only. Outcome is bounded session handoff, not full older
conversation recall; existing memory lookup remains the canonical recall path.
Rollback disables segment context mode; original rows/checkpoints remain intact.

Completion: bounded implementation and focused internal proof are recorded in
[C04F evidence](../reviews/2026-10-08-C04F-session-context-evidence.md). No full
build completion or production semantic-quality claim follows from this slice.
