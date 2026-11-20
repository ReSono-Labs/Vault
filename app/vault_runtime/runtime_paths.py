from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
from collections.abc import Mapping

VAULT_DATA_ROOT_ENV = "RESONO_VAULT_DATA_ROOT"
VAULT_RUNTIME_ARTIFACT_CACHE_ENV = "RESONO_VAULT_RUNTIME_ARTIFACT_CACHE_ROOT"


def resolve_vault_data_root(
    *, platform: str | None = None, environ: Mapping[str, str] | None = None, home: Path | None = None
) -> Path:
    """Resolve the owner-local Vault data root without requiring privileges."""
    env = os.environ if environ is None else environ
    configured = env.get(VAULT_DATA_ROOT_ENV)
    if configured and configured.strip():
        return Path(configured.strip()).expanduser().resolve()
    platform_name = sys.platform if platform is None else platform
    home_path = Path.home() if home is None else home
    if platform_name == "win32":
        windows_root = env.get("LOCALAPPDATA") or env.get("APPDATA")
        return (Path(windows_root) if windows_root else home_path / "AppData" / "Local") / "ReSono Vault"
    if platform_name == "darwin":
        return home_path / "Library" / "Application Support" / "ReSono Vault"
    xdg_data_home = env.get("XDG_DATA_HOME")
    linux_root = Path(xdg_data_home) if xdg_data_home else home_path / ".local" / "share"
    return linux_root / "resono-vault"


def resolve_configured_runtime_artifact_cache_root(
    *, environ: Mapping[str, str] | None = None
) -> Path:
    env = os.environ if environ is None else environ
    configured = env.get(VAULT_RUNTIME_ARTIFACT_CACHE_ENV)
    if configured and configured.strip():
        return Path(configured.strip()).expanduser().resolve()
    return (resolve_vault_data_root(environ=env) / "runtime-artifacts").resolve()


DEFAULT_VAULT_RUNTIME_ARTIFACT_CACHE_ROOT = resolve_vault_data_root() / "runtime-artifacts"
DEFAULT_RUNTIME_ARTIFACT_CACHE_TEMP_ROOT = Path(tempfile.gettempdir()) / "resono-runtime-artifacts"
DEFAULT_VAULT_RUNTIME_SIGNAL_JOB_ROOT = Path(tempfile.gettempdir()) / "resono-vault-runtime"
DEFAULT_VAULT_RUNTIME_SKILL_JOB_ROOT = Path(tempfile.gettempdir()) / "resono-runtime"
DEFAULT_DEVICE_RUNTIME_AUDIO_CAPTURE_DIR = Path(tempfile.gettempdir()) / "device_runtime_audio_captures"
DEFAULT_RUNTIME_TMPFS_ROOT = Path(tempfile.gettempdir())
DEFAULT_X11_UNIX_SOCKET_MOUNT = Path("/tmp/.X11-unix")
