from pathlib import Path

import pytest

from app.vault_runtime.extensions.skills import (
    SkillSpecificationError, confined_skill_resource, parse_skill,
)


def test_parses_standard_skill_without_treating_allowed_tools_as_grants(tmp_path: Path) -> None:
    root = tmp_path / "pdf-work"
    root.mkdir()
    (root / "SKILL.md").write_text(
        "---\nname: pdf-work\ndescription: Work with PDF files when asked.\n"
        "license: Apache-2.0\nmetadata:\n  author: local\nallowed-tools: Shell(*)\n---\nDo the work.\n",
        encoding="utf-8",
    )
    document = parse_skill(root)
    assert document.name == "pdf-work"
    assert document.instructions == "Do the work.\n"
    assert document.allowed_tools == "Shell(*)"
    assert not hasattr(document, "grants")


@pytest.mark.parametrize("name", ["UPPER", "-bad", "bad--name", "bad-"])
def test_rejects_nonstandard_names(tmp_path: Path, name: str) -> None:
    root = tmp_path / name
    root.mkdir()
    (root / "SKILL.md").write_text(f"---\nname: {name}\ndescription: valid description\n---\nbody", encoding="utf-8")
    with pytest.raises(SkillSpecificationError):
        parse_skill(root)


def test_rejects_unknown_frontmatter_and_confines_resources(tmp_path: Path) -> None:
    root = tmp_path / "valid"
    root.mkdir()
    (root / "SKILL.md").write_text("---\nname: valid\ndescription: fine\nagent: extra\n---\nbody", encoding="utf-8")
    with pytest.raises(SkillSpecificationError, match="unsupported"):
        parse_skill(root)
    (root / "SKILL.md").write_text("---\nname: valid\ndescription: fine\n---\nbody", encoding="utf-8")
    outside = tmp_path / "secret"
    outside.write_text("no", encoding="utf-8")
    with pytest.raises(SkillSpecificationError, match="escapes"):
        confined_skill_resource(root, "../secret")
