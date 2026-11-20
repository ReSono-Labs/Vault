from pathlib import Path

from app.vault_runtime.runtime_paths import resolve_configured_runtime_artifact_cache_root, resolve_vault_data_root


def test_explicit_data_root_wins(tmp_path: Path) -> None:
    assert resolve_vault_data_root(environ={"RESONO_VAULT_DATA_ROOT": str(tmp_path)}) == tmp_path.resolve()


def test_linux_uses_xdg_data_home() -> None:
    assert resolve_vault_data_root(platform="linux", environ={"XDG_DATA_HOME": "/data"}, home=Path("/home/me")) == Path("/data/resono-vault")


def test_linux_has_unprivileged_home_fallback() -> None:
    assert resolve_vault_data_root(platform="linux", environ={}, home=Path("/home/me")) == Path("/home/me/.local/share/resono-vault")


def test_macos_uses_application_support() -> None:
    assert resolve_vault_data_root(platform="darwin", environ={}, home=Path("/Users/me")) == Path("/Users/me/Library/Application Support/ReSono Vault")


def test_windows_uses_local_app_data() -> None:
    assert resolve_vault_data_root(platform="win32", environ={"LOCALAPPDATA": "C:/Users/me/AppData/Local"}, home=Path("C:/Users/me")) == Path("C:/Users/me/AppData/Local/ReSono Vault")


def test_artifact_cache_defaults_inside_vault_root(tmp_path: Path) -> None:
    resolved = resolve_configured_runtime_artifact_cache_root(environ={"RESONO_VAULT_DATA_ROOT": str(tmp_path)})
    assert resolved == (tmp_path / "runtime-artifacts").resolve()


def test_artifact_cache_can_be_explicitly_overridden(tmp_path: Path) -> None:
    resolved = resolve_configured_runtime_artifact_cache_root(
        environ={"RESONO_VAULT_RUNTIME_ARTIFACT_CACHE_ROOT": str(tmp_path)}
    )
    assert resolved == tmp_path.resolve()
