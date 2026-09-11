from __future__ import annotations

import secrets
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.core.security.tokens import hash_token
from app.vault_runtime.host_filesystem.models import (
    HostFilesystemIntegration,
    HostFilesystemMount,
    HostFilesystemSettings,
)
from app.vault_runtime.host_filesystem.schema import ensure_host_filesystem_schema


class HostFilesystemError(RuntimeError):
    code = "host_filesystem_error"


class HostFilesystemAuthorizationError(HostFilesystemError):
    code = "host_filesystem_authorization_denied"


class HostFilesystemNotFoundError(HostFilesystemError):
    code = "host_filesystem_not_found"


class HostFilesystemRepository:
    def __init__(
        self,
        *,
        database_url: str,
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
                ensure_host_filesystem_schema(cursor)

    def get_settings(self, *, user_id: str, workspace_id: str) -> HostFilesystemSettings:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT enabled, helper_base_url
                       FROM vault_private.host_filesystem_settings
                       WHERE user_id=%s AND workspace_id=%s""",
                    (user_id, workspace_id),
                )
                row = cursor.fetchone()
                if row is None:
                    return HostFilesystemSettings(
                        user_id=user_id,
                        workspace_id=workspace_id,
                        enabled=False,
                        helper_base_url="http://host.docker.internal:8767",
                    )
                return HostFilesystemSettings(
                    user_id=user_id,
                    workspace_id=workspace_id,
                    enabled=bool(row[0]),
                    helper_base_url=str(row[1]),
                )

    def save_settings(
        self,
        *,
        user_id: str,
        workspace_id: str,
        enabled: bool,
        helper_base_url: str | None = None,
    ) -> HostFilesystemSettings:
        current = self.get_settings(user_id=user_id, workspace_id=workspace_id)
        base_url = helper_base_url or current.helper_base_url
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO vault_private.host_filesystem_settings
                       (user_id, workspace_id, enabled, helper_base_url)
                       VALUES (%s,%s,%s,%s)
                       ON CONFLICT (user_id, workspace_id) DO UPDATE
                       SET enabled=EXCLUDED.enabled,
                           helper_base_url=EXCLUDED.helper_base_url,
                           updated_at=now()""",
                    (user_id, workspace_id, enabled, base_url),
                )
        return HostFilesystemSettings(
            user_id=user_id,
            workspace_id=workspace_id,
            enabled=enabled,
            helper_base_url=base_url,
        )

    def start_pairing(
        self,
        *,
        display_name: str,
        adapter_kind: str,
        poll_token: str,
        runtime_token_hash: str,
        outbound_credential_enc: str | None = None,
    ) -> dict[str, str]:
        if len(runtime_token_hash) != 64 or any(char not in "0123456789abcdef" for char in runtime_token_hash):
            raise ValueError("runtimeTokenHash must be a lowercase SHA-256 digest")
        pairing_id = str(uuid4())
        pairing_code = "-".join((secrets.token_hex(2), secrets.token_hex(2))).upper()
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO vault_private.host_filesystem_pairings
                       (pairing_id,pairing_code,poll_token_hash,runtime_token_hash,
                        display_name,adapter_kind,outbound_credential_enc,expires_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,now()+interval '10 minutes')""",
                    (
                        pairing_id,
                        pairing_code,
                        hash_token(poll_token),
                        runtime_token_hash,
                        display_name,
                        adapter_kind,
                        outbound_credential_enc,
                    ),
                )
        return {"pairingId": pairing_id, "pairingCode": pairing_code, "status": "pending"}

    def pairing_status(self, *, pairing_id: str, poll_token: str) -> str:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE vault_private.host_filesystem_pairings
                       SET status='expired'
                       WHERE pairing_id=%s AND status='pending' AND expires_at<=now()""",
                    (pairing_id,),
                )
                cursor.execute(
                    """SELECT status FROM vault_private.host_filesystem_pairings
                       WHERE pairing_id=%s AND poll_token_hash=%s""",
                    (pairing_id, hash_token(poll_token)),
                )
                row = cursor.fetchone()
                if row is None:
                    raise HostFilesystemAuthorizationError("Pairing request is unavailable.")
                return str(row[0])

    def pairing_by_code(self, *, pairing_code: str) -> dict[str, object]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT pairing_id,display_name,adapter_kind,status,expires_at>now()
                       FROM vault_private.host_filesystem_pairings WHERE pairing_code=%s""",
                    (pairing_code.upper(),),
                )
                row = cursor.fetchone()
                if row is None or row[3] != "pending" or not row[4]:
                    raise HostFilesystemAuthorizationError("Pairing request is unavailable or expired.")
                return {
                    "pairingId": row[0],
                    "displayName": row[1],
                    "adapterKind": row[2],
                    "status": row[3],
                }

    def approve_pairing(
        self,
        *,
        user_id: str,
        workspace_id: str,
        pairing_id: str,
    ) -> HostFilesystemIntegration:
        integration_id = str(uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT display_name,adapter_kind,runtime_token_hash,outbound_credential_enc
                       FROM vault_private.host_filesystem_pairings
                       WHERE pairing_id=%s AND status='pending' AND expires_at>now() FOR UPDATE""",
                    (pairing_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise HostFilesystemAuthorizationError("Pairing request is unavailable or expired.")
                cursor.execute(
                    """INSERT INTO vault_private.host_filesystem_integrations
                       (integration_id,workspace_id,user_id,display_name,adapter_kind,token_hash,outbound_credential_enc)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)
                       RETURNING status,created_at,revoked_at""",
                    (integration_id, workspace_id, user_id, row[0], row[1], row[2], row[3]),
                )
                status, created_at, revoked_at = cursor.fetchone()
                cursor.execute(
                    """UPDATE vault_private.host_filesystem_pairings
                       SET status='approved',integration_id=%s,approved_at=now() WHERE pairing_id=%s""",
                    (integration_id, pairing_id),
                )
                cursor.execute(
                    """INSERT INTO vault_private.host_filesystem_settings
                       (user_id, workspace_id, enabled, helper_base_url)
                       VALUES (%s,%s,true,%s)
                       ON CONFLICT (user_id, workspace_id) DO UPDATE
                       SET enabled=true, updated_at=now()""",
                    (user_id, workspace_id, "http://host.docker.internal:8767"),
                )
        return HostFilesystemIntegration(
            integration_id=integration_id,
            workspace_id=workspace_id,
            user_id=user_id,
            display_name=str(row[0]),
            adapter_kind=str(row[1]),
            status=str(status),
            created_at=created_at,
            revoked_at=revoked_at,
        )

    def list_integrations(self, *, user_id: str, workspace_id: str) -> tuple[HostFilesystemIntegration, ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT integration_id,workspace_id,user_id,display_name,adapter_kind,
                              status,created_at,revoked_at
                       FROM vault_private.host_filesystem_integrations
                       WHERE user_id=%s AND workspace_id=%s ORDER BY created_at""",
                    (user_id, workspace_id),
                )
                return tuple(self._integration(row) for row in cursor.fetchall())

    def active_integration(self, *, user_id: str, workspace_id: str) -> HostFilesystemIntegration | None:
        for integration in self.list_integrations(user_id=user_id, workspace_id=workspace_id):
            if integration.status == "active":
                return integration
        return None

    def ensure_browser_integration(
        self,
        *,
        user_id: str,
        workspace_id: str,
    ) -> HostFilesystemIntegration:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT integration_id,workspace_id,user_id,display_name,adapter_kind,
                              status,created_at,revoked_at
                       FROM vault_private.host_filesystem_integrations
                       WHERE user_id=%s AND workspace_id=%s AND adapter_kind='browser'
                         AND status='active'
                       ORDER BY created_at DESC
                       LIMIT 1""",
                    (user_id, workspace_id),
                )
                row = cursor.fetchone()
                if row is not None:
                    return self._integration(row)
                integration_id = str(uuid4())
                cursor.execute(
                    """INSERT INTO vault_private.host_filesystem_integrations
                       (integration_id,workspace_id,user_id,display_name,adapter_kind,token_hash)
                       VALUES (%s,%s,%s,%s,'browser',%s)
                       RETURNING status,created_at,revoked_at""",
                    (
                        integration_id,
                        workspace_id,
                        user_id,
                        "This browser",
                        hash_token(secrets.token_urlsafe(32)),
                    ),
                )
                status, created_at, revoked_at = cursor.fetchone()
        return HostFilesystemIntegration(
            integration_id=integration_id,
            workspace_id=workspace_id,
            user_id=user_id,
            display_name="This browser",
            adapter_kind="browser",
            status=str(status),
            created_at=created_at,
            revoked_at=revoked_at,
        )

    def integration_by_token(self, *, credential: str) -> HostFilesystemIntegration | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT integration_id,workspace_id,user_id,display_name,adapter_kind,
                              status,created_at,revoked_at
                       FROM vault_private.host_filesystem_integrations
                       WHERE token_hash=%s AND status='active'""",
                    (hash_token(credential),),
                )
                row = cursor.fetchone()
                return self._integration(row) if row is not None else None

    def outbound_credential_enc(self, *, integration_id: str) -> str | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT outbound_credential_enc
                       FROM vault_private.host_filesystem_integrations
                       WHERE integration_id=%s""",
                    (integration_id,),
                )
                row = cursor.fetchone()
                return str(row[0]) if row and row[0] is not None else None

    def revoke_integration(self, *, user_id: str, workspace_id: str, integration_id: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE vault_private.host_filesystem_integrations
                       SET status='revoked',revoked_at=now()
                       WHERE integration_id=%s AND user_id=%s AND workspace_id=%s AND status='active'
                       RETURNING integration_id""",
                    (integration_id, user_id, workspace_id),
                )
                if cursor.fetchone() is None:
                    raise HostFilesystemAuthorizationError("Active integration was not found in this scope.")

    def remove_revoked_integration(self, *, user_id: str, workspace_id: str, integration_id: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """DELETE FROM vault_private.host_filesystem_integrations
                       WHERE integration_id=%s AND user_id=%s AND workspace_id=%s
                         AND status='revoked'
                       RETURNING integration_id""",
                    (integration_id, user_id, workspace_id),
                )
                if cursor.fetchone() is None:
                    raise HostFilesystemAuthorizationError(
                        "Only a revoked integration in the active scope can be removed."
                    )

    def list_mounts(self, *, user_id: str, workspace_id: str) -> tuple[HostFilesystemMount, ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT mount_id,integration_id,workspace_id,user_id,mount_name,
                              permission,source,status,created_at,revoked_at
                       FROM vault_private.host_filesystem_mounts
                       WHERE user_id=%s AND workspace_id=%s AND status='active'
                       ORDER BY mount_name""",
                    (user_id, workspace_id),
                )
                return tuple(self._mount(row) for row in cursor.fetchall())

    def get_mount_by_name(
        self,
        *,
        user_id: str,
        workspace_id: str,
        mount_name: str,
    ) -> HostFilesystemMount | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT mount_id,integration_id,workspace_id,user_id,mount_name,
                              permission,source,status,created_at,revoked_at
                       FROM vault_private.host_filesystem_mounts
                       WHERE user_id=%s AND workspace_id=%s AND mount_name=%s AND status='active'""",
                    (user_id, workspace_id, mount_name),
                )
                row = cursor.fetchone()
                return self._mount(row) if row is not None else None

    def get_mount_by_name_including_revoked(
        self,
        *,
        user_id: str,
        workspace_id: str,
        mount_name: str,
    ) -> HostFilesystemMount | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT mount_id,integration_id,workspace_id,user_id,mount_name,
                              permission,source,status,created_at,revoked_at
                       FROM vault_private.host_filesystem_mounts
                       WHERE user_id=%s AND workspace_id=%s AND mount_name=%s""",
                    (user_id, workspace_id, mount_name),
                )
                row = cursor.fetchone()
                return self._mount(row) if row is not None else None

    def get_mount(self, *, user_id: str, workspace_id: str, mount_id: str) -> HostFilesystemMount | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT mount_id,integration_id,workspace_id,user_id,mount_name,
                              permission,source,status,created_at,revoked_at
                       FROM vault_private.host_filesystem_mounts
                       WHERE user_id=%s AND workspace_id=%s AND mount_id=%s AND status='active'""",
                    (user_id, workspace_id, mount_id),
                )
                row = cursor.fetchone()
                return self._mount(row) if row is not None else None

    def update_mount_permission(
        self,
        *,
        user_id: str,
        workspace_id: str,
        mount_id: str,
        permission: str,
    ) -> HostFilesystemMount:
        if permission not in {"read", "write"}:
            raise ValueError("permission must be read or write.")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE vault_private.host_filesystem_mounts
                       SET permission=%s
                       WHERE mount_id=%s AND user_id=%s AND workspace_id=%s AND status='active'
                       RETURNING integration_id,mount_name,source,status,created_at,revoked_at""",
                    (permission, mount_id, user_id, workspace_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise HostFilesystemNotFoundError("Linked folder was not found.")
        return HostFilesystemMount(
            mount_id=mount_id,
            integration_id=str(row[0]),
            workspace_id=workspace_id,
            user_id=user_id,
            mount_name=str(row[1]),
            permission=permission,
            source=str(row[2]),
            status=str(row[3]),
            created_at=row[4],
            revoked_at=row[5],
        )

    def upsert_mount(
        self,
        *,
        integration_id: str,
        user_id: str,
        workspace_id: str,
        mount_id: str,
        mount_name: str,
        permission: str,
        source: str = "browser",
        status: str = "active",
        revoked_at: datetime | None = None,
    ) -> tuple[HostFilesystemMount, HostFilesystemMount | None]:
        if permission not in {"read", "write"}:
            raise ValueError("permission must be read or write.")
        if source not in {"browser", "helper"}:
            raise ValueError("source must be browser or helper.")
        if status not in {"active", "revoked"}:
            raise ValueError("status must be active or revoked.")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT mount_id,integration_id,workspace_id,user_id,mount_name,
                              permission,source,status,created_at,revoked_at
                       FROM vault_private.host_filesystem_mounts
                       WHERE user_id=%s AND workspace_id=%s AND mount_name=%s
                       FOR UPDATE""",
                    (user_id, workspace_id, mount_name),
                )
                existing = cursor.fetchone()
                if existing is not None:
                    prior = self._mount(existing)
                    cursor.execute(
                        """UPDATE vault_private.host_filesystem_mounts
                           SET mount_id=%s,integration_id=%s,permission=%s,source=%s,
                               status=%s,revoked_at=%s
                           WHERE user_id=%s AND workspace_id=%s AND mount_name=%s
                           RETURNING created_at""",
                        (
                            mount_id,
                            integration_id,
                            permission,
                            source,
                            status,
                            revoked_at,
                            user_id,
                            workspace_id,
                            mount_name,
                        ),
                    )
                    created_at = cursor.fetchone()[0]
                    mount = HostFilesystemMount(
                        mount_id=mount_id,
                        integration_id=integration_id,
                        workspace_id=workspace_id,
                        user_id=user_id,
                        mount_name=mount_name,
                        permission=permission,
                        source=source,
                        status=status,
                        created_at=created_at,
                        revoked_at=revoked_at,
                    )
                    return mount, prior
                cursor.execute(
                    """INSERT INTO vault_private.host_filesystem_mounts
                       (mount_id,integration_id,workspace_id,user_id,mount_name,permission,source,status,revoked_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       RETURNING created_at""",
                    (
                        mount_id,
                        integration_id,
                        workspace_id,
                        user_id,
                        mount_name,
                        permission,
                        source,
                        status,
                        revoked_at,
                    ),
                )
                created_at = cursor.fetchone()[0]
        mount = HostFilesystemMount(
            mount_id=mount_id,
            integration_id=integration_id,
            workspace_id=workspace_id,
            user_id=user_id,
            mount_name=mount_name,
            permission=permission,
            source=source,
            status=status,
            created_at=created_at,
            revoked_at=revoked_at,
        )
        return mount, None

    def create_mount(
        self,
        *,
        integration_id: str,
        user_id: str,
        workspace_id: str,
        mount_id: str,
        mount_name: str,
        permission: str,
        source: str = "browser",
    ) -> HostFilesystemMount:
        if permission not in {"read", "write"}:
            raise ValueError("permission must be read or write.")
        if source not in {"browser", "helper"}:
            raise ValueError("source must be browser or helper.")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO vault_private.host_filesystem_mounts
                       (mount_id,integration_id,workspace_id,user_id,mount_name,permission,source)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)
                       RETURNING status,created_at,revoked_at""",
                    (mount_id, integration_id, workspace_id, user_id, mount_name, permission, source),
                )
                status, created_at, revoked_at = cursor.fetchone()
        return HostFilesystemMount(
            mount_id=mount_id,
            integration_id=integration_id,
            workspace_id=workspace_id,
            user_id=user_id,
            mount_name=mount_name,
            permission=permission,
            source=source,
            status=str(status),
            created_at=created_at,
            revoked_at=revoked_at,
        )

    def revoke_mount(self, *, user_id: str, workspace_id: str, mount_id: str) -> HostFilesystemMount:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE vault_private.host_filesystem_mounts
                       SET status='revoked',revoked_at=now()
                       WHERE mount_id=%s AND user_id=%s AND workspace_id=%s AND status='active'
                       RETURNING integration_id,mount_name,permission,source,status,created_at,revoked_at""",
                    (mount_id, user_id, workspace_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise HostFilesystemNotFoundError("Linked folder was not found.")
        return HostFilesystemMount(
            mount_id=mount_id,
            integration_id=str(row[0]),
            workspace_id=workspace_id,
            user_id=user_id,
            mount_name=str(row[1]),
            permission=str(row[2]),
            source=str(row[3]),
            status=str(row[4]),
            created_at=row[5],
            revoked_at=row[6],
        )

    @staticmethod
    def _integration(row: tuple[Any, ...]) -> HostFilesystemIntegration:
        return HostFilesystemIntegration(
            integration_id=str(row[0]),
            workspace_id=str(row[1]),
            user_id=str(row[2]),
            display_name=str(row[3]),
            adapter_kind=str(row[4]),
            status=str(row[5]),
            created_at=row[6],
            revoked_at=row[7],
        )

    @staticmethod
    def _mount(row: tuple[Any, ...]) -> HostFilesystemMount:
        return HostFilesystemMount(
            mount_id=str(row[0]),
            integration_id=str(row[1]),
            workspace_id=str(row[2]),
            user_id=str(row[3]),
            mount_name=str(row[4]),
            permission=str(row[5]),
            source=str(row[6]),
            status=str(row[7]),
            created_at=row[8],
            revoked_at=row[9],
        )
