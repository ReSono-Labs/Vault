"""Numbered schema migrations, applied once each under a PostgreSQL advisory lock.

A migration is a module ``NNNN_name.py`` in this package with a function ``apply(cursor)``.
The runner records the version, the name and the SHA-256 of the module source (and of its
``NNNN_name.sql`` statements, if any) in
``vault_private.schema_migrations``. Applied migrations never change: a changed checksum,
or an applied version this code does not know, stops startup.
"""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parent
# Fixed key for pg_advisory_lock; one Vault runner at a time per database.
LOCK_KEY = 0x5245534F4E4F  # "RESONO"
_FILE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.py$")
_LOG = logging.getLogger(__name__)
_CONTEXT: ContextVar[dict[str, Any]] = ContextVar("vault_migration_context", default={})
# Checksums recorded by earlier Vault versions for a migration whose statements did not change.
# 0001 before FREEZE-0001 called module DDL functions; the frozen 0001 runs the same statements
# (fresh-schema pg_dump identical), so databases that recorded the old checksum stay valid.
_EARLIER_CHECKSUMS: dict[int, frozenset[str]] = {
    1: frozenset({"f3fec0487cf0188ad8cd26d877c935ad049139bb7ead0289a0c90cbf6a0fcdd1"}),
}


class MigrationError(RuntimeError):
    """The database schema history does not match this code."""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path

    @property
    def checksum(self) -> str:
        """SHA-256 of the module source, followed by its ``NNNN_name.sql`` statements when present."""
        digest = hashlib.sha256(self.path.read_bytes())
        statements = self.path.with_suffix(".sql")
        if statements.exists():
            digest.update(statements.read_bytes())
        return digest.hexdigest()

    def accepts(self, recorded: str) -> bool:
        return recorded == self.checksum or recorded in _EARLIER_CHECKSUMS.get(self.version, frozenset())

    def load(self):
        spec = importlib.util.spec_from_file_location(
            f"app.vault_runtime.migrations._m{self.version:04d}", self.path,
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return module


def discover(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    found: dict[int, Migration] = {}
    for path in sorted(directory.glob("[0-9]*.py")):
        match = _FILE.match(path.name)
        if match is None:
            raise MigrationError(f"Migration file name is not NNNN_name.py: {path.name}")
        version = int(match.group(1))
        if version in found:
            raise MigrationError(f"Two migrations share version {version:04d}")
        found[version] = Migration(version, match.group(2), path)
    return [found[version] for version in sorted(found)]


def latest_version(directory: Path = MIGRATIONS_DIR) -> int:
    migrations = discover(directory)
    return migrations[-1].version if migrations else 0


def context() -> dict[str, Any]:
    """Values the caller of ``run`` passed for migrations that need them (e.g. ``storage``)."""
    return _CONTEXT.get()


@contextmanager
def _locked(connection: psycopg.Connection) -> Iterator[None]:
    connection.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
    try:
        yield
    finally:
        connection.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))


def _applied(connection: psycopg.Connection) -> dict[int, str]:
    exists = connection.execute(
        "SELECT to_regclass('vault_private.schema_migrations')"
    ).fetchone()[0]
    if exists is None:
        # Created only when missing, so a migrated database sees no DDL at startup.
        with connection.transaction():
            if connection.execute(
                "SELECT 1 FROM pg_namespace WHERE nspname = 'vault_private'"
            ).fetchone() is None:
                connection.execute("CREATE SCHEMA vault_private")
            connection.execute(
                """CREATE TABLE vault_private.schema_migrations (
                  version integer PRIMARY KEY,
                  name text NOT NULL,
                  checksum text NOT NULL,
                  applied_at timestamptz NOT NULL DEFAULT now()
                )"""
            )
    rows = connection.execute(
        "SELECT version, checksum FROM vault_private.schema_migrations ORDER BY version"
    ).fetchall()
    return {int(version): str(checksum) for version, checksum in rows}


def run(database_url: str, *, directory: Path = MIGRATIONS_DIR, **values: Any) -> list[int]:
    """Apply pending migrations in order; return the versions applied by this call."""
    migrations = discover(directory)
    known = {migration.version: migration for migration in migrations}
    applied_now: list[int] = []
    with psycopg.connect(database_url, autocommit=True, connect_timeout=5) as connection:
        with _locked(connection):
            applied = _applied(connection)
            unknown = sorted(set(applied) - set(known))
            if unknown:
                raise MigrationError(
                    f"Database has migration(s) {unknown} that this Vault version does not know; "
                    "it was written by a newer Vault. Install that version or restore an older backup."
                )
            for version, checksum in applied.items():
                if not known[version].accepts(checksum):
                    raise MigrationError(
                        f"Migration {version:04d}_{known[version].name} changed after it was applied. "
                        "Applied migrations are append-only; add a new migration instead."
                    )
            token = _CONTEXT.set(dict(values))
            try:
                for migration in migrations:
                    if migration.version in applied:
                        continue
                    module = migration.load()
                    with connection.transaction(), connection.cursor() as cursor:
                        module.apply(cursor)
                        cursor.execute(
                            """INSERT INTO vault_private.schema_migrations (version, name, checksum)
                               VALUES (%s, %s, %s)""",
                            (migration.version, migration.name, migration.checksum),
                        )
                    _LOG.info("Applied schema migration %04d_%s", migration.version, migration.name)
                    applied_now.append(migration.version)
            finally:
                _CONTEXT.reset(token)
    return applied_now
