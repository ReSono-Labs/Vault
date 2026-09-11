from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from app.vault_runtime.local_api.config import VaultLocalApiConfig


class PostgresVaultHealthStore:
    """Phase-bounded extraction of Voice Vault's PostgreSQL health boundary."""

    def __init__(
        self,
        *,
        database_url: str,
        connector: Callable[..., AbstractContextManager[Any]] | None = None,
    ) -> None:
        self._database_url = database_url
        self._connector = connector

    @classmethod
    def from_config(cls, config: VaultLocalApiConfig) -> "PostgresVaultHealthStore":
        return cls(database_url=config.database_url_value())

    def health(self) -> dict[str, Any]:
        connector = self._connector
        if connector is None:
            import psycopg

            connector = psycopg.connect
        with connector(self._database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                      current_database(),
                      current_user,
                      to_regnamespace('vault_private') IS NOT NULL,
                      (SELECT extversion FROM pg_extension WHERE extname = 'vector')
                    """
                )
                database_name, database_user, schema_ready, vector_version = cursor.fetchone()
        return {
            "database": "ok",
            "databaseName": database_name,
            "databaseUser": database_user,
            "schemaReady": bool(schema_ready),
            "pgvectorVersion": vector_version,
        }
