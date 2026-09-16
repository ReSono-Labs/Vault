from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.vault_runtime.background_agent.contracts import (
    LEGAL_TRANSITIONS,
    TERMINAL_RUN_STATES,
    AutonomyProfile,
    BackgroundRunRequest,
    BackgroundRunState,
    ExecutionRecipe,
    RunLimits,
)
from app.vault_runtime.background_agent.schema import ensure_background_schema
from app.vault_runtime.voice.repository import VoiceSessionRepository


class BackgroundRunAuthorizationError(RuntimeError):
    pass


class BackgroundRunConflictError(RuntimeError):
    pass


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

    def create(
        self, *, user_id: str, workspace_id: str, local_session_id: str,
        request: BackgroundRunRequest,
    ) -> StoredBackgroundRun:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                VoiceSessionRepository._require_authority(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id,
                )
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_background_runs
                      (run_id,user_id,workspace_id,local_session_id,request_json,state)
                    VALUES (%s,%s,%s,%s,%s::jsonb,'accepted')
                    """,
                    (
                        request.run_id, user_id, workspace_id, local_session_id,
                        json.dumps(request.payload(), separators=(",", ":")),
                    ),
                )
                self._append_event(cursor, request.run_id, user_id, workspace_id, "accepted", BackgroundRunState.ACCEPTED, {})
        return self.get(
            user_id=user_id, workspace_id=workspace_id,
            local_session_id=local_session_id, run_id=request.run_id,
        )

    def get(
        self, *, user_id: str, workspace_id: str, local_session_id: str, run_id: str,
        for_update: bool = False,
    ) -> StoredBackgroundRun:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                VoiceSessionRepository._require_authority(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id,
                )
                return self._get_cursor(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id, run_id=run_id, for_update=for_update,
                )

    @staticmethod
    def _get_cursor(
        cursor: Any, *, user_id: str, workspace_id: str, local_session_id: str,
        run_id: str, for_update: bool,
    ) -> StoredBackgroundRun:
        cursor.execute(
            f"""
            SELECT request_json,user_id,workspace_id,local_session_id,state,
                   cancellation_requested,output_json,failure_code,failure_message,
                   model_turns,tool_calls,created_at,updated_at,completed_at
            FROM vault_private.vault_background_runs
            WHERE run_id=%s AND user_id=%s AND workspace_id=%s AND local_session_id=%s
            {'FOR UPDATE' if for_update else ''}
            """,
            (run_id, user_id, workspace_id, local_session_id),
        )
        row = cursor.fetchone()
        if row is None:
            raise BackgroundRunAuthorizationError("Background run is unavailable in the active scope.")
        return _stored(row)

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
                    WHERE user_id=%s AND workspace_id=%s
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

    def transition(
        self,
        *,
        user_id: str,
        workspace_id: str,
        local_session_id: str,
        run_id: str,
        target: BackgroundRunState,
        event_type: str,
        detail: dict[str, object] | None = None,
        output: dict[str, object] | None = None,
        failure_code: str | None = None,
        failure_message: str | None = None,
    ) -> StoredBackgroundRun:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                VoiceSessionRepository._require_authority(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id,
                )
                current = self._get_cursor(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id, run_id=run_id, for_update=True,
                )
                if target not in LEGAL_TRANSITIONS.get(current.state, frozenset()):
                    raise BackgroundRunConflictError(
                        f"illegal run transition: {current.state.value} -> {target.value}"
                    )
                if target is BackgroundRunState.COMPLETED and output is None:
                    raise ValueError("completed runs require output")
                if target is BackgroundRunState.FAILED and not failure_code:
                    raise ValueError("failed runs require a failure code")
                terminal = target in TERMINAL_RUN_STATES
                cursor.execute(
                    """
                    UPDATE vault_private.vault_background_runs
                    SET state=%s,output_json=%s::jsonb,failure_code=%s,failure_message=%s,
                        updated_at=now(),completed_at=CASE WHEN %s THEN now() ELSE completed_at END
                    WHERE run_id=%s AND state=%s
                    """,
                    (
                        target.value, json.dumps(output) if output is not None else None,
                        failure_code, failure_message, terminal, run_id, current.state.value,
                    ),
                )
                self._append_event(
                    cursor, run_id, user_id, workspace_id, event_type, target, detail or {}
                )
        return self.get(
            user_id=user_id, workspace_id=workspace_id,
            local_session_id=local_session_id, run_id=run_id,
        )

    def request_cancellation(
        self, *, user_id: str, workspace_id: str, local_session_id: str, run_id: str
    ) -> StoredBackgroundRun:
        current = self.get(
            user_id=user_id, workspace_id=workspace_id,
            local_session_id=local_session_id, run_id=run_id,
        )
        if current.state in TERMINAL_RUN_STATES:
            return current
        with self._connect() as connection:
            with connection.cursor() as cursor:
                VoiceSessionRepository._require_authority(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id,
                )
                cursor.execute(
                    """
                    UPDATE vault_private.vault_background_runs
                    SET cancellation_requested=true,updated_at=now()
                    WHERE run_id=%s AND user_id=%s AND workspace_id=%s
                    """,
                    (run_id, user_id, workspace_id),
                )
                self._append_event(
                    cursor, run_id, user_id, workspace_id, "cancellation_requested",
                    current.state, {},
                )
        return self.get(
            user_id=user_id, workspace_id=workspace_id,
            local_session_id=local_session_id, run_id=run_id,
        )

    def request_cancellation_in_workspace(
        self, *, user_id: str, workspace_id: str, local_session_id: str, run_id: str,
    ) -> StoredBackgroundRun:
        current = self.get_in_workspace(
            user_id=user_id, workspace_id=workspace_id,
            local_session_id=local_session_id, run_id=run_id,
        )
        if current.state in TERMINAL_RUN_STATES:
            return current
        return self.request_cancellation(
            user_id=user_id, workspace_id=workspace_id,
            local_session_id=current.local_session_id, run_id=run_id,
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
                cursor.execute(
                    """DELETE FROM vault_private.vault_background_run_events
                       WHERE run_id=%s AND user_id=%s AND workspace_id=%s""",
                    (run_id, user_id, workspace_id),
                )
                cursor.execute(
                    """DELETE FROM vault_private.vault_background_runs
                       WHERE run_id=%s AND user_id=%s AND workspace_id=%s""",
                    (run_id, user_id, workspace_id),
                )
        return True

    def record_activity(
        self, *, user_id: str, workspace_id: str, local_session_id: str,
        run_id: str, event_type: str, detail: dict[str, object],
    ) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                VoiceSessionRepository._require_authority(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id,
                )
                current = self._get_cursor(
                    cursor, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id, run_id=run_id, for_update=True,
                )
                model_increment = int(detail.get("count", 0)) if event_type == "model_turns" else 0
                tool_call = int(detail.get("call", 0)) if event_type.startswith("tool_") else 0
                cursor.execute(
                    """
                    UPDATE vault_private.vault_background_runs
                    SET model_turns=model_turns+%s,tool_calls=GREATEST(tool_calls,%s),updated_at=now()
                    WHERE run_id=%s
                    """,
                    (model_increment, tool_call, run_id),
                )
                self._append_event(
                    cursor, run_id, user_id, workspace_id, event_type, current.state, detail
                )

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
                    WHERE state=ANY(%s) FOR UPDATE
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
                    self._append_event(
                        cursor, str(run_id), str(user_id), str(workspace_id),
                        "recovered_as_failed", BackgroundRunState.FAILED,
                        {"previousState": str(prior_state)},
                    )
                return len(rows)

    @staticmethod
    def _append_event(
        cursor: Any, run_id: str, user_id: str, workspace_id: str,
        event_type: str, state: BackgroundRunState, detail: dict[str, object],
    ) -> None:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"background-event:{run_id}",)
        )
        cursor.execute(
            "SELECT COALESCE(max(event_index),-1)+1 FROM vault_private.vault_background_run_events WHERE run_id=%s",
            (run_id,),
        )
        index = int(cursor.fetchone()[0])
        cursor.execute(
            """
            INSERT INTO vault_private.vault_background_run_events
              (run_id,event_index,user_id,workspace_id,event_type,state,detail_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            (
                run_id, index, user_id, workspace_id, event_type, state.value,
                json.dumps(detail, separators=(",", ":")),
            ),
        )


def _stored(row: Any) -> StoredBackgroundRun:
    return StoredBackgroundRun(
        request=_request(row[0]), user_id=str(row[1]), workspace_id=str(row[2]),
        local_session_id=str(row[3]), state=BackgroundRunState(row[4]),
        cancellation_requested=bool(row[5]), output=row[6], failure_code=row[7],
        failure_message=row[8], model_turns=int(row[9]), tool_calls=int(row[10]),
        created_at=row[11], updated_at=row[12], completed_at=row[13],
    )


def _request(raw: object) -> BackgroundRunRequest:
    data = raw if isinstance(raw, dict) else json.loads(str(raw))
    return BackgroundRunRequest(
        run_id=str(data["run_id"]), objective=str(data["objective"]),
        instruction_profile=str(data["instruction_profile"]),
        success_criteria=tuple(data["success_criteria"]), result_schema=dict(data["result_schema"]),
        recipe=ExecutionRecipe(data["recipe"]), autonomy=AutonomyProfile(data["autonomy"]),
        limits=RunLimits(**data["limits"]), goal_type=str(data["goal_type"]),
        context_summary=str(data["context_summary"]), expected_result=str(data["expected_result"]),
        scope=str(data["scope"]), exclusions=tuple(data["exclusions"]),
        source_requirements=str(data["source_requirements"]),
        workspace_destination=data["workspace_destination"],
        original_request=str(data["original_request"]),
        verification_method=str(data["verification_method"]),
        completion_conditions=tuple(data["completion_conditions"]),
        stop_conditions=tuple(data["stop_conditions"]),
        requested_tool_names=tuple(data["requested_tool_names"]),
    )
