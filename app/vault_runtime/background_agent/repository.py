"""Run rows in vault_background_runs: read access for the Background routes and recovery of
old-engine rows (work_id IS NULL) at startup. The old engine that wrote those rows is gone (B4);
the durable engine writes its own rows through BackgroundJobs."""
from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.vault_runtime.background_agent.contracts import (
    TERMINAL_RUN_STATES,
    BackgroundRunRequest,
    BackgroundRunState,
)
from app.vault_runtime.background_agent.agent_brief import request_from_payload as _request
from app.vault_runtime.background_agent.run_events import append_run_event
from app.vault_runtime.background_agent.schema import ensure_background_schema
from app.vault_runtime.voice.repository import VoiceSessionRepository


# Re-exported for existing importers; new code imports from .errors.
from .errors import (  # noqa: E402,F401
    BackgroundRunAdmissionBusy,
    BackgroundRunAuthorizationError,
    BackgroundRunConflictError,
)


@dataclass(frozen=True, slots=True)
class StoredBackgroundRun:
    request: BackgroundRunRequest
    user_id: str
    workspace_id: str
    local_session_id: str
    state: BackgroundRunState
    cancellation_requested: bool
    output: dict[str, object] | None
    failure_code: str | None
    failure_message: str | None
    model_turns: int
    tool_calls: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class BackgroundRunEvent:
    run_id: str
    event_index: int
    event_type: str
    state: BackgroundRunState
    detail: dict[str, object]
    created_at: datetime


class BackgroundRunRepository:
    def __init__(
        self, *, database_url: str,
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
                ensure_background_schema(cursor)

    def get_in_workspace(
        self, *, user_id: str, workspace_id: str, local_session_id: str, run_id: str,
    ) -> StoredBackgroundRun:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                VoiceSessionRepository._require_authority(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id,
                )
                cursor.execute(
                    """
                    SELECT request_json,user_id,workspace_id,local_session_id,state,
                           cancellation_requested,output_json,failure_code,failure_message,
                           model_turns,tool_calls,created_at,updated_at,completed_at
                    FROM vault_private.vault_background_runs
                    WHERE run_id=%s AND user_id=%s AND workspace_id=%s
                    """,
                    (run_id, user_id, workspace_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise BackgroundRunAuthorizationError("Background run is unavailable in the active scope.")
                return _stored(row)

    def list_in_workspace(
        self, *, user_id: str, workspace_id: str, local_session_id: str, limit: int = 40,
    ) -> tuple[StoredBackgroundRun, ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                VoiceSessionRepository._require_authority(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id,
                )
                cursor.execute(
                    """
                    SELECT request_json,user_id,workspace_id,local_session_id,state,
                           cancellation_requested,output_json,failure_code,failure_message,
                           model_turns,tool_calls,created_at,updated_at,completed_at
                    FROM vault_private.vault_background_runs
                    WHERE user_id=%s AND workspace_id=%s AND work_id IS NULL
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (user_id, workspace_id, max(1, min(limit, 80))),
                )
                return tuple(_stored(row) for row in cursor.fetchall())

    def list_events(
        self, *, user_id: str, workspace_id: str, local_session_id: str, run_id: str,
        authorize: bool = True,
    ) -> tuple[BackgroundRunEvent, ...]:
        if authorize:
            self.get_in_workspace(
                user_id=user_id, workspace_id=workspace_id,
                local_session_id=local_session_id, run_id=run_id,
            )
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT run_id,event_index,event_type,state,detail_json,created_at
                    FROM vault_private.vault_background_run_events
                    WHERE run_id=%s AND user_id=%s AND workspace_id=%s
                    ORDER BY event_index
                    """,
                    (run_id, user_id, workspace_id),
                )
                return tuple(
                    BackgroundRunEvent(
                        run_id=str(row[0]), event_index=int(row[1]), event_type=str(row[2]),
                        state=BackgroundRunState(row[3]), detail=row[4] if isinstance(row[4], dict) else {},
                        created_at=row[5],
                    )
                    for row in cursor.fetchall()
                )

    def delete_in_workspace(
        self, *, user_id: str, workspace_id: str, local_session_id: str, run_id: str,
    ) -> bool:
        current = self.get_in_workspace(
            user_id=user_id, workspace_id=workspace_id,
            local_session_id=local_session_id, run_id=run_id,
        )
        if current.state not in TERMINAL_RUN_STATES:
            raise BackgroundRunConflictError("Only a completed, failed, or cancelled run can be deleted.")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                # Only an earlier (old-engine) run is deleted here; a work item keeps its run.
                cursor.execute(
                    """SELECT 1 FROM vault_private.vault_background_runs
                       WHERE run_id=%s AND user_id=%s AND workspace_id=%s AND work_id IS NULL FOR UPDATE""",
                    (run_id, user_id, workspace_id),
                )
                if cursor.fetchone() is None:
                    raise BackgroundRunAuthorizationError("Background run is unavailable in the active scope.")
                cursor.execute(
                    """DELETE FROM vault_private.vault_background_run_events
                       WHERE run_id=%s AND user_id=%s AND workspace_id=%s""",
                    (run_id, user_id, workspace_id),
                )
                cursor.execute(
                    """DELETE FROM vault_private.vault_background_runs
                       WHERE run_id=%s AND user_id=%s AND workspace_id=%s AND work_id IS NULL""",
                    (run_id, user_id, workspace_id),
                )
        return True

    def recover_interrupted(self) -> int:
        active = tuple(
            state.value for state in (
                BackgroundRunState.QUEUED, BackgroundRunState.RUNNING,
                BackgroundRunState.REVIEWING, BackgroundRunState.REPAIRING,
            )
        )
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT run_id,user_id,workspace_id,state
                    FROM vault_private.vault_background_runs
                    WHERE state=ANY(%s) AND work_id IS NULL FOR UPDATE
                    """,
                    (list(active),),
                )
                rows = cursor.fetchall()
                for run_id, user_id, workspace_id, prior_state in rows:
                    cursor.execute(
                        """
                        UPDATE vault_private.vault_background_runs
                        SET state='failed',failure_code='runtime_interrupted',
                            failure_message='Runtime stopped before the run completed.',
                            updated_at=now(),completed_at=now()
                        WHERE run_id=%s
                        """,
                        (run_id,),
                    )
                    append_run_event(
                        cursor, str(run_id), str(user_id), str(workspace_id),
                        "recovered_as_failed", BackgroundRunState.FAILED.value,
                        {"previousState": str(prior_state)},
                    )
                return len(rows)

def _stored(row: Any) -> StoredBackgroundRun:
    return StoredBackgroundRun(
        request=_request(row[0]), user_id=str(row[1]), workspace_id=str(row[2]),
        local_session_id=str(row[3]), state=BackgroundRunState(row[4]),
        cancellation_requested=bool(row[5]), output=row[6], failure_code=row[7],
        failure_message=row[8], model_turns=int(row[9]), tool_calls=int(row[10]),
        created_at=row[11], updated_at=row[12], completed_at=row[13],
    )
