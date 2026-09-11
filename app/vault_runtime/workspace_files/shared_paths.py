from __future__ import annotations

from dataclasses import dataclass

from app.vault_runtime.workspace_paths import normalize_workspace_file_prefix


SHARED_FILES_ROOT = "shared"


@dataclass(frozen=True, slots=True)
class ParsedSharedViewPath:
    owner_username: str
    remainder: str


def is_shared_view_path(path: str | None) -> bool:
    normalized = normalize_workspace_file_prefix(path)
    if not normalized:
        return False
    return normalized == SHARED_FILES_ROOT or normalized.startswith(f"{SHARED_FILES_ROOT}/")


def parse_shared_view_path(path: str | None) -> ParsedSharedViewPath | None:
    normalized = normalize_workspace_file_prefix(path)
    if not is_shared_view_path(normalized):
        return None
    if normalized == SHARED_FILES_ROOT:
        return ParsedSharedViewPath(owner_username="", remainder="")
    segments = normalized.split("/", 2)
    if len(segments) < 2 or segments[0] != SHARED_FILES_ROOT:
        return None
    owner_username = segments[1]
    remainder = segments[2] if len(segments) > 2 else ""
    return ParsedSharedViewPath(owner_username=owner_username, remainder=remainder)


def build_shared_mount_path(*, owner_username: str, mount_name: str) -> str:
    return f"{SHARED_FILES_ROOT}/{owner_username}/{mount_name}".strip("/")


def shared_owner_directory(*, owner_username: str) -> str:
    return f"{SHARED_FILES_ROOT}/{owner_username}"


def join_shared_view_path(prefix: str, relative: str) -> str:
    normalized_prefix = normalize_workspace_file_prefix(prefix)
    normalized_relative = normalize_workspace_file_prefix(relative)
    if not normalized_relative:
        return normalized_prefix
    return f"{normalized_prefix}/{normalized_relative}"
