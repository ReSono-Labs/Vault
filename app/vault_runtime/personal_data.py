"""Scoped local private-record store for the admitted Contacts and Calendar donors."""

from __future__ import annotations

import json
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.vault_runtime.types import VaultMigrationExportItem


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_personal_records (
      record_id text PRIMARY KEY,
      account_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      domain text NOT NULL CHECK (domain IN ('contacts_entries','contacts_pending_actions','calendar_event_cache','calendar_pending_actions','provider_credentials')),
      source_table text NOT NULL CHECK (source_table IN ('contacts_entries','contacts_pending_actions','calendar_event_cache','calendar_pending_actions','provider_credentials')),
      source_id text NOT NULL,
      source_payload jsonb NOT NULL,
      content_text text,
      imported_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE (account_id,workspace_id,source_table,source_id)
    )
    """,
    """CREATE INDEX IF NOT EXISTS ix_vault_personal_records_scope
       ON vault_private.vault_personal_records (account_id,workspace_id,source_table,updated_at DESC)""",
    """CREATE INDEX IF NOT EXISTS ix_vault_personal_records_text
       ON vault_private.vault_personal_records USING gin
       (to_tsvector('simple',coalesce(content_text,'') || ' ' || source_payload::text))""",
)


class PersonalDataRepository:
    def __init__(self, *, database_url: str) -> None:
        self._database_url = database_url

    def _connect(self):
        import psycopg
        return psycopg.connect(self._database_url, connect_timeout=5)

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                for statement in SCHEMA_STATEMENTS:
                    cursor.execute(statement)

    @staticmethod
    def _scope(cursor, *, account_id: str, workspace_id: str) -> None:
        cursor.execute(
            """SELECT 1 FROM vault_private.local_workspace_memberships m
               JOIN vault_private.local_users u ON u.user_id=m.user_id
               JOIN vault_private.local_workspaces w ON w.workspace_id=m.workspace_id
               WHERE m.user_id=%s AND m.workspace_id=%s AND m.status='active'
                 AND u.status='active' AND w.status='active'""",
            (account_id,workspace_id),
        )
        if cursor.fetchone() is None:
            raise PermissionError("Personal-data scope was not authorized.")

    def import_items(
        self, items: tuple[VaultMigrationExportItem, ...], *, account_id: str, workspace_id: str,
    ) -> int:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._scope(cursor, account_id=account_id, workspace_id=workspace_id)
                for item in items:
                    payload = item.payload
                    source_table = str(payload.get("sourceTable") or item.domain)
                    if source_table not in {"contacts_entries","contacts_pending_actions","calendar_event_cache","calendar_pending_actions","provider_credentials"}:
                        raise ValueError("Personal-data domain is not admitted.")
                    source_payload = payload.get("sourcePayload")
                    if not isinstance(source_payload, dict):
                        raise ValueError("Personal-data source payload is invalid.")
                    cursor.execute(
                        """INSERT INTO vault_private.vault_personal_records
                             (record_id,account_id,workspace_id,domain,source_table,source_id,source_payload,content_text)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (account_id,workspace_id,source_table,source_id) DO UPDATE SET
                             domain=EXCLUDED.domain,source_payload=EXCLUDED.source_payload,
                             content_text=EXCLUDED.content_text,updated_at=now()""",
                        (str(uuid4()),account_id,workspace_id,item.domain,source_table,item.source_id,
                         Jsonb(source_payload),payload.get("contentText")),
                    )
        return len(items)

    def get_private_record(self, *, account_id: str, workspace_id: str, source_table: str, source_id: str):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._scope(cursor, account_id=account_id, workspace_id=workspace_id)
                cursor.execute(
                    """SELECT source_id,source_payload,content_text,updated_at
                       FROM vault_private.vault_personal_records
                       WHERE account_id=%s AND workspace_id=%s AND source_table=%s AND source_id=%s""",
                    (account_id,workspace_id,source_table,source_id),
                )
                return _record(cursor.fetchone())

    def list_private_records(self, *, account_id: str, workspace_id: str, source_table: str, limit: int):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._scope(cursor, account_id=account_id, workspace_id=workspace_id)
                cursor.execute(
                    """SELECT source_id,source_payload,content_text,updated_at
                       FROM vault_private.vault_personal_records
                       WHERE account_id=%s AND workspace_id=%s AND source_table=%s
                       ORDER BY updated_at DESC,source_id LIMIT %s""",
                    (account_id,workspace_id,source_table,max(1,min(int(limit),1000))),
                )
                return [_record(row) for row in cursor.fetchall()]

    def search_private_records(
        self, *, account_id: str, workspace_id: str, source_table: str,
        query: str, limit: int, exclude_deleted: bool = False,
    ):
        needle = query.strip()
        if not needle:
            return []
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._scope(cursor, account_id=account_id, workspace_id=workspace_id)
                deleted_clause = "AND NOT (source_payload ? 'deleted_at')" if exclude_deleted else ""
                cursor.execute(
                    f"""SELECT source_id,source_payload,content_text,updated_at
                        FROM vault_private.vault_personal_records
                        WHERE account_id=%s AND workspace_id=%s AND source_table=%s
                          {deleted_clause}
                          AND (coalesce(content_text,'') ILIKE %s OR source_payload::text ILIKE %s)
                        ORDER BY updated_at DESC,source_id LIMIT %s""",
                    (account_id,workspace_id,source_table,f"%{needle}%",f"%{needle}%",max(1,min(int(limit),100))),
                )
                return [_record(row) for row in cursor.fetchall()]

    def claim_private_record_status(
        self, *, account_id: str, workspace_id: str, source_table: str, source_id: str,
        expected_status: str, claimed_status: str,
    ):
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._scope(cursor, account_id=account_id, workspace_id=workspace_id)
                cursor.execute(
                    """UPDATE vault_private.vault_personal_records SET
                         source_payload=jsonb_set(source_payload,'{status}',to_jsonb(%s::text),true),updated_at=now()
                       WHERE account_id=%s AND workspace_id=%s AND source_table=%s AND source_id=%s
                         AND source_payload->>'status'=%s
                       RETURNING source_id,source_payload,content_text,updated_at""",
                    (claimed_status,account_id,workspace_id,source_table,source_id,expected_status),
                )
                return _record(cursor.fetchone())


def _record(row):
    if row is None:
        return None
    payload = row[1] if isinstance(row[1], dict) else json.loads(row[1])
    return {"sourceId": str(row[0]), "sourcePayload": payload, "contentText": row[2], "updatedAt": row[3].isoformat()}
