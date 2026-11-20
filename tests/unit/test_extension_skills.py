from pathlib import Path

import pytest

from app.vault_runtime.extensions.skills import (
    SkillSpecificationError, confined_skill_resource, parse_skill, parse_skill_document,
)


def _skill(tmp_path: Path, directory: str, text: str) -> Path:
    root = tmp_path / directory
    root.mkdir()
    (root / "SKILL.md").write_bytes(text.encode("utf-8"))
    return root


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


# Strict rules (new imports): skills-ref 83021e2 validator.py for name, description, compatibility.

@pytest.mark.parametrize(("frontmatter", "message"), [
    ("description: valid description\n", "requires a name"),
    ("name: ''\ndescription: valid description\n", "non-empty string"),
    ("name: 123\ndescription: valid description\n", "non-empty string"),
    ("name: Not_Valid\ndescription: valid description\n", "lowercase"),
])
def test_malformed_names_in_a_valid_directory_no_longer_fall_back(
    tmp_path: Path, frontmatter: str, message: str,
) -> None:
    root = _skill(tmp_path, "valid", f"---\n{frontmatter}---\nbody")
    with pytest.raises(SkillSpecificationError, match=message):
        parse_skill(root)


def test_name_must_match_its_directory(tmp_path: Path) -> None:
    root = _skill(tmp_path, "valid", "---\nname: other\ndescription: fine\n---\nbody")
    with pytest.raises(SkillSpecificationError, match="name 'other' must match the Skill directory 'valid'"):
        parse_skill(root)


def test_unicode_names_follow_the_reference_validator(tmp_path: Path) -> None:
    assert parse_skill(_skill(tmp_path, "café", "---\nname: café\ndescription: fine\n---\n")).name == "café"
    # NFKC: fullwidth letters in the frontmatter equal the ASCII directory by normalization.
    assert parse_skill(_skill(tmp_path, "abc", "---\nname: ａｂｃ\ndescription: fine\n---\n")).name == "abc"
    with pytest.raises(SkillSpecificationError, match="64"):
        parse_skill(_skill(tmp_path, "a" * 65, f"---\nname: {'a' * 65}\ndescription: fine\n---\n"))
    with pytest.raises(SkillSpecificationError, match="only letters, digits and hyphens"):
        parse_skill(_skill(tmp_path, "a_b", "---\nname: a_b\ndescription: fine\n---\n"))


def test_description_and_compatibility_follow_the_reference_validator(tmp_path: Path) -> None:
    padded = " " * 3 + "d" * 1024
    with pytest.raises(SkillSpecificationError, match="description exceeds 1024"):
        parse_skill(_skill(tmp_path, "padded", f"---\nname: padded\ndescription: '{padded}'\n---\n"))
    document = parse_skill(_skill(tmp_path, "compat", "---\nname: compat\ndescription: fine\ncompatibility: ''\n---\n"))
    assert document.compatibility is None
    with pytest.raises(SkillSpecificationError, match="compatibility must be a string"):
        parse_skill(_skill(tmp_path, "typed", "---\nname: typed\ndescription: fine\ncompatibility: 3\n---\n"))
    with pytest.raises(SkillSpecificationError, match="compatibility exceeds 500"):
        parse_skill(_skill(tmp_path, "long", f"---\nname: long\ndescription: fine\ncompatibility: {'c' * 501}\n---\n"))


@pytest.mark.parametrize("frontmatter", [
    "name: valid\nname: valid\ndescription: fine\n",
    "name: valid\ndescription: shown\ndescription: hidden\n",
    "name: valid\ndescription: fine\nmetadata:\n  a: one\n  a: two\n",
])
def test_rejects_repeated_frontmatter_keys(tmp_path: Path, frontmatter: str) -> None:
    root = _skill(tmp_path, "valid", f"---\n{frontmatter}---\nbody")
    with pytest.raises(SkillSpecificationError, match="repeats the key"):
        parse_skill(root)


@pytest.mark.parametrize("text", [
    "---\nname: valid\ndescription: fine\n---",
    "---\r\nname: valid\r\ndescription: fine\r\n---",
])
def test_accepts_closing_line_at_end_of_file(tmp_path: Path, text: str) -> None:
    document = parse_skill(_skill(tmp_path, "valid", text))
    assert (document.name, document.instructions, document.legacy) == ("valid", "", False)


def test_crlf_body_is_normalized(tmp_path: Path) -> None:
    document = parse_skill(_skill(tmp_path, "valid", "---\r\nname: valid\r\ndescription: fine\r\n---\r\nOne\r\nTwo\r\n"))
    assert document.instructions == "One\nTwo\n"


def test_one_bad_skill_does_not_affect_a_healthy_sibling(tmp_path: Path) -> None:
    healthy = _skill(tmp_path, "healthy", "---\nname: healthy\ndescription: fine\n---\nok")
    broken = _skill(tmp_path, "broken", "---\ndescription: no name\n---\nno")
    with pytest.raises(SkillSpecificationError):
        parse_skill(broken)
    assert parse_skill(healthy).name == "healthy"


# Legacy rules (installed records only): kept separate from the strict set above.

def test_installed_record_that_needed_the_fallback_still_loads_marked_legacy(tmp_path: Path) -> None:
    # Installed skills live at skills/<identity>/current; the identity was the folder name.
    current = tmp_path / "skills" / "notes" / "current"
    current.mkdir(parents=True)
    source = current / "SKILL.md"
    source.write_text("---\ndescription: Old install without a name.\nmetadata:\n  k: a\n  k: b\n---\nOld body\n", encoding="utf-8")
    with pytest.raises(SkillSpecificationError):
        parse_skill_document(source, expected_directory="notes")
    document = parse_skill_document(source, expected_directory="notes", allow_legacy=True)
    assert (document.name, document.instructions, document.legacy) == ("notes", "Old body\n", True)
    source.write_text("---\nname: notes\ndescription: Standard install.\n---\nBody\n", encoding="utf-8")
    assert parse_skill_document(source, expected_directory="notes", allow_legacy=True).legacy is False
    source.write_text("---\nname: notes\n---\nNo description is still rejected.\n", encoding="utf-8")
    with pytest.raises(SkillSpecificationError, match="description"):
        parse_skill_document(source, expected_directory="notes", allow_legacy=True)
