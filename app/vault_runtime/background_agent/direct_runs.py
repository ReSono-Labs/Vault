"""One-shot Background Agent runs on the durable engine (owner decision 5-B, 2026-11-19).

A caller such as A2A inbound hands over one complete request. It becomes one coordinator work
item with no specialist, no destination and no planning: the durable worker runs it once with the
resumable executor, under the same admission limits as every other run. Its state and result are
read from the run row in vault_background_runs, so a task created before the old engine was
retired (work_id IS NULL) still reads the same way.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

import psycopg
from psycopg.rows import dict_row

from app.vault_runtime.background_agent.contracts import BackgroundRunRequest, BackgroundRunState
from app.vault_runtime.background_agent.coordination_contracts import OwnerScope, WorkRequest
from app.vault_runtime.background_agent.errors import BackgroundRunAuthorizationError
from app.vault_runtime.local_identity.authority import has_current_session_scope


@dataclass(frozen=True, slots=True)
class DirectRun:
    request: BackgroundRunRequest | None
    state: BackgroundRunState
    output: dict[str, object] | None
    failure_code: str | None
    failure_message: str | None


class DirectBackgroundRuns:
    SOURCE_KIND = "direct_run"

    def __init__(self, *, coordinator, database_url: str) -> None:
        self._coordinator = coordinator
        self._database_url = database_url
        self._restore_tools: Callable[[str, str], None] | None = None

    def attach_tool_restore(self, restore: Callable[[str, str], None]) -> None:
        """Make the owner's MCP tools available to the Background Agent before a run."""
        self._restore_tools = restore

    def submit(
        self, *, user_id: str, workspace_id: str, local_session_id: str, request: BackgroundRunRequest,
    ) -> DirectRun:
        if self._restore_tools is not None:
            self._restore_tools(user_id, workspace_id)
        self._coordinator.observe(OwnerScope(user_id, workspace_id), self.SOURCE_KIND, request.run_id, {
            "explicit": True,
            "work_request": WorkRequest(request=request, grant_id=None,
                                        local_session_id=local_session_id, destination={}),
        })
        return replace(self.get(user_id=user_id, workspace_id=workspace_id,
                                local_session_id=local_session_id, run_id=request.run_id), request=request)

    def get(self, *, user_id: str, workspace_id: str, local_session_id: str, run_id: str) -> DirectRun:
        with psycopg.connect(self._database_url, connect_timeout=5, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                if not has_current_session_scope(cursor, user_id=user_id, workspace_id=workspace_id,
                                                 local_session_id=local_session_id):
                    raise BackgroundRunAuthorizationError("Active local session and workspace membership are required.")
                cursor.execute(
                    """SELECT state,output_json,failure_code,failure_message
                       FROM vault_private.vault_background_runs
                       WHERE run_id=%s AND user_id=%s AND workspace_id=%s AND local_session_id=%s""",
                    (run_id, user_id, workspace_id, local_session_id),
                )
                row = cursor.fetchone()
        if row is None:
            raise BackgroundRunAuthorizationError("Background run is unavailable in the active scope.")
        return DirectRun(
            request=None, state=BackgroundRunState(row["state"]),
            output=row["output_json"] if isinstance(row["output_json"], dict) else None,
            failure_code=row["failure_code"], failure_message=row["failure_message"],
        )
