from pathlib import Path
import os

import pytest

from app.vault_runtime.local_api.config import VaultLocalApiConfig


@pytest.fixture(autouse=True)
def clean_vault_environment(monkeypatch) -> None:
    for name in tuple(os.environ):
        if name.startswith("RESONO_"):
            monkeypatch.delenv(name, raising=False)


def test_vault_local_api_config_requires_token(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RESONO_VAULT_DATA_ROOT", str(tmp_path))
    with pytest.raises(RuntimeError, match="LOCAL_API_TOKEN"):
        VaultLocalApiConfig.from_env()


def test_vault_local_api_config_reads_token_file(monkeypatch, tmp_path: Path) -> None:
    token_file = tmp_path / "token"
    token_file.write_text("local-secret\n", encoding="utf-8")
    monkeypatch.setenv("RESONO_VAULT_LOCAL_API_TOKEN_FILE", str(token_file))
    assert VaultLocalApiConfig.from_env().token == "local-secret"


def test_vault_local_api_config_rejects_non_loopback_management_host(monkeypatch) -> None:
    monkeypatch.setenv("RESONO_VAULT_LOCAL_API_TOKEN", "secret")
    monkeypatch.setenv("RESONO_VAULT_LOCAL_API_HOST", "0.0.0.0")
    with pytest.raises(RuntimeError, match="requires TLS"):
        VaultLocalApiConfig.from_env()


def test_vault_local_api_config_requires_origins_for_browser_startup_listener(monkeypatch) -> None:
    monkeypatch.setenv("RESONO_VAULT_LOCAL_API_TOKEN", "secret")
    monkeypatch.setenv("RESONO_VAULT_BROWSER_STARTUP_HOST", "0.0.0.0")
    with pytest.raises(RuntimeError, match="BROWSER_STARTUP_ALLOWED_ORIGINS"):
        VaultLocalApiConfig.from_env()


def test_vault_local_api_config_rejects_browser_startup_wildcard_origin(monkeypatch) -> None:
    monkeypatch.setenv("RESONO_VAULT_LOCAL_API_TOKEN", "secret")
    monkeypatch.setenv("RESONO_VAULT_BROWSER_STARTUP_HOST", "0.0.0.0")
    monkeypatch.setenv("RESONO_VAULT_BROWSER_STARTUP_ALLOWED_ORIGINS", "*")
    with pytest.raises(RuntimeError, match="not '\\*'"):
        VaultLocalApiConfig.from_env()


def test_vault_local_api_config_accepts_explicit_browser_startup_origins(monkeypatch) -> None:
    monkeypatch.setenv("RESONO_VAULT_LOCAL_API_TOKEN", "secret")
    monkeypatch.setenv("RESONO_VAULT_BROWSER_STARTUP_HOST", "0.0.0.0")
    monkeypatch.setenv(
        "RESONO_VAULT_BROWSER_STARTUP_ALLOWED_ORIGINS",
        "http://127.0.0.1:8765, https://voice.example.test/",
    )
    config = VaultLocalApiConfig.from_env()
    assert config.host == "127.0.0.1"
    assert config.browser_startup_allowed_origins == (
        "http://127.0.0.1:8765", "https://voice.example.test"
    )


def test_vault_local_api_config_accepts_browser_media_when_startup_listener_is_enabled(monkeypatch) -> None:
    monkeypatch.setenv("RESONO_VAULT_LOCAL_API_TOKEN", "secret")
    monkeypatch.setenv("RESONO_VAULT_BROWSER_STARTUP_HOST", "127.0.0.1")
    monkeypatch.setenv("RESONO_VAULT_BROWSER_STARTUP_ALLOWED_ORIGINS", "http://127.0.0.1:8765")
    monkeypatch.setenv("RESONO_VAULT_BROWSER_MEDIA_ENABLED", "true")
    config = VaultLocalApiConfig.from_env()
    assert config.browser_media_enabled is True
    assert config.browser_media_port == 8767
    assert config.browser_media_path == "/session-relay/ws"


def test_vault_local_api_config_rejects_browser_media_without_startup_listener(monkeypatch) -> None:
    monkeypatch.setenv("RESONO_VAULT_LOCAL_API_TOKEN", "secret")
    monkeypatch.setenv("RESONO_VAULT_BROWSER_MEDIA_ENABLED", "true")
    with pytest.raises(RuntimeError, match="BROWSER_STARTUP_HOST"):
        VaultLocalApiConfig.from_env()


def test_vault_local_api_config_rejects_shared_browser_ports(monkeypatch) -> None:
    monkeypatch.setenv("RESONO_VAULT_LOCAL_API_TOKEN", "secret")
    monkeypatch.setenv("RESONO_VAULT_BROWSER_STARTUP_HOST", "127.0.0.1")
    monkeypatch.setenv("RESONO_VAULT_BROWSER_STARTUP_ALLOWED_ORIGINS", "http://127.0.0.1:8765")
    monkeypatch.setenv("RESONO_VAULT_BROWSER_MEDIA_ENABLED", "true")
    monkeypatch.setenv("RESONO_VAULT_BROWSER_MEDIA_PORT", "8766")
    with pytest.raises(RuntimeError, match="must differ"):
        VaultLocalApiConfig.from_env()


def test_vault_local_api_config_has_no_cloud_control_plane_fields(monkeypatch) -> None:
    monkeypatch.setenv("RESONO_VAULT_LOCAL_API_TOKEN", "secret")
    config = VaultLocalApiConfig.from_env()
    assert not hasattr(config, "api_base_url")
    assert not hasattr(config, "service_api_key")
    assert not hasattr(config, "r1_tunnel_enabled")


def test_vault_local_api_config_uses_data_root_for_private_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RESONO_VAULT_LOCAL_API_TOKEN", "secret")
    monkeypatch.setenv("RESONO_VAULT_DATA_ROOT", str(tmp_path))
    config = VaultLocalApiConfig.from_env()
    assert config.data_root == str(tmp_path.resolve())
    assert config.storage_mount_point == str(tmp_path.resolve() / "private")
    assert config.device_identity_key_file == str(tmp_path.resolve() / "keys" / "device-identity-ed25519.pem")
    assert config.database_url_file == str(tmp_path.resolve() / "config" / "database-url")


def test_vault_local_api_config_reads_local_database_url_file(monkeypatch, tmp_path: Path) -> None:
    database_url_file = tmp_path / "database-url"
    database_url_file.write_text("postgresql://vault@localhost/vault\n", encoding="utf-8")
    monkeypatch.setenv("RESONO_VAULT_LOCAL_API_TOKEN", "secret")
    monkeypatch.setenv("RESONO_VAULT_DATABASE_URL_FILE", str(database_url_file))
    assert VaultLocalApiConfig.from_env().database_url_value() == "postgresql://vault@localhost/vault"


def test_vault_local_api_config_requires_local_database_configuration(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RESONO_VAULT_LOCAL_API_TOKEN", "secret")
    monkeypatch.setenv("RESONO_VAULT_DATA_ROOT", str(tmp_path))
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        VaultLocalApiConfig.from_env().database_url_value()
