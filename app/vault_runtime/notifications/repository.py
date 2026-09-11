from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from app.vault_runtime.notifications.schema import SCHEMA_STATEMENTS


class NotificationRepository:
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

    def list_active(self, *, user_id: str, workspace_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    SELECT notification_id, kind, title, body, payload, created_at
                    FROM vault_private.vault_notifications
                    WHERE user_id = %s AND workspace_id = %s AND dismissed_at IS NULL
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (user_id, workspace_id, max(1, min(limit, 100))),
                )
                rows = cursor.fetchall()
        return [_row_to_item(row) for row in rows]

    def dismiss(self, *, user_id: str, workspace_id: str, notification_id: str) -> bool:
        now = datetime.now(UTC)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    UPDATE vault_private.vault_notifications
                    SET dismissed_at = %s
                    WHERE notification_id = %s AND user_id = %s AND workspace_id = %s AND dismissed_at IS NULL
                    """,
                    (now, notification_id, user_id, workspace_id),
                )
                updated = cursor.rowcount > 0
            connection.commit()
        return updated

    def dismiss_all(self, *, user_id: str, workspace_id: str) -> int:
        now = datetime.now(UTC)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    UPDATE vault_private.vault_notifications
                    SET dismissed_at = %s
                    WHERE user_id = %s AND workspace_id = %s AND dismissed_at IS NULL
                    """,
                    (now, user_id, workspace_id),
                )
                count = cursor.rowcount
            connection.commit()
        return count

    def create(
        self,
        *,
        user_id: str,
        workspace_id: str,
        kind: str,
        title: str,
        body: str = "",
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        notification_id = str(uuid4())
        now = datetime.now(UTC)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_notifications (
                      notification_id, user_id, workspace_id, kind, title, body, payload, created_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING notification_id, kind, title, body, payload, created_at
                    """,
                    (notification_id, user_id, workspace_id, kind, title, body, Jsonb(payload or {}), now),
                )
                row = cursor.fetchone()
            connection.commit()
        return _row_to_item(row)

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
            raise PermissionError("Notification access was not authorized for this workspace.")


def _row_to_item(row: object) -> dict[str, Any]:
    payload = row[4] if isinstance(row[4], dict) else {}
    created_at = row[5]
    return {
        "notificationId": str(row[0]),
        "kind": str(row[1]),
        "title": str(row[2]),
        "body": str(row[3]),
        "payload": payload,
        "createdAt": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
    }
