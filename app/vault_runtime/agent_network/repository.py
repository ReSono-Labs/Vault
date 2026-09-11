from __future__ import annotations

import json
import os
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.vault_runtime.agent_network.schema import ensure_a2a_schema
from app.vault_runtime.extensions.secrets import LocalMasterKey


@dataclass(frozen=True, slots=True)
class A2AConnection:
    connection_id: str
    user_id: str
    workspace_id: str
    display_name: str
    card_url: str
    rpc_url: str
    agent_card: dict[str, object]
    enabled: bool


class A2ARepository:
    def __init__(self, *, database_url: str, master_key: LocalMasterKey,
                 connector: Callable[..., AbstractContextManager[Any]] | None = None) -> None:
        self._database_url, self._master_key, self._connector = database_url, master_key, connector

    def _connect(self):
        if self._connector is not None:
            return self._connector(self._database_url)
        import psycopg
        return psycopg.connect(self._database_url, connect_timeout=5)

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                ensure_a2a_schema(cursor)

    def create(self, *, connection_id: str, user_id: str, workspace_id: str, display_name: str,
               card_url: str, rpc_url: str, card: dict[str, object], token: str) -> A2AConnection:
        nonce, ciphertext = self._seal(connection_id, workspace_id, token)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id, workspace_id, owner=True)
                cursor.execute("""INSERT INTO vault_private.vault_a2a_connections
                  (connection_id,user_id,workspace_id,display_name,card_url,rpc_url,agent_card,credential_nonce,credential_ciphertext)
                  VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s)""",
                  (connection_id,user_id,workspace_id,display_name,card_url,rpc_url,json.dumps(card),nonce,ciphertext))
        return self.get(user_id=user_id, workspace_id=workspace_id, connection_id=connection_id)

    def list(self, *, user_id: str, workspace_id: str) -> tuple[A2AConnection, ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id, workspace_id)
                cursor.execute("""SELECT connection_id,user_id,workspace_id,display_name,card_url,rpc_url,agent_card,enabled
                  FROM vault_private.vault_a2a_connections WHERE user_id=%s AND workspace_id=%s ORDER BY display_name""", (user_id,workspace_id))
                return tuple(_connection(row) for row in cursor.fetchall())

    def get(self, *, user_id: str, workspace_id: str, connection_id: str) -> A2AConnection:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, user_id, workspace_id)
                cursor.execute("""SELECT connection_id,user_id,workspace_id,display_name,card_url,rpc_url,agent_card,enabled
                  FROM vault_private.vault_a2a_connections WHERE connection_id=%s AND user_id=%s AND workspace_id=%s""", (connection_id,user_id,workspace_id))
                row = cursor.fetchone()
        if row is None: raise ValueError("A2A connection is unavailable.")
        return _connection(row)

    def token(self, connection: A2AConnection) -> str:
        with self._connect() as database:
            with database.cursor() as cursor:
                cursor.execute("SELECT credential_nonce,credential_ciphertext FROM vault_private.vault_a2a_connections WHERE connection_id=%s", (connection.connection_id,))
                row = cursor.fetchone()
        if row is None or row[0] is None: return ""
        aad = f"{connection.workspace_id}:{connection.connection_id}:a2a".encode()
        return AESGCM(self._master_key.load_or_create()).decrypt(bytes(row[0]),bytes(row[1]),aad).decode()

    def remove(self, *, user_id: str, workspace_id: str, connection_id: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor,user_id,workspace_id,owner=True)
                cursor.execute("DELETE FROM vault_private.vault_a2a_connections WHERE connection_id=%s AND user_id=%s AND workspace_id=%s",(connection_id,user_id,workspace_id))
                if cursor.rowcount != 1: raise ValueError("A2A connection is unavailable.")

    def context(self, *, connection_id: str, user_id: str, workspace_id: str, owner_kind: str, owner_id: str) -> str | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT context_id FROM vault_private.vault_a2a_conversations WHERE connection_id=%s AND user_id=%s AND workspace_id=%s AND owner_kind=%s AND owner_id=%s""",(connection_id,user_id,workspace_id,owner_kind,owner_id))
                row=cursor.fetchone()
        return str(row[0]) if row else None

    def save_task(self, *, record_id: str, connection: A2AConnection, owner_kind: str, owner_id: str,
                  context_id: str, remote_task_id: str, state: str, summary: str, issue: str | None) -> None:
        terminal=state in {"completed","failed","rejected","cancelled"}
        with self._connect() as database:
            with database.cursor() as cursor:
                cursor.execute("""INSERT INTO vault_private.vault_a2a_conversations(connection_id,user_id,workspace_id,owner_kind,owner_id,context_id)
                  VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(connection_id,user_id,workspace_id,owner_kind,owner_id)
                  DO UPDATE SET context_id=EXCLUDED.context_id,updated_at=now()""",(connection.connection_id,connection.user_id,connection.workspace_id,owner_kind,owner_id,context_id))
                cursor.execute("""INSERT INTO vault_private.vault_a2a_tasks(task_record_id,connection_id,user_id,workspace_id,owner_kind,owner_id,remote_task_id,context_id,state,summary,issue,completed_at)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s THEN now() END)
                  ON CONFLICT(task_record_id) DO UPDATE SET state=EXCLUDED.state,summary=EXCLUDED.summary,issue=EXCLUDED.issue,updated_at=now(),completed_at=CASE WHEN %s THEN now() ELSE vault_a2a_tasks.completed_at END""",
                  (record_id,connection.connection_id,connection.user_id,connection.workspace_id,owner_kind,owner_id,remote_task_id or None,context_id,state,summary,issue,terminal,terminal))

    def pending(self) -> tuple[dict[str, object], ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT task_record_id,connection_id,user_id,workspace_id,owner_kind,owner_id,remote_task_id,context_id,state
                  FROM vault_private.vault_a2a_tasks WHERE state IN ('working','submitted') AND remote_task_id IS NOT NULL ORDER BY updated_at LIMIT 100""")
                return tuple(dict(zip(("recordId","connectionId","userId","workspaceId","ownerKind","ownerId","remoteTaskId","contextId","state"),row)) for row in cursor.fetchall())

    def notifications(self, *, user_id: str, workspace_id: str) -> tuple[dict[str, object], ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor,user_id,workspace_id)
                cursor.execute("""SELECT t.task_record_id,c.display_name,t.state,t.summary,t.issue,t.owner_kind,t.created_at,t.updated_at,t.completed_at
                  FROM vault_private.vault_a2a_tasks t JOIN vault_private.vault_a2a_connections c USING(connection_id)
                  WHERE t.user_id=%s AND t.workspace_id=%s AND t.state='completed'
                  ORDER BY t.completed_at DESC NULLS LAST LIMIT 5""",(user_id,workspace_id))
                return tuple({"taskId":str(r[0]),"agentName":str(r[1]),"state":str(r[2]),"summary":str(r[3]),"issue":r[4],"ownerKind":str(r[5]),"createdAt":r[6].isoformat(),"updatedAt":r[7].isoformat(),"completedAt":r[8].isoformat() if r[8] else None} for r in cursor.fetchall())

    def _seal(self, connection_id: str, workspace_id: str, token: str) -> tuple[bytes|None,bytes|None]:
        if not token: return None,None
        nonce=os.urandom(12); aad=f"{workspace_id}:{connection_id}:a2a".encode()
        return nonce,AESGCM(self._master_key.load_or_create()).encrypt(nonce,token.encode(),aad)

    @staticmethod
    def _require_scope(cursor, user_id: str, workspace_id: str, owner: bool=False) -> None:
        cursor.execute("SELECT 1 FROM vault_private.local_workspace_memberships WHERE user_id=%s AND workspace_id=%s AND status='active'" + (" AND membership_type='owner'" if owner else ""),(user_id,workspace_id))
        if cursor.fetchone() is None: raise ValueError("A2A access is unavailable in the active scope.")


def _connection(row) -> A2AConnection:
    return A2AConnection(str(row[0]),str(row[1]),str(row[2]),str(row[3]),str(row[4]),str(row[5]),dict(row[6]),bool(row[7]))
