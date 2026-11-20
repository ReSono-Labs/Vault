from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

import psycopg

from app.vault_runtime.workspace_files.constants import RESERVED_WORKSPACE_FILE_KEYS
from app.vault_runtime.workspace_files.errors import (
    WorkspaceFileBadRequestError,
    WorkspaceFileNotFoundError,
)
from app.vault_runtime.workspace_files.schema import SCHEMA_STATEMENTS
from app.vault_runtime.workspace_files.local_paths import LOCAL_FILES_ROOT
from app.vault_runtime.workspace_files.shared_paths import SHARED_FILES_ROOT
from app.vault_runtime.workspace_files.store import WorkspaceFilesystemStore
from app.vault_runtime.workspace_paths import (
    normalize_workspace_file_key,
    normalize_workspace_file_prefix,
)
from app.vault_runtime.workspace_storage import WorkspaceStorage


def workspace_file_key_hash(file_key: str) -> str:
    from hashlib import sha256

    return sha256(file_key.encode("utf-8")).hexdigest()


def is_reserved_workspace_file_key(file_key: str) -> bool:
    try:
        normalized = normalize_workspace_file_key(file_key, require_extension=False)
    except ValueError:
        return False
    if normalized == SHARED_FILES_ROOT or normalized.startswith(f"{SHARED_FILES_ROOT}/"):
        return True
    if normalized == LOCAL_FILES_ROOT or normalized.startswith(f"{LOCAL_FILES_ROOT}/"):
        return True
    return normalized in RESERVED_WORKSPACE_FILE_KEYS


def share_mount_name_for_path(*, target_path: str, share_kind: str) -> str:
    return PurePosixPath(target_path).name or target_path


@dataclass(frozen=True, slots=True)
class WorkspaceFolderShare:
    share_id: str
    workspace_id: str
    folder_path: str
    grantee_user_id: str
    permission: str
    created_by_user_id: str
    status: str
    share_kind: str = "folder"
    share_mount_name: str = ""
    grantee_display_name: str | None = None
    grantee_username: str | None = None
    owner_display_name: str | None = None
    owner_username: str | None = None


_SHARE_SELECT = """
  s.share_id, s.workspace_id, s.folder_path, s.grantee_user_id, s.permission,
  s.created_by_user_id, s.status, s.share_kind, s.share_mount_name,
  grantee.display_name, grantee.username_normalized,
  owner.display_name, owner.username_normalized
"""


def _row_to_share(row: tuple[Any, ...]) -> WorkspaceFolderShare:
    return WorkspaceFolderShare(
        share_id=str(row[0]),
        workspace_id=str(row[1]),
        folder_path=str(row[2]),
        grantee_user_id=str(row[3]),
        permission=str(row[4]),
        created_by_user_id=str(row[5]),
        status=str(row[6]),
        share_kind=str(row[7] or "folder"),
        share_mount_name=str(row[8] or PurePosixPath(str(row[2])).name),
        grantee_display_name=str(row[9]) if row[9] is not None else None,
        grantee_username=str(row[10]) if row[10] is not None else None,
        owner_display_name=str(row[11]) if row[11] is not None else None,
        owner_username=str(row[12]) if row[12] is not None else None,
    )


class WorkspaceFileRepository:
    def __init__(self, *, database_url: str) -> None:
        self._database_url = database_url

    def ensure_schema(self, *, storage: WorkspaceStorage | None = None) -> int:
        migrated = 0
        with psycopg.connect(self._database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                for statement in SCHEMA_STATEMENTS:
                    cursor.execute(statement)
                if storage is not None:
                    migrated = self._migrate_legacy_projections(cursor, storage=storage)
                cursor.execute(
                    "DROP TABLE IF EXISTS vault_private.vault_workspace_file_projections"
                )
            connection.commit()
        return migrated

    def list_shares_for_folder(
        self, *, workspace_id: str, folder_path: str, actor_user_id: str,
    ) -> list[WorkspaceFolderShare]:
        normalized = normalize_workspace_file_prefix(folder_path)
        with psycopg.connect(self._database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                self._require_owner_cursor(cursor, user_id=actor_user_id, workspace_id=workspace_id)
                cursor.execute(
                    f"""
                    SELECT {_SHARE_SELECT}
                    FROM vault_private.vault_workspace_folder_shares s
                    JOIN vault_private.local_users grantee ON grantee.user_id = s.grantee_user_id
                    JOIN vault_private.local_workspaces w ON w.workspace_id = s.workspace_id
                    JOIN vault_private.local_users owner ON owner.user_id = w.owner_user_id
                    WHERE s.workspace_id = %s AND s.folder_path_hash = %s AND s.status = 'active'
                    ORDER BY grantee.display_name, grantee.username_normalized
                    """,
                    (workspace_id, workspace_file_key_hash(normalized)),
                )
                rows = cursor.fetchall()
        return [_row_to_share(row) for row in rows]

    def list_shares_for_grantee(self, *, grantee_user_id: str) -> list[WorkspaceFolderShare]:
        with psycopg.connect(self._database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT {_SHARE_SELECT}
                    FROM vault_private.vault_workspace_folder_shares s
                    JOIN vault_private.local_users grantee ON grantee.user_id = s.grantee_user_id
                    JOIN vault_private.local_workspaces w ON w.workspace_id = s.workspace_id
                    JOIN vault_private.local_users owner ON owner.user_id = w.owner_user_id
                    WHERE s.grantee_user_id = %s AND s.status = 'active'
                    ORDER BY owner.username_normalized, s.share_mount_name
                    """,
                    (grantee_user_id,),
                )
                rows = cursor.fetchall()
        return [_row_to_share(row) for row in rows]

    def get_share(self, *, share_id: str, grantee_user_id: str | None = None) -> WorkspaceFolderShare | None:
        query = f"""
            SELECT {_SHARE_SELECT}
            FROM vault_private.vault_workspace_folder_shares s
            JOIN vault_private.local_users grantee ON grantee.user_id = s.grantee_user_id
            JOIN vault_private.local_workspaces w ON w.workspace_id = s.workspace_id
            JOIN vault_private.local_users owner ON owner.user_id = w.owner_user_id
            WHERE s.share_id = %s AND s.status = 'active'
        """
        params: list[Any] = [share_id]
        if grantee_user_id is not None:
            query += " AND s.grantee_user_id = %s"
            params.append(grantee_user_id)
        with psycopg.connect(self._database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
        if row is None:
            return None
        return _row_to_share(row)

    def upsert_share(
        self,
        *,
        workspace_id: str,
        folder_path: str,
        grantee_user_id: str,
        permission: str,
        created_by_user_id: str,
        share_kind: str,
        share_mount_name: str,
    ) -> WorkspaceFolderShare:
        if permission not in {"read", "write"}:
            raise WorkspaceFileBadRequestError("Share permission must be read or write.")
        if share_kind not in {"file", "folder"}:
            raise WorkspaceFileBadRequestError("Share kind must be file or folder.")
        normalized = normalize_workspace_file_prefix(folder_path)
        if not normalized:
            raise WorkspaceFileBadRequestError("A path is required to share.")
        mount_name = share_mount_name.strip() or share_mount_name_for_path(
            target_path=normalized,
            share_kind=share_kind,
        )
        with psycopg.connect(self._database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                self._require_owner_cursor(cursor, user_id=created_by_user_id, workspace_id=workspace_id)
                cursor.execute(
                    "SELECT 1 FROM vault_private.local_users WHERE user_id = %s AND status = 'active'",
                    (grantee_user_id,),
                )
                if cursor.fetchone() is None:
                    raise WorkspaceFileBadRequestError("That local user is unavailable.")
                share_id = str(uuid4())
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_workspace_folder_shares (
                      share_id, workspace_id, folder_path, folder_path_hash,
                      grantee_user_id, permission, created_by_user_id, status,
                      share_kind, share_mount_name
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', %s, %s)
                    ON CONFLICT (workspace_id, folder_path_hash, grantee_user_id) DO UPDATE SET
                      permission = EXCLUDED.permission,
                      share_kind = EXCLUDED.share_kind,
                      share_mount_name = EXCLUDED.share_mount_name,
                      status = 'active',
                      revoked_at = NULL
                    RETURNING share_id
                    """,
                    (
                        share_id, workspace_id, normalized, workspace_file_key_hash(normalized),
                        grantee_user_id, permission, created_by_user_id, share_kind, mount_name,
                    ),
                )
                saved_id = str(cursor.fetchone()[0])
            connection.commit()
        share = self.get_share(share_id=saved_id)
        if share is None:
            raise WorkspaceFileNotFoundError("Workspace share could not be saved.")
        return share

    def revoke_share(self, *, workspace_id: str, share_id: str, actor_user_id: str) -> None:
        with psycopg.connect(self._database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                self._require_owner_cursor(cursor, user_id=actor_user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    UPDATE vault_private.vault_workspace_folder_shares
                    SET status = 'revoked', revoked_at = now()
                    WHERE share_id = %s AND workspace_id = %s AND status = 'active'
                    """,
                    (share_id, workspace_id),
                )
            connection.commit()

    @staticmethod
    def _migrate_legacy_projections(cursor: Any, *, storage: WorkspaceStorage) -> int:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'vault_private'
              AND table_name = 'vault_workspace_file_projections'
            """
        )
        if cursor.fetchone() is None:
            return 0
        cursor.execute(
            """
            SELECT workspace_id, file_key, entry_kind, content_markdown, content_bytes
            FROM vault_private.vault_workspace_file_projections
            ORDER BY file_key ASC
            """
        )
        rows = cursor.fetchall()
        if not rows:
            return 0
        store = WorkspaceFilesystemStore(storage)
        migrated = 0
        for workspace_id, file_key, entry_kind, content_markdown, content_bytes in rows:
            store.import_legacy_projection(
                workspace_id=str(workspace_id),
                file_key=str(file_key),
                entry_kind=str(entry_kind),
                content_markdown=str(content_markdown or ""),
                content_bytes=bytes(content_bytes) if content_bytes is not None else None,
            )
            migrated += 1
        return migrated

    @staticmethod
    def _require_owner_cursor(cursor: Any, *, user_id: str, workspace_id: str) -> None:
        cursor.execute(
            """
            SELECT 1 FROM vault_private.local_workspace_memberships
            WHERE workspace_id = %s AND user_id = %s AND membership_type = 'owner'
              AND status = 'active'
            """,
            (workspace_id, user_id),
        )
        if cursor.fetchone() is None:
            from app.vault_runtime.workspace_files.errors import WorkspaceFileForbiddenError
            raise WorkspaceFileForbiddenError("Workspace owner access is required.")
