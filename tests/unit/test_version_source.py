"""PKG-06: pyproject.toml is the one Vault version source; everything else reads it."""

from __future__ import annotations

import importlib.util
import json
from importlib.metadata import version as package_version
from pathlib import Path
import tomllib

import pytest

from app.vault_runtime.extensions import mcp_client

ROOT = Path(__file__).resolve().parents[2]
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]


def _builder():
    spec = importlib.util.spec_from_file_location("build_artifacts_under_test", ROOT / "scripts" / "release" / "build_artifacts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_builder_reads_pyproject_and_rewrites_any_package_version(tmp_path) -> None:
    builder = _builder()
    assert builder.project_version() == VERSION
    env = tmp_path / "vault.env"
    env.write_text((ROOT / "packaging/docker-release/vault.env").read_text())
    builder.write_package_version(env, "9.8.7")
    builder.write_package_version(env, "9.8.8")
    assert env.read_text().splitlines()[0] == "VAULT_VERSION=9.8.8"
    env.write_text("VAULT_PORT=8765\n")
    with pytest.raises(RuntimeError):
        builder.write_package_version(env, "9.8.7")


def test_package_template_carries_no_version_literal() -> None:
    assert "VAULT_VERSION=\n" in (ROOT / "packaging/docker-release/vault.env").read_text()
    compose = (ROOT / "packaging/docker-release/compose.yml").read_text()
    assert compose.count("resono-labs-vault:${VAULT_VERSION:?") == 2


def test_mcp_client_info_reports_the_installed_vault_version() -> None:
    assert mcp_client.VAULT_VERSION == package_version("resono-labs-vault")


def test_guide_download_links_match_the_built_archive_names() -> None:
    """The Dockerfile names the downloads from the versions; a bump must update the guides too."""
    plugin_guide = (ROOT / "docs/VAULT-PLUGIN-KIT.md").read_text()
    for name in ("plugin-kit", "plugin-python-starter", "plugin-typescript-starter"):
        assert f"/downloads/resono-labs-vault-{name}-{VERSION}.zip" in plugin_guide
    hermes = tomllib.loads((ROOT / "integrations/hermes-vault-memory/pyproject.toml").read_text())["project"]["version"]
    openclaw = json.loads((ROOT / "integrations/openclaw-vault-memory/package.json").read_text())["version"]
    adapter_guide = (ROOT / "docs/HERMES-OPENCLAW-MEMORY.md").read_text()
    assert f"/downloads/resono-vault-hermes-memory-{hermes}.zip" in adapter_guide
    assert f"/downloads/resono-vault-openclaw-memory-{openclaw}.zip" in adapter_guide
