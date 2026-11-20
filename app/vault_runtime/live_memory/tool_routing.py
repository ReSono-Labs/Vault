"""Live tool routing: its own on/off setting, separate from Live Memory.

Live memory search runs on the local embedding model and works with every provider. Live tool
routing calls the OpenAI Decisions API, so it is only available with an OpenAI API key. Without
one it reports "unavailable" and makes no calls.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any

from app.vault_runtime.local_identity.authority import has_current_session_scope
from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.local_identity.repository import LocalSessionError

SCHEMA = """CREATE TABLE IF NOT EXISTS vault_private.vault_live_tool_routing_preferences (
   user_id text NOT NULL,
   workspace_id text NOT NULL,
   enabled boolean NOT NULL DEFAULT true,
   updated_at timestamptz NOT NULL DEFAULT now(),
   PRIMARY KEY (user_id, workspace_id),
   FOREIGN KEY (workspace_id, user_id)
     REFERENCES vault_private.local_workspace_memberships(workspace_id, user_id)
     ON DELETE CASCADE
)"""

UNAVAILABLE_REASON = "Live tool routing uses the OpenAI Decisions API. Add an OpenAI API key in Connections to use it."
_CACHE_SECONDS = 10.0


@dataclass(frozen=True, slots=True)
class ToolRoutingStatus:
    enabled: bool
    available: bool

    @property
    def active(self) -> bool:
        return self.enabled and self.available

    def payload(self) -> dict[str, object]:
        return {"enabled": self.enabled, "available": self.available,
                "reason": None if self.available else UNAVAILABLE_REASON}


class ToolRoutingPreferences:
    def __init__(self, *, database_url: str, credentials: Any,
                 connector: Callable[..., AbstractContextManager[Any]] | None = None) -> None:
        self._database_url, self._connector, self._credentials = database_url, connector, credentials
        self._cache: dict[tuple[str, str], tuple[float, ToolRoutingStatus]] = {}
        self._lock = threading.Lock()

    def _connect(self):
        if self._connector is not None:
            return self._connector(self._database_url)
        import psycopg
        return psycopg.connect(self._database_url, connect_timeout=5)

    def ensure_schema(self) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(SCHEMA)

    def _enabled(self, user_id: str, workspace_id: str) -> bool:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT enabled FROM vault_private.vault_live_tool_routing_preferences
                              WHERE user_id=%s AND workspace_id=%s""", (user_id, workspace_id))
            row = cursor.fetchone()
            return True if row is None else bool(row[0])

    def _available(self, principal: Any) -> bool:
        try:
            return bool(self._credentials.has_api_key(principal, "openai"))
        except Exception:
            return False

    def status(self, principal: Any) -> ToolRoutingStatus:
        """Cached briefly: live preparation asks about once a second while someone types or talks."""
        key = (principal.user_id, principal.workspace_id)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None and time.monotonic() - cached[0] < _CACHE_SECONDS:
                return cached[1]
        status = ToolRoutingStatus(self._enabled(*key), self._available(principal))
        with self._lock:
            self._cache[key] = (time.monotonic(), status)
        return status

    def set(self, principal: LocalPrincipal, *, enabled: bool) -> ToolRoutingStatus:
        if type(enabled) is not bool:
            raise ValueError("enabled must be boolean.")
        with self._connect() as connection, connection.cursor() as cursor:
            if not has_current_session_scope(cursor, user_id=principal.user_id, workspace_id=principal.workspace_id,
                                             local_session_id=principal.session_id, lock=True):
                raise LocalSessionError("Active local session and workspace membership are required.")
            cursor.execute("""INSERT INTO vault_private.vault_live_tool_routing_preferences
                              (user_id, workspace_id, enabled) VALUES (%s,%s,%s)
                              ON CONFLICT (user_id, workspace_id) DO UPDATE
                              SET enabled=EXCLUDED.enabled, updated_at=now()""",
                           (principal.user_id, principal.workspace_id, enabled))
        with self._lock:
            self._cache.pop((principal.user_id, principal.workspace_id), None)
        return self.status(principal)
