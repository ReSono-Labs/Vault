from __future__ import annotations

from http.cookies import SimpleCookie
import http.client
import json
import os
from urllib.parse import parse_qs, urlsplit

import psycopg
import pytest

from app.core.security.tokens import hash_token
from app.vault_runtime.local_api.app import VaultLocalApiApp
from app.vault_runtime.local_api.config import VaultLocalApiConfig
from app.vault_runtime.local_api.server import VaultLocalServer
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.local_identity.service import LocalIdentityService


class HealthStore:
    def health(self):
        return {"database": "ok", "schemaReady": True}


@pytest.fixture()
def local_identity_http_server():
    database_url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("VAULT_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
    setup_credential = "http-setup-credential"
    identity = LocalIdentityService(
        repository=LocalIdentityRepository(database_url=database_url),
        setup_credential_hash=hash_token(setup_credential),
    )
    identity.ensure_schema()
    config = VaultLocalApiConfig(
        host="127.0.0.1", port=0, token="foundation-token", data_root="/tmp/vault-http-test",
        storage_status_file="/tmp/vault-http-test/status.json",
        storage_mount_point="/tmp/vault-http-test/private", database_url=database_url,
    )
    runtime = VaultLocalServer(
        config=config,
        app=VaultLocalApiApp(store=HealthStore(), token=config.token, identity_service=identity),
    )
    host, port = runtime.start()
    yield host, port, setup_credential
    runtime.stop()
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")


def _request(connection, method: str, path: str, payload=None, headers=None):
    body = json.dumps(payload).encode() if payload is not None else None
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    connection.request(method, path, body=body, headers=request_headers)
    response = connection.getresponse()
    response_body = response.read()
    return response, json.loads(response_body) if response_body else {}


def _cookies(response) -> tuple[str, str, str]:
    values = response.msg.get_all("Set-Cookie") or []
    jar = SimpleCookie()
    for value in values:
        jar.load(value)
    session_token = jar["resono_refresh"].value
    csrf_token = jar["resono_csrf"].value
    cookie_header = f"resono_refresh={session_token}; resono_csrf={csrf_token}"
    return session_token, csrf_token, cookie_header


def test_setup_session_cookie_survives_refresh_before_owner_registration(local_identity_http_server) -> None:
    host, port, setup_credential = local_identity_http_server
    connection = http.client.HTTPConnection(host, port, timeout=4)
    started, body = _request(connection, "POST", "/identity/setup-session", {
        "setupCredential": setup_credential,
    })
    assert started.status == 200 and body["status"] == "ready"
    jar = SimpleCookie()
    for value in started.msg.get_all("Set-Cookie") or []:
        jar.load(value)
    resume_cookie = jar["resono_setup_resume"].value
    registration, registered = _request(connection, "POST", "/identity/register", {
        "setupCredential": "", "username": "owner", "password": "owner-password",
        "displayName": "Owner", "experienceStyle": "warm",
    }, {"Cookie": f"resono_setup_resume={resume_cookie}"})
    assert registration.status == 201
    assert registered["user"]["username"] == "owner"
    assert any("resono_setup_resume=;" in value and "Max-Age=0" in value
               for value in registration.msg.get_all("Set-Cookie") or [])


def test_server_setup_link_validates_then_redirects_without_fragment(local_identity_http_server) -> None:
    host, port, setup_credential = local_identity_http_server
    connection = http.client.HTTPConnection(host, port, timeout=4)
    response, body = _request(connection, "GET", f"/identity/setup/start?credential={setup_credential}")
    assert response.status == 303 and body["status"] == "ready"
    location = response.getheader("Location") or ""
    assert urlsplit(location).path == "/browser-voice.html"
    query = parse_qs(urlsplit(location).query)
    assert query == {"setup": ["fresh"], "bootstrap": [setup_credential]}
    assert "no-store" in (response.getheader("Cache-Control") or "")
    assert "resono_setup_resume=" in (response.getheader("Set-Cookie") or "")


def test_server_setup_link_bootstrap_query_completes_registration_without_cookie(local_identity_http_server) -> None:
    host, port, setup_credential = local_identity_http_server
    connection = http.client.HTTPConnection(host, port, timeout=4)
    response, _body = _request(connection, "GET", f"/identity/setup/start?credential={setup_credential}")
    bootstrap = parse_qs(urlsplit(response.getheader("Location") or "").query)["bootstrap"][0]
    registration, registered = _request(connection, "POST", "/identity/register", {
        "setupCredential": bootstrap, "username": "owner", "password": "owner-password",
        "displayName": "Owner", "experienceStyle": "warm",
    })
    assert registration.status == 201
    assert registered["user"]["username"] == "owner"


def test_browser_cookie_csrf_and_authenticated_workspace_flow(local_identity_http_server) -> None:
    host, port, setup_credential = local_identity_http_server
    connection = http.client.HTTPConnection(host, port, timeout=4)
    registration, registered = _request(connection, "POST", "/identity/register", {
        "setupCredential": setup_credential, "username": "owner", "password": "owner-password",
        "displayName": "Owner", "experienceStyle": "concise",
    })
    assert registration.status == 201
    assert registered["user"]["username"] == "owner"
    set_cookie_values = registration.msg.get_all("Set-Cookie") or []
    assert any("HttpOnly" in value and "SameSite=Strict" in value for value in set_cookie_values)
    _token, csrf, cookie = _cookies(registration)

    me_response, me = _request(connection, "GET", "/me", headers={"Cookie": cookie})
    assert me_response.status == 200
    assert me["user"]["activeWorkspaceId"] == registered["user"]["activeWorkspaceId"]

    denied, denied_payload = _request(
        connection, "POST", "/local-users",
        {"username": "second", "password": "second-password", "displayName": "Second", "experienceStyle": "warm", "ageGroup": "adult"},
        {"Cookie": cookie, "x-resono-csrf": "wrong"},
    )
    assert denied.status == 401
    assert denied_payload["error"]["code"] == "local_session_invalid"

    created, created_payload = _request(
        connection, "POST", "/local-users",
        {"username": "second", "password": "second-password", "displayName": "Second", "experienceStyle": "warm", "ageGroup": "adult"},
        {"Cookie": cookie, "x-resono-csrf": csrf},
    )
    assert created.status == 201 and created_payload["userId"]

    logged_out, payload = _request(
        connection, "POST", "/identity/logout", {},
        {"Cookie": cookie, "x-resono-csrf": csrf},
    )
    assert logged_out.status == 200 and payload["status"] == "logged_out"
    cleared = logged_out.msg.get_all("Set-Cookie") or []
    assert len(cleared) == 2 and all("Max-Age=0" in value for value in cleared)
    stale, _payload = _request(connection, "GET", "/me", headers={"Cookie": cookie})
    assert stale.status == 401
    connection.close()


def test_minimal_onboarding_asks_only_name_and_experience_and_generates_recovery(local_identity_http_server) -> None:
    host, port, setup_credential = local_identity_http_server
    connection = http.client.HTTPConnection(host, port, timeout=4)
    status, payload = _request(connection, "GET", "/identity/status")
    assert status.status == 200 and payload == {"setupComplete": False}
    created, body = _request(connection, "POST", "/identity/onboard", {
        "setupCredential": setup_credential,
        "displayName": "Local Owner",
        "experienceStyle": "funny",
    })
    assert created.status == 201
    assert body["user"]["displayName"] == "Local Owner"
    assert body["user"]["experienceStyle"] == "funny"
    assert body["recovery"]["username"] == "owner"
    assert len(body["recovery"]["generatedPassword"]) >= 20
    assert body["recovery"]["mustStoreNow"] is True
    complete, complete_body = _request(connection, "GET", "/identity/status")
    assert complete.status == 200 and complete_body == {"setupComplete": True}
    connection.close()


def test_temporary_password_session_is_restricted_until_changed(local_identity_http_server) -> None:
    host, port, setup_credential = local_identity_http_server
    connection = http.client.HTTPConnection(host, port, timeout=4)
    registration, _body = _request(connection, "POST", "/identity/register", {
        "setupCredential": setup_credential, "username": "owner", "password": "owner-password",
        "displayName": "Owner", "experienceStyle": "concise",
    })
    _owner_token, owner_csrf, owner_cookie = _cookies(registration)
    created, _created_body = _request(connection, "POST", "/local-users", {
        "username": "second", "password": "temporary-password", "passwordMode": "temporary_password",
        "displayName": "Second", "experienceStyle": "warm", "ageGroup": "under_18",
    }, {"Cookie": owner_cookie, "x-resono-csrf": owner_csrf})
    assert created.status == 201

    login, login_body = _request(connection, "POST", "/identity/login", {
        "username": "second", "password": "temporary-password",
    })
    assert login.status == 200 and login_body["user"]["mustChangePassword"] is True
    assert login_body["user"]["ageGroup"] == "under_18"
    _token, csrf, cookie = _cookies(login)
    me, me_body = _request(connection, "GET", "/me", headers={"Cookie": cookie})
    assert me.status == 200 and me_body["user"]["passwordMode"] == "temporary_password"
    denied, denied_body = _request(connection, "GET", "/workspaces", headers={"Cookie": cookie})
    assert denied.status == 403 and denied_body["error"]["code"] == "password_change_required"
    refreshed, refreshed_body = _request(
        connection, "POST", "/identity/token/refresh", {},
        {"Cookie": cookie, "x-resono-csrf": csrf},
    )
    assert refreshed.status == 403 and refreshed_body["error"]["code"] == "password_change_required"
    changed, _changed_body = _request(connection, "POST", "/identity/password", {
        "currentPassword": "temporary-password", "newPassword": "chosen-password",
    }, {"Cookie": cookie, "x-resono-csrf": csrf})
    assert changed.status == 200
    allowed, _allowed_body = _request(connection, "GET", "/workspaces", headers={"Cookie": cookie})
    assert allowed.status == 200
    connection.close()
