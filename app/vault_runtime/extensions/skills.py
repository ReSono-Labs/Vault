"""Agent Skills parser adapted from R1 skills/specification.py (SHA in Phase 5 inventory)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import yaml


_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_SKILL_BYTES = 512 * 1024


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


def parse_skill(root: Path) -> SkillDocument:
    skill_root = root.resolve(strict=True)
    source = skill_root / "SKILL.md"
    if not source.is_file():
        raise SkillSpecificationError("SKILL.md is required")
    if not source.resolve().is_relative_to(skill_root):
        raise SkillSpecificationError("SKILL.md escapes its Skill root")
    return parse_skill_document(source, expected_directory=skill_root.name)


def parse_skill_document(source: Path, *, expected_directory: str | None = None) -> SkillDocument:
    skill_source = source.resolve(strict=True)
    if skill_source.stat().st_size > MAX_SKILL_BYTES:
        raise SkillSpecificationError("SKILL.md exceeds the size limit")
    try:
        raw = skill_source.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise SkillSpecificationError("SKILL.md must be UTF-8") from exc
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    frontmatter, instructions = _split_frontmatter(normalized)
    try:
        parsed = yaml.safe_load(frontmatter)
    except yaml.YAMLError as exc:
        raise SkillSpecificationError("SKILL.md frontmatter is invalid YAML") from exc
    if not isinstance(parsed, dict):
        raise SkillSpecificationError("SKILL.md frontmatter must be an object")
    unknown = set(parsed) - {
        "name", "description", "license", "compatibility", "metadata", "allowed-tools"
    }
    if unknown:
        raise SkillSpecificationError("SKILL.md contains unsupported frontmatter fields")
    return SkillDocument(
        name=_name(parsed.get("name"), expected_directory),
        description=_bounded(parsed.get("description"), "description", 1024),
        instructions=instructions,
        license=_optional(parsed.get("license"), "license"),
        compatibility=_optional(parsed.get("compatibility"), "compatibility", 500),
        metadata=_metadata(parsed.get("metadata")),
        allowed_tools=_optional(parsed.get("allowed-tools"), "allowed-tools"),
    )


def confined_skill_resource(root: Path, relative_path: str) -> Path:
    if not relative_path or Path(relative_path).is_absolute():
        raise SkillSpecificationError("Skill resource path is invalid")
    base = root.resolve(strict=True)
    target = (base / relative_path).resolve(strict=True)
    if not target.is_relative_to(base) or not target.is_file():
        raise SkillSpecificationError("Skill resource escapes its Skill root")
    return target


def _split_frontmatter(raw: str) -> tuple[str, str]:
    if not raw.startswith("---\n"):
        raise SkillSpecificationError("SKILL.md must begin with YAML frontmatter")
    end = raw.find("\n---\n", 4)
    if end < 0:
        raise SkillSpecificationError("SKILL.md frontmatter is not closed")
    return raw[4:end], raw[end + 5:]


def _name(value: object, directory: str | None) -> str:
    if isinstance(value, str) and _NAME.fullmatch(value) and len(value) <= 64:
        if directory is not None and value != directory:
            raise SkillSpecificationError("name must match the Skill directory")
        return value
    if directory is not None and _NAME.fullmatch(directory) and len(directory) <= 64:
        return directory
    raise SkillSpecificationError("name must be 1-64 lowercase letters, digits, or hyphens")


def _bounded(value: object, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SkillSpecificationError(f"{field} is required")
    result = value.strip()
    if len(result) > maximum:
        raise SkillSpecificationError(f"{field} exceeds {maximum} characters")
    return result


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
