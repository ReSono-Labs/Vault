from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_link_bridge_is_loopback_only_and_verifies_vault_tls() -> None:
    compose = (PROJECT_ROOT / "compose.yml").read_text(encoding="utf-8")
    nginx = (PROJECT_ROOT / "docker/link-bridge/nginx.conf").read_text(encoding="utf-8")

    assert '"127.0.0.1:${VAULT_LINK_BRIDGE_PORT:-8766}:8766"' in compose
    assert 'user: "10001:10001"' in compose
    assert "vault_data:/vault-data:ro" in compose
    assert "proxy_pass https://vault:8765;" in nginx
    assert "proxy_ssl_verify on;" in nginx
    assert "proxy_ssl_name localhost;" in nginx
    assert "proxy_ssl_trusted_certificate /vault-data/tls/vault-local-ca.crt;" in nginx


def test_link_bridge_preserves_forwarding_and_websocket_headers() -> None:
    nginx = (PROJECT_ROOT / "docker/link-bridge/nginx.conf").read_text(encoding="utf-8")

    assert "proxy_set_header X-Forwarded-Host $forwarded_host;" in nginx
    assert "proxy_set_header X-Forwarded-Proto $forwarded_proto;" in nginx
    assert "proxy_set_header Upgrade $http_upgrade;" in nginx
    assert "proxy_set_header Connection $connection_upgrade;" in nginx
