"""Vault's Docker network on Linux, where Link's connector serves Vault's Agent Network gateway.

On Linux, folders.sh pins Vault's compose network to 198.19.235.0/24 and points
host.docker.internal at its gateway 198.19.235.1, the address Link's Vault manifest names
([container_gateway] bind). macOS (and Windows, vault.ps1) keep Docker Desktop's host-gateway.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FOLDERS = ROOT / "packaging" / "docker-release" / "folders.sh"
LINK_GATEWAY = "198.19.235.1"


def _override(tmp_path: Path, system: str | None = None) -> str:
    env = dict(os.environ)
    if system is not None:
        stub = tmp_path / "bin"
        stub.mkdir()
        uname = stub / "uname"
        uname.write_text(f"#!/bin/sh\necho {system}\n", encoding="utf-8")
        uname.chmod(uname.stat().st_mode | stat.S_IXUSR)
        env["PATH"] = f"{stub}:{env['PATH']}"
    output = tmp_path / "compose.folders.yml"
    subprocess.run(["sh", str(FOLDERS), "compose", str(output), "link_bridge"], check=True, env=env)
    return output.read_text(encoding="utf-8")


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="the Linux branch of folders.sh")
def test_linux_pins_vault_network_and_points_host_docker_internal_at_its_gateway(tmp_path: Path) -> None:
    text = _override(tmp_path)
    assert "    extra_hosts: !override\n" in text
    assert f'      - "host.docker.internal:{LINK_GATEWAY}"\n' in text
    assert "networks:\n  default:\n    ipam:\n      config:\n" in text
    assert f"        - subnet: 198.19.235.0/24\n          gateway: {LINK_GATEWAY}\n" in text


def test_macos_keeps_docker_desktop_host_gateway(tmp_path: Path) -> None:
    text = _override(tmp_path, "Darwin")
    assert "extra_hosts" not in text
    assert "networks:" not in text


def test_link_gateway_address_matches_the_transport() -> None:
    from app.vault_runtime.link_companion.transport import COMPANION_DOCKER_GATEWAY

    assert COMPANION_DOCKER_GATEWAY == "http://host.docker.internal:8769"
    assert f"link_gateway={LINK_GATEWAY}" in FOLDERS.read_text(encoding="utf-8")
