from dataclasses import dataclass
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from app.vault_runtime.local_identity.authority import has_current_session_scope
from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.local_identity.repository import LocalSessionError
from app.vault_runtime.live_memory.preference_schema import ensure_preference_schema


class PreferenceConflictError(RuntimeError):
    code = "live_memory_preference_conflict"


@dataclass(frozen=True, slots=True)
class LiveMemoryPreference:
    user_id: str
    workspace_id: str
    enabled: bool
    epoch: int


class LiveMemoryPreferenceRepository:
    """Removable scoped setting; normal final retrieval/review never reads it."""

    def __init__(self, *, database_url: str,
                 connector: Callable[..., AbstractContextManager[Any]] | None = None):
        self._database_url, self._connector = database_url, connector

    def _connect(self):
        if self._connector is not None:
            return self._connector(self._database_url)
        import psycopg
        return psycopg.connect(self._database_url, connect_timeout=5)

    def ensure_schema(self):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                ensure_preference_schema(cursor)

    @staticmethod
    def _require_authority(cursor, principal: LocalPrincipal):
        if not has_current_session_scope(cursor, user_id=principal.user_id,
                workspace_id=principal.workspace_id, local_session_id=principal.session_id,
                lock=True):
            raise LocalSessionError("Active local session and workspace membership are required.")

    def get(self, principal: LocalPrincipal) -> LiveMemoryPreference:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_authority(cursor, principal)
                return self._get_cursor(cursor, user_id=principal.user_id,
                                        workspace_id=principal.workspace_id)

    @staticmethod
    def _get_cursor(cursor, *, user_id: str, workspace_id: str) -> LiveMemoryPreference:
        """Internal read; caller owns transaction and current scope authority."""
        cursor.execute("""SELECT enabled,epoch FROM vault_private.vault_live_memory_preferences
                    WHERE user_id=%s AND workspace_id=%s""",
                    (user_id, workspace_id))
        row = cursor.fetchone()
        return LiveMemoryPreference(user_id, workspace_id,
                                    *(row if row is not None else (True, 0)))

    def set(self, principal: LocalPrincipal, *, enabled: bool,
            expected_epoch: int) -> LiveMemoryPreference:
        if type(enabled) is not bool or type(expected_epoch) is not int or expected_epoch < 0:
            raise ValueError("Expected boolean enabled and nonnegative integer expectedEpoch.")
        scope = (principal.user_id, principal.workspace_id)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_authority(cursor, principal)
                if expected_epoch == 0:
                    cursor.execute("""INSERT INTO vault_private.vault_live_memory_preferences
                        (user_id,workspace_id,enabled) VALUES (%s,%s,%s)
                        ON CONFLICT(user_id,workspace_id) DO NOTHING RETURNING enabled,epoch""",
                        (*scope, enabled))
                    row = cursor.fetchone()
                    if row is None:
                        raise PreferenceConflictError("Preference changed; reload before updating.")
                else:
                    cursor.execute("""SELECT enabled,epoch FROM vault_private.vault_live_memory_preferences
                        WHERE user_id=%s AND workspace_id=%s FOR UPDATE""", scope)
                    row = cursor.fetchone()
                    if row is None or row[1] != expected_epoch:
                        raise PreferenceConflictError("Preference changed; reload before updating.")
                    if row[0] != enabled:
                        cursor.execute("""UPDATE vault_private.vault_live_memory_preferences
                            SET enabled=%s,epoch=epoch+1 WHERE user_id=%s AND workspace_id=%s
                            RETURNING enabled,epoch""", (enabled, *scope))
                        row = cursor.fetchone()
        return LiveMemoryPreference(*scope, *row)
