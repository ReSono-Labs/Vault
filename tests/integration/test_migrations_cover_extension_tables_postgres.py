"""Production builds its schema only from migrations. Every table the extension code creates
in tests (``extensions/schema.py``) must exist after the migrations alone, or a deploy starts
code against tables that are missing (the 2026-11-21 outage)."""
from __future__ import annotations

import os
import re

import psycopg
import pytest

from app.vault_runtime.extensions.schema import SCHEMA_STATEMENTS
from app.vault_runtime.migrations import run


def test_migrations_create_every_extension_table() -> None:
    database_url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("VAULT_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
        connection.execute("DROP SCHEMA IF EXISTS vault_background_queue CASCADE")
    try:
        run(database_url)
        expected = {match for statement in SCHEMA_STATEMENTS
                    for match in re.findall(r"CREATE TABLE IF NOT EXISTS vault_private\.(\w+)", statement)}
        with psycopg.connect(database_url) as connection:
            present = {row[0] for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='vault_private'")}
        assert expected and expected - present == set()
    finally:
        with psycopg.connect(database_url) as connection:
            connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
            connection.execute("DROP SCHEMA IF EXISTS vault_background_queue CASCADE")
