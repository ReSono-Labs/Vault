from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from uuid import uuid4

import psycopg

from app.vault_runtime.tasks.schema import SCHEMA_STATEMENTS


@dataclass(frozen=True, slots=True)
class TaskRecord:
    task_id: str
    task_text: str
    status: str
    created_at: str
    updated_at: str
    completed_at: str | None


class TaskRepository:
    def __init__(self, *, database_url: str) -> None:
        self._database_url = database_url

    def _connect(self):
        return psycopg.connect(self._database_url, connect_timeout=5)

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                for statement in SCHEMA_STATEMENTS:
                    cursor.execute(statement)
            connection.commit()

    def list_active(self, *, user_id: str, workspace_id: str, limit: int = 100) -> list[TaskRecord]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    SELECT task_id, task_text, status, created_at, updated_at, completed_at
                    FROM vault_private.vault_tasks
                    WHERE user_id = %s AND workspace_id = %s AND status = 'open'
                    ORDER BY created_at, task_id
                    LIMIT %s
                    """,
                    (user_id, workspace_id, max(1, min(limit, 200))),
                )
                rows = cursor.fetchall()
        return [_task_row(row) for row in rows]

    def list(self, *, user_id: str, workspace_id: str, include_completed: bool = False, limit: int = 100) -> list[TaskRecord]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=user_id, workspace_id=workspace_id)
                where = "user_id = %s AND workspace_id = %s"
                params: list[object] = [user_id, workspace_id]
                if not include_completed:
                    where += " AND status = 'open'"
                cursor.execute(
                    f"""
                    SELECT task_id, task_text, status, created_at, updated_at, completed_at
                    FROM vault_private.vault_tasks
                    WHERE {where}
                    ORDER BY created_at, task_id
                    LIMIT %s
                    """,
                    (*params, max(1, min(limit, 200))),
                )
                rows = cursor.fetchall()
        return [_task_row(row) for row in rows]

    def get(self, *, user_id: str, workspace_id: str, task_id: str) -> TaskRecord | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    SELECT task_id, task_text, status, created_at, updated_at, completed_at
                    FROM vault_private.vault_tasks
                    WHERE user_id = %s AND workspace_id = %s AND task_id = %s
                    """,
                    (user_id, workspace_id, task_id),
                )
                row = cursor.fetchone()
        return _task_row(row) if row is not None else None

    def prepare(
        self,
        *,
        user_id: str,
        workspace_id: str,
        operation: str,
        task_id: str | None,
        payload: dict[str, object],
        voice_session_id: str,
        tool_call_id: str,
        utterance_id: int,
    ) -> dict[str, object]:
        if operation not in {"add", "edit", "complete", "remove"}:
            raise ValueError("Task operation is invalid.")
        if operation != "add" and (task_id is None or self.get(user_id=user_id, workspace_id=workspace_id, task_id=task_id) is None):
            raise ValueError("Task was not found.")
        if not voice_session_id or not tool_call_id or utterance_id <= 0:
            raise ValueError("A trusted Voice invocation is required for Task changes.")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        content_hash = sha256(canonical.encode()).hexdigest()
        action_id = str(uuid4())
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=10)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_task_pending_actions (
                      action_id, user_id, workspace_id, task_id, operation, payload_json, content_hash, state,
                      voice_session_id, tool_call_id, prepared_utterance_id, expires_at, created_at, updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,'pending_review',%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        action_id, user_id, workspace_id, task_id, operation, canonical, content_hash,
                        voice_session_id, tool_call_id, utterance_id, expires_at, now, now,
                    ),
                )
            connection.commit()
        return {
            "actionId": action_id,
            "contentHash": content_hash,
            "operation": operation,
            "taskId": task_id,
            "proposed": payload,
            "expiresAt": expires_at.isoformat(),
            "confirmationRequired": True,
        }

    def claim(
        self,
        *,
        user_id: str,
        workspace_id: str,
        action_id: str,
        content_hash: str,
        voice_session_id: str,
        approval_utterance_id: int,
    ) -> dict[str, object]:
        now = datetime.now(UTC)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    SELECT task_id, operation, payload_json
                    FROM vault_private.vault_task_pending_actions
                    WHERE action_id = %s AND user_id = %s AND workspace_id = %s AND content_hash = %s
                      AND voice_session_id = %s AND state = 'pending_review' AND expires_at >= %s
                      AND prepared_utterance_id < %s
                    FOR UPDATE
                    """,
                    (action_id, user_id, workspace_id, content_hash, voice_session_id, now, approval_utterance_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ValueError("The reviewed Task change is stale, changed, expired, or already used.")
                cursor.execute(
                    """
                    UPDATE vault_private.vault_task_pending_actions
                    SET state = 'executing', updated_at = %s
                    WHERE action_id = %s
                    """,
                    (now, action_id),
                )
            connection.commit()
        return {"taskId": row[0], "operation": row[1], "payload": json.loads(row[2])}

    def execute(self, *, user_id: str, workspace_id: str, claim: dict[str, object]) -> TaskRecord | None:
        operation = str(claim["operation"])
        payload = claim["payload"]
        if not isinstance(payload, dict):
            raise ValueError("Task payload is invalid.")
        now = datetime.now(UTC)
        task_id = str(claim["taskId"] or uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=user_id, workspace_id=workspace_id)
                if operation == "add":
                    cursor.execute(
                        """
                        INSERT INTO vault_private.vault_tasks (
                          task_id, user_id, workspace_id, task_text, status, created_at, updated_at
                        ) VALUES (%s,%s,%s,%s,'open',%s,%s)
                        """,
                        (task_id, user_id, workspace_id, _task_text(payload), now, now),
                    )
                elif operation == "edit":
                    cursor.execute(
                        """
                        UPDATE vault_private.vault_tasks
                        SET task_text = %s, updated_at = %s
                        WHERE task_id = %s AND user_id = %s AND workspace_id = %s
                        """,
                        (_task_text(payload), now, task_id, user_id, workspace_id),
                    )
                elif operation == "complete":
                    cursor.execute(
                        """
                        UPDATE vault_private.vault_tasks
                        SET status = 'completed', completed_at = %s, updated_at = %s
                        WHERE task_id = %s AND user_id = %s AND workspace_id = %s
                        """,
                        (now, now, task_id, user_id, workspace_id),
                    )
                else:
                    cursor.execute(
                        """
                        DELETE FROM vault_private.vault_tasks
                        WHERE task_id = %s AND user_id = %s AND workspace_id = %s
                        """,
                        (task_id, user_id, workspace_id),
                    )
            connection.commit()
        if operation == "remove":
            return None
        item = self.get(user_id=user_id, workspace_id=workspace_id, task_id=task_id)
        if item is None:
            raise ValueError("Task was not found.")
        return item

    def finish(self, action_id: str, *, completed: bool) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE vault_private.vault_task_pending_actions
                    SET state = %s, updated_at = %s
                    WHERE action_id = %s
                    """,
                    ("completed" if completed else "failed", datetime.now(UTC), action_id),
                )
            connection.commit()

    @staticmethod
    def _require_scope(cursor, *, user_id: str, workspace_id: str) -> None:
        cursor.execute(
            """
            SELECT 1 FROM vault_private.local_workspace_memberships
            WHERE user_id = %s AND workspace_id = %s AND status = 'active'
            """,
            (user_id, workspace_id),
        )
        if cursor.fetchone() is None:
            raise PermissionError("Task access was not authorized for this workspace.")


def task_view(item: TaskRecord) -> dict[str, object]:
    return {
        "taskId": item.task_id,
        "text": item.task_text,
        "status": item.status,
        "createdAt": item.created_at,
        "updatedAt": item.updated_at,
        "completedAt": item.completed_at,
    }


def _task_row(row: object) -> TaskRecord:
    return TaskRecord(
        task_id=str(row[0]),
        task_text=str(row[1]),
        status=str(row[2]),
        created_at=row[3].isoformat() if hasattr(row[3], "isoformat") else str(row[3]),
        updated_at=row[4].isoformat() if hasattr(row[4], "isoformat") else str(row[4]),
        completed_at=row[5].isoformat() if row[5] is not None and hasattr(row[5], "isoformat") else (str(row[5]) if row[5] is not None else None),
    )


def _task_text(payload: dict[str, object]) -> str:
    value = payload.get("text")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("text is required.")
    return value.strip()
