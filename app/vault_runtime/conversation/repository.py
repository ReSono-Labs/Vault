from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any
from uuid import uuid4

from app.vault_runtime.conversation.contracts import (
    AuthorizationError, ConflictError, Conversation, ConversationSegment,
    NotFoundError, SubmittedTurn, history_version, identifier, text_fingerprint,
)
from app.vault_runtime.conversation.schema import ensure_conversation_schema
from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.local_identity.authority import has_current_session_scope
from app.vault_runtime.decision_routing.contracts import InputIdentity, ScopedPrincipalRef

_HEADER_COLUMNS = """conversation_id,user_id,workspace_id,create_key,history_version,
    next_turn_ordinal,state,title,created_at,updated_at"""
_SEGMENT_COLUMNS = """segment_id,conversation_id,user_id,workspace_id,ordinal,state,
    created_at,updated_at"""
_TURN_COLUMNS = """turn_id,conversation_id,segment_id,user_id,workspace_id,ordinal,
    submission_key,input_text,input_fingerprint,submitted_history_version,state,
    created_at,updated_at"""


class ConversationRepository:
    """Scoped final-input persistence, independent of execution and learning."""

    def __init__(self, *, database_url: str,
                 connector: Callable[..., AbstractContextManager[Any]] | None = None) -> None:
        self._database_url = database_url
        self._connector = connector

    def _connect(self):
        if self._connector is not None:
            return self._connector(self._database_url)
        import psycopg

        return psycopg.connect(self._database_url, connect_timeout=5)

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                ensure_conversation_schema(cursor)

    @staticmethod
    def _require_authority(cursor: Any, principal: LocalPrincipal) -> None:
        # Neutral local-authority predicate reused from VoiceSessionRepository;
        # shared locks are required here to hold authority through the write commit.
        if not has_current_session_scope(
            cursor, user_id=principal.user_id, workspace_id=principal.workspace_id,
            local_session_id=principal.session_id, lock=True,
        ):
            raise AuthorizationError("Active local session and workspace membership are required.")

    @staticmethod
    def _scope(principal: LocalPrincipal, conversation_id: str) -> tuple[str, str, str]:
        return principal.user_id, principal.workspace_id, conversation_id

    @staticmethod
    def context_identity_in_transaction(cursor: Any, scope: ScopedPrincipalRef,
                                        identity: InputIdentity) -> int:
        """Canonical pre-submit history identity; caller holds current authority."""
        cursor.execute(
            """SELECT c.history_version, t.submitted_history_version,
                      t.input_fingerprint, t.state
               FROM vault_private.vault_conversations c
               JOIN vault_private.vault_conversation_segments s
                 ON s.user_id=c.user_id AND s.workspace_id=c.workspace_id
                 AND s.conversation_id=c.conversation_id AND s.segment_id=%s
               LEFT JOIN vault_private.vault_conversation_turns t
                 ON t.user_id=c.user_id AND t.workspace_id=c.workspace_id
                 AND t.conversation_id=c.conversation_id AND t.segment_id=s.segment_id
                 AND t.turn_id=%s
               WHERE c.user_id=%s AND c.workspace_id=%s AND c.conversation_id=%s
                 AND c.state='open' AND s.state='open'""",
            (identity.segment_id, identity.turn_id, scope.user_id, scope.workspace_id,
             identity.conversation_id),
        )
        row = cursor.fetchone()
        if row is None:
            raise NotFoundError("Current conversation segment is unavailable.")
        if identity.turn_id is None:
            return row[0]
        if (row[1] is None or row[0] != row[1] + 1
                or row[2] != identity.input_fingerprint or row[3] not in {"submitted", "running"}):
            raise ConflictError("Final input is not the current submitted turn.")
        return row[1]

    def _header(self, cursor: Any, principal: LocalPrincipal, conversation_id: str,
                *, lock: bool = False):
        cursor.execute(
            f"""SELECT {_HEADER_COLUMNS} FROM vault_private.vault_conversations
                WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s"""
            + (" FOR UPDATE" if lock else ""),
            self._scope(principal, conversation_id),
        )
        row = cursor.fetchone()
        if row is None:
            raise NotFoundError("Conversation is unavailable.")
        return row

    def _conversation(self, cursor: Any, principal: LocalPrincipal, row) -> Conversation:
        cursor.execute(
            f"""SELECT {_SEGMENT_COLUMNS} FROM vault_private.vault_conversation_segments
                WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s ORDER BY ordinal""",
            self._scope(principal, row[0]),
        )
        return Conversation(*row, segments=tuple(ConversationSegment(*segment) for segment in cursor.fetchall()))

    @staticmethod
    def _submitted(row, *, duplicate: bool = False) -> SubmittedTurn:
        return SubmittedTurn(*row, duplicate=duplicate, history_version=row[9] + 1)

    def create(self, principal: LocalPrincipal, create_key: str) -> Conversation:
        key = identifier(create_key)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_authority(cursor, principal)
                cursor.execute(
                    """INSERT INTO vault_private.vault_conversations
                       (conversation_id,user_id,workspace_id,create_key) VALUES (%s,%s,%s,%s)
                       ON CONFLICT (user_id,workspace_id,create_key) DO NOTHING""",
                    (str(uuid4()), principal.user_id, principal.workspace_id, key),
                )
                cursor.execute(
                    f"""SELECT {_HEADER_COLUMNS} FROM vault_private.vault_conversations
                        WHERE user_id=%s AND workspace_id=%s AND create_key=%s FOR UPDATE""",
                    (principal.user_id, principal.workspace_id, key),
                )
                row = cursor.fetchone()
                cursor.execute(
                    """INSERT INTO vault_private.vault_conversation_segments
                       (segment_id,conversation_id,user_id,workspace_id,ordinal)
                       VALUES (%s,%s,%s,%s,0)
                       ON CONFLICT (user_id,workspace_id,conversation_id,ordinal) DO NOTHING""",
                    (str(uuid4()), row[0], principal.user_id, principal.workspace_id),
                )
                result = self._conversation(cursor, principal, row)
        return result

    def load(self, principal: LocalPrincipal, conversation_id: str) -> Conversation:
        conversation_id = identifier(conversation_id)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_authority(cursor, principal)
                result = self._conversation(cursor, principal, self._header(cursor, principal, conversation_id))
        return result

    def submit_text(self, principal: LocalPrincipal, conversation_id: str,
                    submission_key: str, input_text: str,
                    expected_history_version: int, *, require_idle: bool = False, bind_source=None) -> SubmittedTurn:
        conversation_id = identifier(conversation_id)
        key = identifier(submission_key)
        fingerprint = text_fingerprint(input_text)
        expected = history_version(expected_history_version)
        scope = self._scope(principal, conversation_id)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_authority(cursor, principal)
                header = self._header(cursor, principal, conversation_id, lock=True)
                cursor.execute(
                    f"""SELECT {_TURN_COLUMNS} FROM vault_private.vault_conversation_turns
                        WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND submission_key=%s""",
                    (*scope, key),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    if existing[7] != input_text or existing[8] != fingerprint:
                        raise ConflictError("Submission key already belongs to different text.")
                    result = self._submitted(existing, duplicate=True)
                else:
                    if header[6] != "open" or header[4] != expected:
                        raise ConflictError("Conversation is closed or history version changed.")
                    if require_idle:
                        cursor.execute("""SELECT 1 FROM vault_private.vault_conversation_turns
                          WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s
                          AND state IN ('submitted','running') LIMIT 1""",scope)
                        if cursor.fetchone() is not None:
                            raise ConflictError("Conversation already has an active turn.")
                    cursor.execute(
                        """SELECT segment_id FROM vault_private.vault_conversation_segments
                           WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND state='open'
                           FOR UPDATE""", scope,
                    )
                    segment = cursor.fetchone()
                    if segment is None:
                        raise ConflictError("Conversation has no open segment.")
                    cursor.execute(
                        f"""INSERT INTO vault_private.vault_conversation_turns
                            (turn_id,conversation_id,segment_id,user_id,workspace_id,ordinal,
                             submission_key,input_text,input_fingerprint,submitted_history_version)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING {_TURN_COLUMNS}""",
                        (str(uuid4()), conversation_id, segment[0], principal.user_id,
                         principal.workspace_id, header[5], key, input_text, fingerprint, header[4]),
                    )
                    result = self._submitted(cursor.fetchone())
                    cursor.execute(
                        """UPDATE vault_private.vault_conversations SET history_version=history_version+1,
                           next_turn_ordinal=next_turn_ordinal+1,updated_at=now()
                           WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s""", scope,
                    )
                if bind_source is not None:
                    bind_source(cursor,result)
        return result

    def turn(self, principal: LocalPrincipal, conversation_id: str, turn_id: str) -> SubmittedTurn:
        conversation_id, turn_id = identifier(conversation_id), identifier(turn_id)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_authority(cursor, principal)
                cursor.execute(
                    f"""SELECT {_TURN_COLUMNS} FROM vault_private.vault_conversation_turns
                        WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND turn_id=%s""",
                    (*self._scope(principal, conversation_id), turn_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise NotFoundError("Submitted turn is unavailable.")
                result = self._submitted(row)
        return result
