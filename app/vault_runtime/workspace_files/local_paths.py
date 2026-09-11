from __future__ import annotations

from dataclasses import dataclass

from app.vault_runtime.workspace_paths import normalize_workspace_file_prefix


LOCAL_FILES_ROOT = "local"


@dataclass(frozen=True, slots=True)
class ParsedLocalViewPath:
    mount_name: str
    remainder: str


def is_local_view_path(path: str | None) -> bool:
    normalized = normalize_workspace_file_prefix(path)
    if not normalized:
        return False
    return normalized == LOCAL_FILES_ROOT or normalized.startswith(f"{LOCAL_FILES_ROOT}/")


def parse_local_view_path(path: str | None) -> ParsedLocalViewPath | None:
    normalized = normalize_workspace_file_prefix(path)
    if not is_local_view_path(normalized):
        return None
    if normalized == LOCAL_FILES_ROOT:
        return ParsedLocalViewPath(mount_name="", remainder="")
    segments = normalized.split("/", 2)
    if len(segments) < 2 or segments[0] != LOCAL_FILES_ROOT:
        return None
    mount_name = segments[1]
    remainder = segments[2] if len(segments) > 2 else ""
    return ParsedLocalViewPath(mount_name=mount_name, remainder=remainder)


def build_local_mount_path(*, mount_name: str) -> str:
    return f"{LOCAL_FILES_ROOT}/{mount_name}".strip("/")


def join_local_view_path(prefix: str, relative: str) -> str:
    normalized_prefix = normalize_workspace_file_prefix(prefix)
    normalized_relative = normalize_workspace_file_prefix(relative)
    if not normalized_relative:
        return normalized_prefix
    return f"{normalized_prefix}/{normalized_relative}"
