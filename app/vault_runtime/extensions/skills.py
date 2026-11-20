"""Agent Skills parser adapted from R1 skills/specification.py (SHA in Phase 5 inventory).

New imports follow the pinned upstream reference validator (agentskills/agentskills
83021e2, skills-ref ``validator.py``) for ``name``, ``description`` and
``compatibility``. Installed records that only loaded through the old directory-name
fallback are read with ``allow_legacy=True`` and come back marked ``legacy``.

This module depends only on the standard library and PyYAML: the Plugin Kit loads
the same file to validate skills without a running Vault.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata

import yaml


_LEGACY_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_SKILL_BYTES = 512 * 1024
MAX_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
MAX_COMPATIBILITY_LENGTH = 500
_FIELDS = frozenset({"name", "description", "license", "compatibility", "metadata", "allowed-tools"})


class SkillSpecificationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SkillDocument:
    name: str
    description: str
    instructions: str
    license: str | None
    compatibility: str | None
    metadata: dict[str, str]
    allowed_tools: str | None
    # True only when an installed record needed the pre-standard reader (allow_legacy).
    legacy: bool = False


def parse_skill(root: Path, *, allow_legacy: bool = False) -> SkillDocument:
    skill_root = root.resolve(strict=True)
    source = skill_root / "SKILL.md"
    if not source.is_file():
        raise SkillSpecificationError("SKILL.md is required")
    if not source.resolve().is_relative_to(skill_root):
        raise SkillSpecificationError("SKILL.md escapes its Skill root")
    return parse_skill_document(source, expected_directory=skill_root.name, allow_legacy=allow_legacy)


def parse_skill_document(
    source: Path, *, expected_directory: str | None = None, allow_legacy: bool = False,
) -> SkillDocument:
    """Strict parse; ``allow_legacy`` is for already-installed records only, never imports."""
    normalized = _read(source)
    try:
        return _parse_strict(normalized, expected_directory)
    except SkillSpecificationError:
        if not allow_legacy:
            raise
        try:
            document = _parse_legacy(normalized, expected_directory)
        except SkillSpecificationError:
            pass
        else:
            return document
        raise


def confined_skill_resource(root: Path, relative_path: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise SkillSpecificationError("Skill resource path is invalid")
    base = root.resolve(strict=True)
    target = (base / relative_path).resolve(strict=True)
    if not target.is_relative_to(base) or not target.is_file():
        raise SkillSpecificationError("Skill resource escapes its Skill root")
    return target


def _read(source: Path) -> str:
    skill_source = source.resolve(strict=True)
    if skill_source.stat().st_size > MAX_SKILL_BYTES:
        raise SkillSpecificationError("SKILL.md exceeds the size limit")
    try:
        raw = skill_source.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise SkillSpecificationError("SKILL.md must be UTF-8") from exc
    return raw.replace("\r\n", "\n").replace("\r", "\n")


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that rejects a repeated key in any mapping (PyYAML keeps the last one)."""


def _unique_mapping(loader: _UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False):
    seen: set[object] = set()
    for key_node, _value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            repeated = key in seen
        except TypeError:
            continue  # Unhashable keys fail later in SafeLoader with its own error.
        if repeated:
            raise SkillSpecificationError(f"SKILL.md frontmatter repeats the key '{key}'")
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def _parse_strict(normalized: str, directory: str | None) -> SkillDocument:
    frontmatter, instructions = _split_frontmatter(normalized)
    try:
        parsed = yaml.load(frontmatter, Loader=_UniqueKeyLoader)  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError as exc:
        raise SkillSpecificationError("SKILL.md frontmatter is invalid YAML") from exc
    if not isinstance(parsed, dict):
        raise SkillSpecificationError("SKILL.md frontmatter must be an object")
    _known_fields(parsed)
    if "name" not in parsed:
        raise SkillSpecificationError("SKILL.md frontmatter requires a name")
    if "description" not in parsed:
        raise SkillSpecificationError("description is required")
    return SkillDocument(
        name=_name(parsed["name"], directory),
        description=_description(parsed["description"]),
        instructions=instructions,
        license=_optional(parsed.get("license"), "license"),
        compatibility=_compatibility(parsed.get("compatibility")),
        metadata=_metadata(parsed.get("metadata")),
        allowed_tools=_optional(parsed.get("allowed-tools"), "allowed-tools"),
    )


def _known_fields(parsed: dict) -> None:
    unknown = set(parsed) - _FIELDS
    if unknown:
        raise SkillSpecificationError(
            "SKILL.md contains unsupported frontmatter fields: "
            + ", ".join(sorted(str(item) for item in unknown))
        )


def _split_frontmatter(raw: str) -> tuple[str, str]:
    lines = raw.split("\n")
    if lines[0] != "---":
        raise SkillSpecificationError("SKILL.md must begin with YAML frontmatter")
    for index in range(1, len(lines)):
        if lines[index] == "---":
            # A closing line at end of file (no trailing newline) is valid: empty body.
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1:])
    raise SkillSpecificationError("SKILL.md frontmatter is not closed")


def _name(value: object, directory: str | None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SkillSpecificationError("name must be a non-empty string")
    name = unicodedata.normalize("NFKC", value.strip())
    if len(name) > MAX_NAME_LENGTH:
        raise SkillSpecificationError(f"name exceeds {MAX_NAME_LENGTH} characters")
    if name != name.lower():
        raise SkillSpecificationError("name must be lowercase")
    if name.startswith("-") or name.endswith("-"):
        raise SkillSpecificationError("name cannot start or end with a hyphen")
    if "--" in name:
        raise SkillSpecificationError("name cannot contain consecutive hyphens")
    if not all(character.isalnum() or character == "-" for character in name):
        raise SkillSpecificationError("name may contain only letters, digits and hyphens")
    if directory is not None and unicodedata.normalize("NFKC", directory) != name:
        raise SkillSpecificationError(f"name '{name}' must match the Skill directory '{directory}'")
    return name


def _description(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SkillSpecificationError("description is required")
    if len(value) > MAX_DESCRIPTION_LENGTH:  # The reference measures the raw value.
        raise SkillSpecificationError(f"description exceeds {MAX_DESCRIPTION_LENGTH} characters")
    return value.strip()


def _compatibility(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SkillSpecificationError("compatibility must be a string")
    if len(value) > MAX_COMPATIBILITY_LENGTH:
        raise SkillSpecificationError(f"compatibility exceeds {MAX_COMPATIBILITY_LENGTH} characters")
    return value.strip() or None


def _optional(value: object, field: str, maximum: int | None = None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SkillSpecificationError(f"{field} must be a non-empty string")
    result = value.strip()
    if maximum is not None and len(result) > maximum:
        raise SkillSpecificationError(f"{field} exceeds {maximum} characters")
    return result


def _metadata(value: object) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict) or any(
        not isinstance(key, str) or not isinstance(item, str) for key, item in value.items()
    ):
        raise SkillSpecificationError("metadata must map strings to strings")
    return dict(value)


# Legacy reader: the exact pre-standard rules, kept separate so installed records keep
# loading. It must never be reached from an import path.

def _parse_legacy(normalized: str, directory: str | None) -> SkillDocument:
    if not normalized.startswith("---\n"):
        raise SkillSpecificationError("SKILL.md must begin with YAML frontmatter")
    end = normalized.find("\n---\n", 4)
    if end < 0:
        raise SkillSpecificationError("SKILL.md frontmatter is not closed")
    frontmatter, instructions = normalized[4:end], normalized[end + 5:]
    try:
        parsed = yaml.safe_load(frontmatter)
    except yaml.YAMLError as exc:
        raise SkillSpecificationError("SKILL.md frontmatter is invalid YAML") from exc
    if not isinstance(parsed, dict):
        raise SkillSpecificationError("SKILL.md frontmatter must be an object")
    _known_fields(parsed)
    return SkillDocument(
        name=_legacy_name(parsed.get("name"), directory),
        description=_legacy_bounded(parsed.get("description"), "description", 1024),
        instructions=instructions,
        license=_optional(parsed.get("license"), "license"),
        compatibility=_optional(parsed.get("compatibility"), "compatibility", 500),
        metadata=_metadata(parsed.get("metadata")),
        allowed_tools=_optional(parsed.get("allowed-tools"), "allowed-tools"),
        legacy=True,
    )


def _legacy_name(value: object, directory: str | None) -> str:
    if isinstance(value, str) and _LEGACY_NAME.fullmatch(value) and len(value) <= 64:
        if directory is not None and value != directory:
            raise SkillSpecificationError("name must match the Skill directory")
        return value
    if directory is not None and _LEGACY_NAME.fullmatch(directory) and len(directory) <= 64:
        return directory
    raise SkillSpecificationError("name must be 1-64 lowercase letters, digits, or hyphens")


def _legacy_bounded(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SkillSpecificationError(f"{field} is required")
    result = value.strip()
    if len(result) > maximum:
        raise SkillSpecificationError(f"{field} exceeds {maximum} characters")
    return result
