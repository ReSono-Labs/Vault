from __future__ import annotations

import importlib.util
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[2]
CLI_PATH = ROOT / "plugin-kit" / "cli" / "vault_plugin.py"
SPEC = importlib.util.spec_from_file_location("vault_plugin_kit_cli", CLI_PATH)
assert SPEC and SPEC.loader
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


def test_starters_validate_and_package_reproducibly(tmp_path: Path) -> None:
    for language in ("python", "typescript"):
        source = ROOT / "plugin-kit" / "starters" / language
        result = CLI.validate(source)
        assert result["name"] == "starter.example"
        output = tmp_path / f"{language}.zip"
        CLI.package(source, output)
        with zipfile.ZipFile(output) as archive:
            assert "starter.example/plugin.json" in archive.namelist()
            assert all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist())


def test_new_replaces_plugin_identity(tmp_path: Path) -> None:
    target = CLI.create("example.weather", tmp_path, "python")
    assert CLI.validate(target)["name"] == "example.weather"
    assert '"name": "example.weather"' in (target / "plugin.json").read_text()


def test_validate_runs_the_vault_skill_parser_on_every_skill_folder(tmp_path: Path) -> None:
    import shutil

    import pytest

    target = tmp_path / "plugin"
    shutil.copytree(ROOT / "plugin-kit" / "starters" / "python", target)
    assert CLI.validate(target)["skills"] == ["starter"]
    # The same strict rules as import: no fallback to the folder name, no repeated keys.
    (target / "skills" / "starter" / "SKILL.md").write_text(
        "---\ndescription: Missing its name.\n---\nBody\n", encoding="utf-8",
    )
    with pytest.raises(CLI.KitError, match="skills/starter: .*name"):
        CLI.validate(target)
    (target / "skills" / "starter" / "SKILL.md").write_text(
        "---\nname: starter\nname: starter\ndescription: Twice.\n---\n", encoding="utf-8",
    )
    with pytest.raises(CLI.KitError, match="repeats the key 'name'"):
        CLI.validate(target)
    (target / "skills" / "starter" / "SKILL.md").write_text(
        "---\r\nname: starter\r\ndescription: CRLF and a closing line at end of file.\r\n---", encoding="utf-8",
    )
    assert CLI.validate(target)["skills"] == ["starter"]
    (target / "skills" / "notes.txt").write_text("not a skill", encoding="utf-8")
    with pytest.raises(CLI.KitError, match="skills/notes.txt must be a directory"):
        CLI.validate(target)


def _minimal(tmp_path: Path, name: str = "portable.demo") -> Path:
    import json

    root = tmp_path / name
    root.mkdir()
    (root / "plugin.json").write_text(json.dumps({"$schema": CLI.AGENT_PLUGIN_SCHEMA, "name": name}), encoding="utf-8")
    return root


def test_starters_use_the_vault_namespace_and_no_vault_json() -> None:
    for language in ("python", "typescript"):
        source = ROOT / "plugin-kit" / "starters" / language
        assert not (source / "vault.json").exists()
        result = CLI.validate(source)
        assert result["vault"]["agents"] == ["voice", "background"] and result["warnings"] == []
        assert result["mcpServers"] == ["starter"]


def test_portable_package_without_vault_json_validates(tmp_path: Path) -> None:
    root = _minimal(tmp_path)
    result = CLI.validate(root)
    assert (result["vault"], result["skills"], result["mcpServers"]) == ({}, [], [])


def test_legacy_vault_json_still_validates_and_loses_to_the_namespace(tmp_path: Path) -> None:
    import json
    import shutil

    target = tmp_path / "legacy"
    shutil.copytree(ROOT / "plugin-kit" / "starters" / "python", target)
    plugin = json.loads((target / "plugin.json").read_text())
    namespace = plugin.pop("extensions")[CLI.VAULT_NAMESPACE]
    (target / "plugin.json").write_text(json.dumps(plugin))
    (target / "vault.json").write_text(json.dumps({"$schema": CLI.VAULT_SCHEMA, **namespace}))
    shutil.move(target / CLI.VAULT_NAMESPACE / "config.schema.json", target / "config.schema.json")
    result = CLI.validate(target)
    assert result["vault"]["agents"] == ["voice", "background"]
    assert any("legacy" in item for item in result["warnings"])
    plugin["extensions"] = {CLI.VAULT_NAMESPACE: {"minimumVaultVersion": "0.1.0", "agents": ["voice"]}}
    (target / "plugin.json").write_text(json.dumps(plugin))
    result = CLI.validate(target)
    assert result["vault"]["agents"] == ["voice"]
    assert any("vault.json is ignored" in item for item in result["warnings"])


def test_validate_checks_root_mcp_json_with_the_runtime_rules(tmp_path: Path) -> None:
    import json

    import pytest

    root = _minimal(tmp_path)

    def mcp(servers):
        (root / "mcp.json").write_text(json.dumps({"$schema": CLI.MCP_SCHEMA, "mcpServers": servers}))

    mcp({"remote": {"type": "streamable-http", "url": "https://example.test/mcp", "headers": {"X-Tenant": "t"}},
         "cli": {"type": "stdio", "command": "server"}})
    result = CLI.validate(root)
    assert result["mcpServers"] == ["remote"]
    assert any("cli" in item and "unsupported transport stdio" in item for item in result["warnings"])
    for servers, message in (
        ({"remote": {"type": "streamable-http", "url": "https://example.test/mcp", "headers": {"Authorization": "x"}}}, "secret fields"),
        ({"remote": {"type": "streamable-http", "url": "https://example.test/mcp", "headers": {"X-Vault-Capability": "x"}}}, "set by Vault"),
        ({"remote": {"type": "streamable-http", "url": "https://example.test/mcp", "headers": {"Bad Name": "x"}}}, "valid HTTP field name"),
        ({"a/b": {"type": "streamable-http", "url": "https://example.test/mcp"}}, "safe path segment"),
        ({"remote": {"type": "streamable-http", "url": "https://u:p@example.test/mcp"}}, "no credentials"),
        ({"remote": {"type": "nope", "url": "https://example.test/mcp"}}, "mcp.json"),
    ):
        mcp(servers)
        with pytest.raises(CLI.KitError, match=message):
            CLI.validate(root)


def test_new_uses_the_agent_plugins_name_pattern(tmp_path: Path) -> None:
    import pytest

    for bad in ("my_plugin", "a--b", "a..b", "-a", "a" * 65):
        with pytest.raises(CLI.KitError, match="1-64 lowercase"):
            CLI.create(bad, tmp_path, "python")
    plugin = _minimal(tmp_path, "unsupported.version")
    plugin.joinpath("plugin.json").write_text('{"$schema": "https://agent-plugins.org/schemas/9.0.0/plugin.schema.json", "name": "x"}')
    with pytest.raises(CLI.KitError, match="unsupported Agent Plugins version"):
        CLI.validate(plugin)
