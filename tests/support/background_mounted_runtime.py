"""Shared test helpers moved out of test modules (TST-01)."""

from __future__ import annotations

import json
from time import monotonic, sleep

import psycopg

from app.core.security.tokens import hash_token
from app.vault_runtime.local_api.app import _session_token
from app.vault_runtime.local_api.config import VaultLocalApiConfig
from tests.support.conversation_identity import require_test_database


def _reset_schemas(url: str) -> None:
    require_test_database(url)
    with psycopg.connect(url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
        connection.execute("DROP SCHEMA IF EXISTS vault_background_queue CASCADE")


def _api(app, method: str, target: str, headers: dict[str, str], payload: dict | None = None):
    body = b"" if payload is None else json.dumps(payload).encode()
    return app.handle(method=method, target=target, headers=headers, body=body)


def _boot_config(tmp_path, url: str) -> VaultLocalApiConfig:
    return VaultLocalApiConfig(
        host="127.0.0.1",
        port=0,
        token="local-test",
        data_root=str(tmp_path),
        storage_status_file=str(tmp_path / "status.json"),
        storage_mount_point=str(tmp_path / "private"),
        database_url=url,
        setup_credential_hash=hash_token("setup"),
        background_coordination_enabled=True,
        owner_approvals_enabled=True,
        decision_review_enabled=False,
        indexed_memory_enabled=False,
    )


def _onboard_owner(app):
    onboard = _api(
        app,
        "POST",
        "/identity/onboard",
        {},
        {"setupCredential": "setup", "displayName": "Owner", "experienceStyle": "strict"},
    )
    assert onboard.status_code == 201
    cookies = "; ".join(v.split(";", 1)[0] for k, v in onboard.headers if k == "Set-Cookie")
    csrf = next(v.split("=", 1)[1] for v in cookies.split("; ") if v.startswith("resono_csrf="))
    headers = {"Cookie": cookies, "X-ReSono-CSRF": csrf}
    configured = _api(
        app,
        "POST",
        "/providers/openai",
        headers,
        {
            "apiKey": "sk-synthetic-test-only",
            "modelKey": "gpt-realtime",
            "backgroundModelKey": "gpt-5.4-mini",
            "voice": "alloy",
        },
    )
    assert configured.status_code == 200
    principal = app._identity_service.authenticate(session_token=_session_token(headers))
    return principal, headers


def _wait_until(predicate, timeout: float = 12.0, step: float = 0.05):
    deadline = monotonic() + timeout
    last = None
    while monotonic() < deadline:
        last = predicate()
        if last:
            return last
        sleep(step)
    raise AssertionError(f"Timed out waiting for condition; last={last!r}")
