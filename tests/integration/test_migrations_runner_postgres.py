"""Migration runner: order, checksums, one transaction per migration, advisory lock (DB-RUNNER)."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import psycopg
import pytest

from app.vault_runtime.migrations import runner
from app.vault_runtime.migrations.runner import LOCK_KEY, MigrationError, discover, run

_TABLE = "vault_private.migration_runner_probe"


@pytest.fixture()
def database_url():
    url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Isolated PostgreSQL harness is required; a skip is not verification.")
    with psycopg.connect(url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
    yield url
    with psycopg.connect(url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")


def _write(directory: Path, name: str, body: str) -> None:
    (directory / name).write_text("def apply(cursor):\n" + "".join(f"    {line}\n" for line in body.splitlines()))


def _rows(url: str, query: str):
    with psycopg.connect(url) as connection:
        return connection.execute(query).fetchall()


def test_discover_orders_by_version_and_rejects_bad_names(tmp_path: Path) -> None:
    _write(tmp_path, "0002_second.py", "pass")
    _write(tmp_path, "0010_tenth.py", "pass")
    _write(tmp_path, "0001_first.py", "pass")
    assert [(m.version, m.name) for m in discover(tmp_path)] == [(1, "first"), (2, "second"), (10, "tenth")]
    _write(tmp_path, "0002_again.py", "pass")
    with pytest.raises(MigrationError, match="share version 0002"):
        discover(tmp_path)
    (tmp_path / "0002_again.py").unlink()
    _write(tmp_path, "3_bad.py", "pass")
    with pytest.raises(MigrationError, match="NNNN_name"):
        discover(tmp_path)


def test_applies_pending_in_order_once_and_records_checksums(database_url: str, tmp_path: Path) -> None:
    _write(tmp_path, "0001_create.py", f"cursor.execute('CREATE TABLE {_TABLE} (step text)')")
    _write(tmp_path, "0002_fill.py", f"cursor.execute(\"INSERT INTO {_TABLE} VALUES ('two')\")")
    assert run(database_url, directory=tmp_path) == [1, 2]
    _write(tmp_path, "0003_more.py", f"cursor.execute(\"INSERT INTO {_TABLE} VALUES ('three')\")")
    assert run(database_url, directory=tmp_path) == [3]
    assert run(database_url, directory=tmp_path) == []
    assert _rows(database_url, f"SELECT step FROM {_TABLE} ORDER BY step") == [("three",), ("two",)]
    recorded = _rows(database_url, "SELECT version, name, checksum FROM vault_private.schema_migrations ORDER BY version")
    assert [(v, n) for v, n, _ in recorded] == [(1, "create"), (2, "fill"), (3, "more")]
    assert [c for _, _, c in recorded] == [m.checksum for m in discover(tmp_path)]


def test_refuses_changed_checksum_and_unknown_version(database_url: str, tmp_path: Path) -> None:
    _write(tmp_path, "0001_create.py", f"cursor.execute('CREATE TABLE {_TABLE} (step text)')")
    run(database_url, directory=tmp_path)
    _write(tmp_path, "0001_create.py", f"cursor.execute('CREATE TABLE {_TABLE} (step text, extra int)')")
    _write(tmp_path, "0002_never.py", f"cursor.execute(\"INSERT INTO {_TABLE} VALUES ('no')\")")
    with pytest.raises(MigrationError, match="0001_create changed after it was applied"):
        run(database_url, directory=tmp_path)
    assert _rows(database_url, f"SELECT count(*) FROM {_TABLE}") == [(0,)]
    newer = tmp_path / "newer"
    newer.mkdir()
    with pytest.raises(MigrationError, match=r"migration\(s\) \[1\]"):
        run(database_url, directory=newer)


def test_failed_migration_rolls_back_and_stops(database_url: str, tmp_path: Path) -> None:
    _write(tmp_path, "0001_create.py", f"cursor.execute('CREATE TABLE {_TABLE} (step text)')")
    _write(tmp_path, "0002_broken.py",
           f"cursor.execute(\"INSERT INTO {_TABLE} VALUES ('partial')\")\ncursor.execute('SELECT * FROM no_such_table')")
    _write(tmp_path, "0003_after.py", f"cursor.execute(\"INSERT INTO {_TABLE} VALUES ('after')\")")
    with pytest.raises(psycopg.errors.UndefinedTable):
        run(database_url, directory=tmp_path)
    assert _rows(database_url, f"SELECT count(*) FROM {_TABLE}") == [(0,)]
    assert _rows(database_url, "SELECT version FROM vault_private.schema_migrations") == [(1,)]
    with psycopg.connect(database_url) as connection:  # the lock was released
        assert connection.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_KEY,)).fetchone()[0] is True


def test_second_runner_waits_for_the_lock(database_url: str, tmp_path: Path) -> None:
    _write(tmp_path, "0001_create.py", f"cursor.execute('CREATE TABLE {_TABLE} (step text)')")
    done: list[object] = []
    with psycopg.connect(database_url, autocommit=True) as holder:
        holder.execute("SELECT pg_advisory_lock(%s)", (LOCK_KEY,))
        worker = threading.Thread(target=lambda: done.append(run(database_url, directory=tmp_path)))
        worker.start()
        time.sleep(1.0)
        assert done == [] and _rows(database_url, f"SELECT to_regclass('{_TABLE}')") == [(None,)]
        holder.execute("SELECT pg_advisory_unlock(%s)", (LOCK_KEY,))
        worker.join(timeout=10)
    assert done == [[1]]


def test_context_values_reach_migrations(database_url: str, tmp_path: Path) -> None:
    seen: list[object] = []
    runner._TEST_SINK = seen  # read by the migration below
    try:
        _write(tmp_path, "0001_ctx.py",
               "from app.vault_runtime.migrations import runner\nrunner._TEST_SINK.append(runner.context().get('storage'))")
        run(database_url, directory=tmp_path, storage="disk")
    finally:
        del runner._TEST_SINK
    assert seen == ["disk"]


def test_checksum_covers_the_frozen_sql(tmp_path: Path) -> None:  # FREEZE-0001
    _write(tmp_path, "0001_frozen.py", "pass")
    plain = discover(tmp_path)[0].checksum
    (tmp_path / "0001_frozen.sql").write_text("-- @statement\nSELECT 1\n")
    with_sql = discover(tmp_path)[0].checksum
    (tmp_path / "0001_frozen.sql").write_text("-- @statement\nSELECT 2\n")
    assert len({plain, with_sql, discover(tmp_path)[0].checksum}) == 3
    real = discover()[0]
    assert real.version == 1 and real.path.with_suffix(".sql").exists()


def test_database_with_the_pre_freeze_0001_checksum_stays_valid(database_url: str, tmp_path: Path) -> None:
    # Installs that applied 0001 before FREEZE-0001 recorded the checksum of the old module.
    real = discover()[0]
    for source in (real.path, real.path.with_suffix(".sql")):
        (tmp_path / source.name).write_bytes(source.read_bytes())
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute("CREATE SCHEMA vault_private")
        connection.execute("""CREATE TABLE vault_private.schema_migrations (version integer PRIMARY KEY,
            name text NOT NULL, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())""")
        connection.execute("INSERT INTO vault_private.schema_migrations (version, name, checksum) VALUES (1, 'baseline', %s)",
                           ("f3fec0487cf0188ad8cd26d877c935ad049139bb7ead0289a0c90cbf6a0fcdd1",))
    assert run(database_url, directory=tmp_path) == []
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute("UPDATE vault_private.schema_migrations SET checksum = 'other' WHERE version = 1")
    with pytest.raises(MigrationError, match="0001_baseline changed after it was applied"):
        run(database_url, directory=tmp_path)
