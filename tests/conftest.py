"""Global test safety gates."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest

_INTEGRATION_DIR = Path(__file__).resolve().parent / "integration"


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session: pytest.Session) -> None:
    database_url = os.getenv("VAULT_TEST_DATABASE_URL", "").strip()
    if not database_url:
        # CI and release checks set VAULT_REQUIRE_INTEGRATION=1: a missing database is an error
        # there, not a quiet skip of every integration test.
        if os.getenv("VAULT_REQUIRE_INTEGRATION", "").strip() == "1":
            raise pytest.UsageError(
                "VAULT_REQUIRE_INTEGRATION=1 but VAULT_TEST_DATABASE_URL is not set. "
                "Start the test database (docker compose -f compose.test.yml up -d --wait) and set the URL."
            )
        return
    # One strict guard for every test module (TST-05): only the isolated test database from
    # compose.test.yml, before any fixture connects or drops a schema.
    parts = urlsplit(database_url)
    target = (parts.scheme, parts.hostname, parts.port, parts.path, parts.username)
    if (parts.scheme not in {"postgres", "postgresql"} or target[1:] != ("127.0.0.1", 55436, "/resono_vault_test", "vault_test")
            or parts.query or parts.fragment):
        raise pytest.UsageError(
            f"Refusing to run pytest against {parts.hostname}:{parts.port}{parts.path} as {parts.username!r}. "
            "Use the isolated test database from compose.test.yml (scripts/test_env.py)."
        )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    # Everything under tests/integration needs the isolated database; mark it so a run can
    # select or exclude it (-m integration / -m "not integration").
    for item in items:
        if _INTEGRATION_DIR in Path(str(item.fspath)).resolve().parents:
            item.add_marker(pytest.mark.integration)
