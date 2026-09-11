from pathlib import Path

from app.vault_runtime.extensions.import_diagnostics import blocking_import_diagnostics
from app.vault_runtime.extensions.package_review import review_plugin_package
from app.vault_runtime.extensions.skills import parse_skill_document


def test_blocking_import_diagnostics_ignores_review_and_partial_component_issues() -> None:
    diagnostics = (
        "review:medium:executable-content:server.py: contains code",
        "skill:crm-ops: name must be 1-64 lowercase letters, digits, or hyphens",
        "mcp:invalid: unsupported transport",
        "plugin.json ignored unknown top-level field: unknown",
        "migration: database payload is missing",
        "runtime.command is empty",
    )
    assert blocking_import_diagnostics(diagnostics) == (
        "migration: database payload is missing",
        "runtime.command is empty",
    )


def test_package_review_skips_migration_tree(tmp_path: Path) -> None:
    (tmp_path / "plugin.json").write_text('{"name":"demo"}', encoding="utf-8")
    (tmp_path / "server.py").write_text("print('ok')\n", encoding="utf-8")
    migration_script = tmp_path / "migration" / "workspace" / "ops" / "crm" / "run.sh"
    migration_script.parent.mkdir(parents=True)
    migration_script.write_text("#!/bin/sh\n", encoding="utf-8")
    review = review_plugin_package(tmp_path)
    paths = {item.path for item in review.findings}
    assert "server.py" in paths
    assert "migration/workspace/ops/crm/run.sh" not in paths


def test_skill_name_defaults_to_directory_when_frontmatter_omits_name(tmp_path: Path) -> None:
    skill = tmp_path / "crm-ops"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\ndescription: CRM operations guidance.\n---\nUse CRM tools.\n",
        encoding="utf-8",
    )
    document = parse_skill_document(skill / "SKILL.md", expected_directory="crm-ops")
    assert document.name == "crm-ops"
