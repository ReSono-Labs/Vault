"""Global test safety gates."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session: pytest.Session) -> None:
    database_url = os.getenv("VAULT_TEST_DATABASE_URL", "").strip()
    if not database_url:
        return
    database_name = urlsplit(database_url).path.lstrip("/")
    if database_name != "resono_vault_test":
        raise pytest.UsageError(
            f"Refusing to run pytest against non-test database {database_name!r}. "
            "Automated tests may target only resono_vault_test through scripts/test_env.py."
        )
