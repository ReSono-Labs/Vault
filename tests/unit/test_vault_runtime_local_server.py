from __future__ import annotations

import http.client
import json
import socket
from pathlib import Path

from app.vault_runtime.local_api.app import VaultLocalApiApp, _session_cookie_headers
from app.vault_runtime.local_api.config import VaultLocalApiConfig
from app.vault_runtime.local_api.server import VaultLocalServer


class FakeHealthStore:
    def health(self) -> dict[str, object]:
        return {"schemaReady": True, "backend": "test"}


def _config(*, max_body_bytes: int = 1024, web_root: str | None = None) -> VaultLocalApiConfig:
    return VaultLocalApiConfig(
        host="127.0.0.1", port=0, token="local-token", data_root="/tmp/test-vault",
        storage_status_file="/tmp/test-vault/status.json",
        storage_mount_point="/tmp/test-vault/private", max_body_bytes=max_body_bytes,
        web_root=web_root,
    )


def test_local_api_health_is_support_safe() -> None:
    app = VaultLocalApiApp(store=FakeHealthStore(), token="secret")
    response = app.handle(method="GET", target="/health", headers={})
    assert response.status_code == 200
    assert response.payload == {
        "status": "ok", "store": {"schemaReady": True, "backend": "test"}
    }


def test_session_cookies_are_secure_only_for_secure_browser_transport() -> None:
    secure = _session_cookie_headers("session", "csrf", secure=True)
    bridge = _session_cookie_headers("session", "csrf", secure=False)
    assert all("; Secure" in value for _name, value in secure)
    assert all("; Secure" not in value for _name, value in bridge)


def test_local_server_start_health_unknown_route_and_stop() -> None:
    runtime = VaultLocalServer(
        config=_config(), app=VaultLocalApiApp(store=FakeHealthStore(), token="local-token")
    )
    host, port = runtime.start()
    assert runtime.start() == (host, port)
    connection = http.client.HTTPConnection(host, port, timeout=2)
    connection.request("GET", "/health")
    response = connection.getresponse()
    assert response.status == 200
    assert response.getheader("Cache-Control") == "no-store"
    assert json.loads(response.read()) == {
        "status": "ok", "store": {"schemaReady": True, "backend": "test"}
    }
    connection.request("GET", "/missing")
    missing = connection.getresponse()
    assert missing.status == 404
    assert json.loads(missing.read())["error"]["code"] == "not_found"
    connection.close()
    runtime.stop()
    runtime.stop()
    probe = socket.socket()
    try:
        assert probe.connect_ex((host, port)) != 0
    finally:
        probe.close()


def test_local_server_rejects_oversized_body_before_dispatch() -> None:
    runtime = VaultLocalServer(
        config=_config(max_body_bytes=1024),
        app=VaultLocalApiApp(store=FakeHealthStore(), token="local-token"),
    )
    host, port = runtime.start()
    try:
        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.request("POST", "/anything", body=b"x" * 1025)
        response = connection.getresponse()
        assert response.status == 413
        assert json.loads(response.read())["error"]["code"] == "request_too_large"
        connection.close()
    finally:
        runtime.stop()


def test_local_server_serves_browser_voice_with_locked_security_headers(tmp_path: Path) -> None:
    (tmp_path / "browser-voice.html").write_text("<!doctype html><title>Vault</title>", encoding="utf-8")
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("export {};", encoding="utf-8")
    runtime = VaultLocalServer(
        config=_config(web_root=str(tmp_path)),
        app=VaultLocalApiApp(store=FakeHealthStore(), token="local-token"),
    )
    host, port = runtime.start()
    try:
        connection = http.client.HTTPConnection(host, port, timeout=2)
        connection.request("GET", "/")
        response = connection.getresponse()
        assert response.status == 200
        assert response.getheader("Content-Security-Policy")
        assert response.getheader("X-Frame-Options") == "DENY"
        assert response.getheader("Cache-Control") == "no-store"
        assert b"Vault" in response.read()
        connection.request("GET", "/assets/app.js")
        asset = connection.getresponse()
        assert asset.status == 200
        assert "immutable" in asset.getheader("Cache-Control")
        asset.read()
        connection.request("GET", "/%2e%2e/pyproject.toml")
        traversal = connection.getresponse()
        assert traversal.status == 404
        traversal.read()
        connection.close()
    finally:
        runtime.stop()
