from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any
from uuid import uuid4

from app.core.security.tokens import hash_token
from app.vault_runtime.external_memory.models import (
    EnrollmentResult,
    ExternalMemoryIdentity,
    ExternalMemoryIntegration,
)
from app.vault_runtime.external_memory.schema import ensure_external_memory_schema


class ExternalMemoryError(RuntimeError):
    code = "external_memory_error"


class ExternalMemoryAuthorizationError(ExternalMemoryError):
    code = "external_memory_authorization_denied"


class ExternalMemoryReplayError(ExternalMemoryError):
    code = "external_memory_request_replayed"


class ExternalMemoryRepository:
    def __init__(self, *, database_url: str, connector: Callable[..., AbstractContextManager[Any]] | None = None) -> None:
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
                ensure_external_memory_schema(cursor)

    def enroll(self, *, user_id: str, workspace_id: str, display_name: str, adapter_kind: str, grants: tuple[str, ...]) -> EnrollmentResult:
        credential = secrets.token_urlsafe(32)
        integration_id = str(uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT 1 FROM vault_private.local_workspace_memberships
                       WHERE user_id=%s AND workspace_id=%s AND status='active'""",
                    (user_id, workspace_id),
                )
                if cursor.fetchone() is None:
                    raise ExternalMemoryAuthorizationError("Active workspace membership is required.")
                cursor.execute(
                    """INSERT INTO vault_private.external_memory_integrations
                       (integration_id,workspace_id,user_id,display_name,adapter_kind,token_hash,grants_json)
                       VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
                       RETURNING status,created_at,revoked_at""",
                    (integration_id, workspace_id, user_id, display_name, adapter_kind,
                     hash_token(credential), json.dumps(grants)),
                )
                status, created_at, revoked_at = cursor.fetchone()
        return EnrollmentResult(
            ExternalMemoryIntegration(integration_id, workspace_id, user_id, display_name,
                                      adapter_kind, grants, status, created_at, revoked_at),
            credential,
        )

    def start_pairing(
        self, *, display_name: str, adapter_kind: str, grants: tuple[str, ...],
        poll_token: str, runtime_token_hash: str,
    ) -> dict[str, str]:
        if len(runtime_token_hash) != 64 or any(char not in "0123456789abcdef" for char in runtime_token_hash):
            raise ValueError("runtimeTokenHash must be a lowercase SHA-256 digest")
        pairing_id = str(uuid4())
        pairing_code = "-".join((secrets.token_hex(2), secrets.token_hex(2))).upper()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO vault_private.external_memory_pairings
                       (pairing_id,pairing_code,poll_token_hash,runtime_token_hash,
                        display_name,adapter_kind,grants_json,expires_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,now()+interval '10 minutes')""",
                    (pairing_id, pairing_code, hash_token(poll_token), runtime_token_hash,
                     display_name, adapter_kind, json.dumps(grants)),
                )
        return {"pairingId": pairing_id, "pairingCode": pairing_code, "status": "pending"}

    def pairing_status(self, *, pairing_id: str, poll_token: str) -> str:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE vault_private.external_memory_pairings
                       SET status='expired'
                       WHERE pairing_id=%s AND status='pending' AND expires_at<=now()""",
                    (pairing_id,),
                )
                cursor.execute(
                    """SELECT status FROM vault_private.external_memory_pairings
                       WHERE pairing_id=%s AND poll_token_hash=%s""",
                    (pairing_id, hash_token(poll_token)),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ExternalMemoryAuthorizationError("Pairing request is unavailable.")
                return str(row[0])

    def pairing_by_code(self, *, pairing_code: str) -> dict[str, object]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT pairing_id,display_name,adapter_kind,grants_json,status,expires_at>now()
                       FROM vault_private.external_memory_pairings WHERE pairing_code=%s""",
                    (pairing_code.upper(),),
                )
                row = cursor.fetchone()
                if row is None or row[4] != "pending" or not row[5]:
                    raise ExternalMemoryAuthorizationError("Pairing request is unavailable or expired.")
                return {"pairingId": row[0], "displayName": row[1], "adapterKind": row[2],
                        "grants": tuple(row[3]), "status": row[4]}

    def approve_pairing(
        self, *, user_id: str, workspace_id: str, pairing_id: str,
    ) -> ExternalMemoryIntegration:
        integration_id = str(uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT display_name,adapter_kind,grants_json,runtime_token_hash
                       FROM vault_private.external_memory_pairings
                       WHERE pairing_id=%s AND status='pending' AND expires_at>now() FOR UPDATE""",
                    (pairing_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ExternalMemoryAuthorizationError("Pairing request is unavailable or expired.")
                cursor.execute(
                    """INSERT INTO vault_private.external_memory_integrations
                       (integration_id,workspace_id,user_id,display_name,adapter_kind,token_hash,grants_json)
                       VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
                       RETURNING status,created_at,revoked_at""",
                    (integration_id, workspace_id, user_id, row[0], row[1], row[3], json.dumps(row[2])),
                )
                status, created_at, revoked_at = cursor.fetchone()
                cursor.execute(
                    """UPDATE vault_private.external_memory_pairings
                       SET status='approved',integration_id=%s,approved_at=now() WHERE pairing_id=%s""",
                    (integration_id, pairing_id),
                )
        return ExternalMemoryIntegration(
            integration_id, workspace_id, user_id, row[0], row[1], tuple(row[2]),
            status, created_at, revoked_at,
        )

    def list(self, *, user_id: str, workspace_id: str) -> tuple[ExternalMemoryIntegration, ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT integration_id,workspace_id,user_id,display_name,adapter_kind,
                              grants_json,status,created_at,revoked_at
                       FROM vault_private.external_memory_integrations
                       WHERE user_id=%s AND workspace_id=%s ORDER BY created_at""",
                    (user_id, workspace_id),
                )
                return tuple(self._integration(row) for row in cursor.fetchall())

    def revoke(self, *, user_id: str, workspace_id: str, integration_id: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE vault_private.external_memory_integrations
                       SET status='revoked',revoked_at=now()
                       WHERE integration_id=%s AND user_id=%s AND workspace_id=%s AND status='active'
                       RETURNING integration_id""",
                    (integration_id, user_id, workspace_id),
                )
                if cursor.fetchone() is None:
                    raise ExternalMemoryAuthorizationError("Active integration was not found in this scope.")

    def remove_revoked(self, *, user_id: str, workspace_id: str, integration_id: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """DELETE FROM vault_private.external_memory_integrations
                       WHERE integration_id=%s AND user_id=%s AND workspace_id=%s
                         AND status='revoked'
                       RETURNING integration_id""",
                    (integration_id, user_id, workspace_id),
                )
                if cursor.fetchone() is None:
                    raise ExternalMemoryAuthorizationError(
                        "Only a revoked integration in the active scope can be removed."
                    )

    def disconnect_credential(self, *, credential: str) -> str:
        if not credential:
            raise ExternalMemoryAuthorizationError("Integration credential is required.")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE vault_private.external_memory_integrations
                       SET status='revoked',revoked_at=COALESCE(revoked_at,now())
                       WHERE token_hash=%s
                       RETURNING integration_id""",
                    (hash_token(credential),),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ExternalMemoryAuthorizationError("Integration credential is invalid.")
                return str(row[0])

    def authorize(self, *, credential: str, operation: str, request_id: str) -> ExternalMemoryIdentity:
        if not credential or not request_id or len(request_id) > 128:
            raise ExternalMemoryAuthorizationError("Credential and bounded request ID are required.")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT i.integration_id,i.workspace_id,i.user_id,i.display_name,
                              i.adapter_kind,i.grants_json
                       FROM vault_private.external_memory_integrations i
                       JOIN vault_private.local_workspace_memberships m
                         ON m.workspace_id=i.workspace_id AND m.user_id=i.user_id
                       WHERE i.token_hash=%s AND i.status='active' AND m.status='active'""",
                    (hash_token(credential),),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ExternalMemoryAuthorizationError("Integration credential is invalid or revoked.")
                identity = ExternalMemoryIdentity(
                    row[0], row[1], row[2], row[3], row[4], tuple(row[5]),
                )
                if operation not in identity.grants:
                    raise ExternalMemoryAuthorizationError(f"Integration is not granted {operation}.")
                cursor.execute(
                    """INSERT INTO vault_private.external_memory_requests
                       (integration_id,request_id,operation) VALUES (%s,%s,%s)
                       ON CONFLICT DO NOTHING RETURNING request_id""",
                    (identity.integration_id, request_id, operation),
                )
                if cursor.fetchone() is None:
                    raise ExternalMemoryReplayError("Request ID has already been used.")
                return identity

    @staticmethod
    def _integration(row: tuple[Any, ...]) -> ExternalMemoryIntegration:
        return ExternalMemoryIntegration(
            row[0], row[1], row[2], row[3], row[4], tuple(row[5]), row[6], row[7], row[8]
        )
