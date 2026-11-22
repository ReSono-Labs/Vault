"""0005: one new round for chat reviews that failed before the 2026-11-22 review fixes.

Decision reviews failed on dropped model streams, exact-offset excerpt checks, a fixed time budget
and a lock conflict (all fixed in this release), and Vault re-armed them after every chat turn.
Sealed segments that used their attempts get three new ones, spaced three minutes apart so the
review pool works through them gradually. Only segments whose review session is still active are
requeued; the others would be refused for authority anyway. Completed reviews are untouched.

Idempotent per release: it requeues only segments still marked failed with attempts used.
Do not edit after release; add a new migration.
"""

from __future__ import annotations

STATEMENTS = (
    """
    WITH due AS (
      SELECT s.segment_id, row_number() OVER (ORDER BY s.updated_at, s.segment_id) AS n
      FROM vault_private.vault_conversation_segments s
      JOIN vault_private.local_sessions ls ON ls.session_id = s.review_session_id
      WHERE s.state = 'sealed' AND s.review_state = 'failed' AND s.review_attempts >= 3
        AND ls.status = 'active' AND ls.expires_at > now()
    )
    UPDATE vault_private.vault_conversation_segments s
    SET review_state = 'queued', review_attempts = 0,
        review_due_at = now() + due.n * interval '3 minutes'
    FROM due WHERE s.segment_id = due.segment_id
    """,
)


def apply(cursor) -> None:
    cursor.execute("SELECT to_regclass('vault_private.vault_conversation_segments')")
    if cursor.fetchone()[0] is None:
        return
    for statement in STATEMENTS:
        cursor.execute(statement)
