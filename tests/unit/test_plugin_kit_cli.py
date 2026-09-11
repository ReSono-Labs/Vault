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
