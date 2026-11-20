from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any
from uuid import uuid4

from app.vault_runtime.folders.errors import FolderNameTakenError, FolderUnavailableError
from app.vault_runtime.folders.models import FolderGrant, UserFolder
from app.vault_runtime.folders.schema import ensure_folders_schema

_GRANT_COLUMNS = "grant_id, user_id, location_id, relative_path, max_permission, created_at, include_hidden"
_FOLDER_COLUMNS = (
    "folder_id, user_id, grant_id, relative_path, name, permission, created_vault, created_at, include_hidden"
)


def _grant(row: Any) -> FolderGrant:
    return FolderGrant(
        grant_id=str(row[0]), user_id=str(row[1]), location_id=str(row[2]),
        relative_path=str(row[3]), max_permission=str(row[4]), created_at=row[5],
        include_hidden=bool(row[6]),
    )


def _folder(row: Any) -> UserFolder:
    return UserFolder(
        folder_id=str(row[0]), user_id=str(row[1]), grant_id=str(row[2]),
        relative_path=str(row[3]), name=str(row[4]), permission=str(row[5]),
        created_vault=bool(row[6]), created_at=row[7], include_hidden=bool(row[8]),
    )


class FolderRepository:
    """Grants and folders. Every query is scoped by user id."""

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
        with self._connect() as connection, connection.cursor() as cursor:
            ensure_folders_schema(cursor)

    # Grants

    def list_grants(self, *, user_id: str) -> list[FolderGrant]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_GRANT_COLUMNS} FROM vault_private.folder_grants "
                "WHERE user_id=%s ORDER BY location_id, relative_path",
                (user_id,),
            )
            return [_grant(row) for row in cursor.fetchall()]

    def get_grant(self, *, grant_id: str) -> FolderGrant | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_GRANT_COLUMNS} FROM vault_private.folder_grants WHERE grant_id=%s",
                (grant_id,),
            )
            row = cursor.fetchone()
            return _grant(row) if row else None

    def upsert_grant(
        self,
        *,
        user_id: str,
        location_id: str,
        relative_path: str,
        max_permission: str,
        created_by: str,
        include_hidden: bool | None = None,
    ) -> FolderGrant:
        """Insert or update. include_hidden=None keeps the current setting (off for new access)."""
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT 1 FROM vault_private.local_users WHERE user_id=%s AND status <> 'deleted'",
                (user_id,),
            )
            if cursor.fetchone() is None:
                raise FolderUnavailableError("That person was not found.")
            cursor.execute(
                f"""INSERT INTO vault_private.folder_grants
                    (grant_id, user_id, location_id, relative_path, max_permission, created_by, include_hidden)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (user_id, location_id, relative_path) DO UPDATE
                    SET max_permission = EXCLUDED.max_permission,
                        include_hidden = CASE WHEN %s THEN EXCLUDED.include_hidden
                                              ELSE vault_private.folder_grants.include_hidden END
                    RETURNING {_GRANT_COLUMNS}""",
                (str(uuid4()), user_id, location_id, relative_path, max_permission, created_by,
                 bool(include_hidden), include_hidden is not None),
            )
            grant = _grant(cursor.fetchone())
            if max_permission == "read":
                cursor.execute(
                    "UPDATE vault_private.user_folders SET permission='read' WHERE grant_id=%s",
                    (grant.grant_id,),
                )
            return grant

    def set_grant_permission(self, *, grant_id: str, max_permission: str) -> FolderGrant:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""UPDATE vault_private.folder_grants SET max_permission=%s
                    WHERE grant_id=%s RETURNING {_GRANT_COLUMNS}""",
                (max_permission, grant_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise FolderUnavailableError("That access was not found.")
            if max_permission == "read":
                cursor.execute(
                    "UPDATE vault_private.user_folders SET permission='read' WHERE grant_id=%s",
                    (grant_id,),
                )
            return _grant(row)

    def set_grant_hidden(self, *, grant_id: str, include_hidden: bool) -> FolderGrant:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""UPDATE vault_private.folder_grants SET include_hidden=%s
                    WHERE grant_id=%s RETURNING {_GRANT_COLUMNS}""",
                (include_hidden, grant_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise FolderUnavailableError("That access was not found.")
            return _grant(row)

    def delete_grant(self, *, grant_id: str) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM vault_private.folder_grants WHERE grant_id=%s", (grant_id,))
            if cursor.rowcount == 0:
                raise FolderUnavailableError("That access was not found.")

    def folder_counts(self, *, grant_ids: list[str]) -> dict[str, int]:
        if not grant_ids:
            return {}
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT grant_id, count(*) FROM vault_private.user_folders
                   WHERE grant_id = ANY(%s) GROUP BY grant_id""",
                (grant_ids,),
            )
            return {str(row[0]): int(row[1]) for row in cursor.fetchall()}

    # Folders

    def list_folders(self, *, user_id: str) -> list[UserFolder]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_FOLDER_COLUMNS} FROM vault_private.user_folders "
                "WHERE user_id=%s ORDER BY name_folded",
                (user_id,),
            )
            return [_folder(row) for row in cursor.fetchall()]

    def get_folder(self, *, user_id: str, folder_id: str) -> UserFolder | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_FOLDER_COLUMNS} FROM vault_private.user_folders "
                "WHERE user_id=%s AND folder_id=%s",
                (user_id, folder_id),
            )
            row = cursor.fetchone()
            return _folder(row) if row else None

    def get_folder_by_name(self, *, user_id: str, name: str) -> UserFolder | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {_FOLDER_COLUMNS} FROM vault_private.user_folders "
                "WHERE user_id=%s AND name_folded=%s",
                (user_id, name.casefold()),
            )
            row = cursor.fetchone()
            return _folder(row) if row else None

    def insert_folder(
        self,
        *,
        user_id: str,
        grant_id: str,
        relative_path: str,
        name: str,
        permission: str,
        created_vault: bool,
        include_hidden: bool = False,
    ) -> UserFolder:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""INSERT INTO vault_private.user_folders
                    (folder_id, user_id, grant_id, relative_path, name, name_folded, permission,
                     created_vault, include_hidden)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (user_id, name_folded) DO NOTHING
                    RETURNING {_FOLDER_COLUMNS}""",
                (str(uuid4()), user_id, grant_id, relative_path, name, name.casefold(), permission,
                 created_vault, include_hidden),
            )
            row = cursor.fetchone()
            if row is None:
                raise FolderNameTakenError(f"You already have a folder named '{name}'.")
            return _folder(row)

    def set_folder_permission(self, *, user_id: str, folder_id: str, permission: str) -> UserFolder:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""UPDATE vault_private.user_folders SET permission=%s
                    WHERE user_id=%s AND folder_id=%s RETURNING {_FOLDER_COLUMNS}""",
                (permission, user_id, folder_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise FolderUnavailableError("This folder is no longer available.")
            return _folder(row)

    def set_folder_hidden(self, *, user_id: str, folder_id: str, include_hidden: bool) -> UserFolder:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""UPDATE vault_private.user_folders SET include_hidden=%s
                    WHERE user_id=%s AND folder_id=%s RETURNING {_FOLDER_COLUMNS}""",
                (include_hidden, user_id, folder_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise FolderUnavailableError("This folder is no longer available.")
            return _folder(row)

    def delete_folder(self, *, user_id: str, folder_id: str) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM vault_private.user_folders WHERE user_id=%s AND folder_id=%s",
                (user_id, folder_id),
            )
            if cursor.rowcount == 0:
                raise FolderUnavailableError("This folder is no longer available.")
