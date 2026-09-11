from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_openclaw_pairing_explicitly_disables_local_dreaming() -> None:
    pairing = (ROOT / "integrations/openclaw-vault-memory/pair.mjs").read_text()
    assert "dreaming: { enabled: false }" in pairing


def test_openclaw_manifest_defaults_local_dreaming_off() -> None:
    manifest = json.loads(
        (ROOT / "integrations/openclaw-vault-memory/openclaw.plugin.json").read_text()
    )
    dreaming = manifest["configSchema"]["properties"]["dreaming"]
    assert dreaming["properties"]["enabled"]["default"] is False


def test_user_guide_links_both_adapter_downloads() -> None:
    guide = (ROOT / "docs/HERMES-OPENCLAW-MEMORY.md").read_text()
    assert "/downloads/resono-vault-hermes-memory-0.1.0.zip" in guide
    assert "/downloads/resono-vault-openclaw-memory-0.1.0.zip" in guide
    assert "/vault-local-ca.crt" in guide


def test_plugin_packages_use_the_vault_noncommercial_license() -> None:
    hermes = (ROOT / "integrations/hermes-vault-memory/pyproject.toml").read_text()
    openclaw = json.loads(
        (ROOT / "integrations/openclaw-vault-memory/package.json").read_text()
    )
    assert "LicenseRef-PolyForm-Noncommercial-1.0.0" in hermes
    assert openclaw["license"] == "SEE LICENSE IN LICENSE.md"
