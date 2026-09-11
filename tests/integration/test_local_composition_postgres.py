from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
import pytest

from app.core.security.tokens import hash_token
from app.vault_runtime.composition import build_local_app
from app.vault_runtime.local_api.config import VaultLocalApiConfig


def test_production_composition_exposes_local_voice_extensions_and_provider(tmp_path: Path) -> None:
    database_url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("VAULT_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
    config = VaultLocalApiConfig(
        host="127.0.0.1", port=0, token="local-token", data_root=str(tmp_path),
        storage_status_file=str(tmp_path / "status.json"),
        storage_mount_point=str(tmp_path / "private"), database_url=database_url,
        setup_credential_hash=hash_token("setup"),
    )
    app = build_local_app(config)
    onboard = app.handle(
        method="POST", target="/identity/onboard", headers={},
        body=json.dumps({
            "setupCredential": "setup", "displayName": "Owner", "experienceStyle": "strict",
        }).encode(),
    )
    assert onboard.status_code == 201
    cookies = "; ".join(value.split(";", 1)[0] for name, value in onboard.headers if name == "Set-Cookie")
    csrf = next(value.split("=", 1)[1] for value in cookies.split("; ") if value.startswith("resono_csrf="))
    headers = {"Cookie": cookies, "X-ReSono-CSRF": csrf}
    background = app.handle(
        method="POST", target="/background/runs", headers=headers,
        body=json.dumps({
            "objective": "Return local status.", "instructionProfile": "strict",
            "successCriteria": ["Status exists."],
            "resultSchema": {"type": "object", "properties": {"status": {"type": "string"}}, "required": ["status"]},
            "originalRequest": "Return local status.", "verificationMethod": "Validate schema.",
            "completionConditions": ["Status exists."], "requestedToolNames": [],
        }).encode(),
    )
    assert background.status_code == 202 and background.payload["agentKind"] == "background"
    assert app.handle(method="GET", target="/extensions/runtime", headers=headers).payload == {"safeMode": True}
    assert app.handle(method="GET", target="/providers/openai", headers=headers).payload["configured"] is False
    def mail_credentials(address: str, suffix: str) -> dict[str, object]:
        return {
            "emailAddress": address,
            "imap": {"host": "imap.example.com", "port": 993, "username": address, "password": f"imap-{suffix}", "useTls": True},
            "smtp": {"host": "smtp.example.com", "port": 465, "username": address, "password": f"smtp-{suffix}", "useTls": True},
        }
    for address, suffix in (("one@example.com", "one"), ("two@example.com", "two")):
        connected = app.handle(
            method="POST", target="/mail/accounts", headers=headers,
            body=json.dumps({
                "credentials": mail_credentials(address, suffix),
                "validateConnection": False,
            }).encode(),
        )
        assert connected.status_code == 201
        assert f"imap-{suffix}" not in json.dumps(connected.payload)
        assert f"smtp-{suffix}" not in json.dumps(connected.payload)
    mailboxes = app.handle(method="GET", target="/mail/accounts", headers=headers)
    assert len(mailboxes.payload["items"]) == 2
    calendar = app.handle(
        method="POST", target="/calendar/accounts", headers=headers,
        body=json.dumps({
            "providerType": "ics", "displayName": "Family calendar",
            "credentials": {"feedUrl": "https://calendar.example.test/family.ics"},
            "validateConnection": False,
        }).encode(),
    )
    assert calendar.status_code == 201
    assert calendar.payload["displayName"] == "Family calendar"
    assert app.handle(method="GET", target="/calendar/accounts", headers=headers).payload["items"] == [calendar.payload]
    removed = app.handle(
        method="DELETE", target=f"/calendar/accounts/{calendar.payload['calendarAccountId']}", headers=headers,
    )
    assert removed.status_code == 200
    configured = app.handle(
        method="POST", target="/providers/openai", headers=headers,
        body=json.dumps({"apiKey": "sk-owner-local", "modelKey": "gpt-realtime",
                         "backgroundModelKey": "gpt-5.6-sol", "voice": "alloy"}).encode(),
    )
    assert configured.status_code == 200 and configured.payload["configured"] is True
    assert "sk-owner-local" not in json.dumps(configured.payload)
    assert app.handle(method="GET", target="/system-agents", headers=headers).payload["items"] == [
        {"kind": "voice", "displayName": "Voice Agent", "interactive": True},
        {"kind": "background", "displayName": "Background Agent", "interactive": False},
    ]
    app.close()
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
