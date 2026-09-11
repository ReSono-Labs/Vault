from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any
from uuid import uuid4

from app.vault_runtime.voice.models import ProviderEvent, VoiceSession
from app.vault_runtime.voice.schema import ensure_voice_schema

OPEN_VOICE_STATES = frozenset({"starting", "transport_open"})
TERMINAL_VOICE_STATES = frozenset({"closed", "failed", "lost"})


class VoiceRuntimeError(RuntimeError):
    code = "voice_runtime_error"


class VoiceAuthorizationError(VoiceRuntimeError):
    code = "voice_authorization_denied"


class VoiceSessionConflictError(VoiceRuntimeError):
    code = "voice_session_conflict"


class VoiceSessionNotFoundError(VoiceRuntimeError):
    code = "voice_session_not_found"


class VoiceSessionRepository:
    def __init__(
        self,
        *,
        database_url: str,
        connector: Callable[..., AbstractContextManager[Any]] | None = None,
    ) -> None:
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
                ensure_voice_schema(cursor)

    @staticmethod
    def _require_authority(
        cursor: Any, *, user_id: str, workspace_id: str, local_session_id: str
    ) -> None:
        cursor.execute(
            """
            SELECT 1
            FROM vault_private.local_sessions s
            JOIN vault_private.local_users u ON u.user_id=s.user_id
            JOIN vault_private.local_workspace_memberships m
              ON m.workspace_id=%s AND m.user_id=s.user_id
            JOIN vault_private.local_workspaces w ON w.workspace_id=m.workspace_id
            WHERE s.session_id=%s AND s.user_id=%s AND s.active_workspace_id=%s
              AND s.status='active' AND s.expires_at>now()
              AND u.status='active' AND m.status='active' AND w.status='active'
            """,
            (workspace_id, local_session_id, user_id, workspace_id),
        )
        if cursor.fetchone() is None:
            raise VoiceAuthorizationError("Active local session and workspace membership are required.")

    def create_session(
        self,
        *,
        user_id: str,
        workspace_id: str,
        local_session_id: str,
        provider_key: str,
        model_key: str,
        connection_mode: str,
        now: datetime | None = None,
    ) -> VoiceSession:
        if connection_mode not in {"webrtc", "websocket", "provider-websocket"}:
            raise ValueError("unsupported realtime connection mode")
        provider = provider_key.strip()
        model = model_key.strip()
        if not provider or not model or len(provider) > 120 or len(model) > 255:
            raise ValueError("provider and model keys are required and bounded")
        voice_session_id = str(uuid4())
        opened_at = now or datetime.now(UTC)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_authority(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id,
                )
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_voice_sessions
                      (voice_session_id,user_id,workspace_id,local_session_id,
                       provider_key,model_key,connection_mode,status,opened_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,'starting',%s)
                    RETURNING voice_session_id,user_id,workspace_id,local_session_id,
                              provider_key,model_key,connection_mode,status,
                              provider_session_id,opened_at,closed_at,created_at,updated_at
                    """,
                    (
                        voice_session_id, user_id, workspace_id, local_session_id,
                        provider, model, connection_mode, opened_at,
                    ),
                )
                return VoiceSession(*cursor.fetchone())

    def session(
        self,
        *,
        user_id: str,
        workspace_id: str,
        local_session_id: str,
        voice_session_id: str,
        require_open: bool = False,
    ) -> VoiceSession:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_authority(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id,
                )
                return self._session_cursor(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id, voice_session_id=voice_session_id,
                    require_open=require_open,
                )

    @staticmethod
    def _session_cursor(
        cursor: Any,
        *,
        user_id: str,
        workspace_id: str,
        local_session_id: str,
        voice_session_id: str,
        require_open: bool,
        for_update: bool = False,
    ) -> VoiceSession:
        open_clause = "AND status IN ('starting','transport_open') AND closed_at IS NULL" if require_open else ""
        lock_clause = "FOR UPDATE" if for_update else ""
        cursor.execute(
            f"""
            SELECT voice_session_id,user_id,workspace_id,local_session_id,
                   provider_key,model_key,connection_mode,status,provider_session_id,
                   opened_at,closed_at,created_at,updated_at
            FROM vault_private.vault_voice_sessions
            WHERE voice_session_id=%s AND user_id=%s AND workspace_id=%s
              AND local_session_id=%s {open_clause} {lock_clause}
            """,
            (voice_session_id, user_id, workspace_id, local_session_id),
        )
        row = cursor.fetchone()
        if row is None:
            raise VoiceSessionNotFoundError("Voice session is unavailable in the active scope.")
        return VoiceSession(*row)

    def mark_transport_open(
        self,
        *,
        user_id: str,
        workspace_id: str,
        local_session_id: str,
        voice_session_id: str,
        provider_session_id: str,
    ) -> VoiceSession:
        provider_session = provider_session_id.strip()
        if not provider_session or len(provider_session) > 255:
            raise ValueError("provider session id is required and bounded")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_authority(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id,
                )
                current = self._session_cursor(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id, voice_session_id=voice_session_id,
                    require_open=True, for_update=True,
                )
                if current.status != "starting":
                    raise VoiceSessionConflictError("Voice transport is already open.")
                cursor.execute(
                    """
                    UPDATE vault_private.vault_voice_sessions
                    SET status='transport_open',provider_session_id=%s,updated_at=now()
                    WHERE voice_session_id=%s
                    """,
                    (provider_session, voice_session_id),
                )
                return self._session_cursor(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id, voice_session_id=voice_session_id,
                    require_open=True,
                )

    def close_session(
        self,
        *,
        user_id: str,
        workspace_id: str,
        local_session_id: str,
        voice_session_id: str,
        terminal_status: str = "closed",
        now: datetime | None = None,
    ) -> VoiceSession:
        if terminal_status not in TERMINAL_VOICE_STATES:
            raise ValueError("unsupported terminal voice status")
        closed_at = now or datetime.now(UTC)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_authority(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id,
                )
                self._session_cursor(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id, voice_session_id=voice_session_id,
                    require_open=True, for_update=True,
                )
                cursor.execute(
                    """
                    UPDATE vault_private.vault_voice_sessions
                    SET status=%s,closed_at=%s,updated_at=now()
                    WHERE voice_session_id=%s
                    """,
                    (terminal_status, closed_at, voice_session_id),
                )
                return self._session_cursor(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id, voice_session_id=voice_session_id,
                    require_open=False,
                )

    def record_provider_event(
        self,
        *,
        user_id: str,
        workspace_id: str,
        local_session_id: str,
        voice_session_id: str,
        provider_event_id: str,
        event_type: str,
        event_role: str | None,
        payload: object,
        transcript_entry_index: int | None = None,
    ) -> ProviderEvent:
        event_id, event = provider_event_id.strip(), event_type.strip()
        if not event_id or not event or len(event_id) > 255 or len(event) > 255:
            raise ValueError("provider event identity is required and bounded")
        if event_role not in {None, "user", "assistant", "tool"}:
            raise ValueError("unsupported provider event role")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        payload_hash = sha256(canonical.encode("utf-8")).hexdigest()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_authority(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id,
                )
                self._session_cursor(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id, voice_session_id=voice_session_id,
                    require_open=True,
                )
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_voice_provider_events
                      (provider_event_id,voice_session_id,user_id,workspace_id,event_type,
                       event_role,payload_sha256,transcript_entry_index)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (voice_session_id,provider_event_id) DO NOTHING
                    RETURNING provider_event_id
                    """,
                    (
                        event_id, voice_session_id, user_id, workspace_id, event,
                        event_role, payload_hash, transcript_entry_index,
                    ),
                )
                accepted = cursor.fetchone() is not None
                if not accepted:
                    cursor.execute(
                        """
                        SELECT payload_sha256,event_type,event_role,transcript_entry_index
                        FROM vault_private.vault_voice_provider_events
                        WHERE voice_session_id=%s AND provider_event_id=%s
                        """,
                        (voice_session_id, event_id),
                    )
                    prior = cursor.fetchone()
                    if prior != (payload_hash, event, event_role, transcript_entry_index):
                        raise VoiceSessionConflictError("Provider event identity was replayed with different content.")
                return ProviderEvent(
                    event_id, voice_session_id, event, event_role,
                    transcript_entry_index, accepted,
                )
