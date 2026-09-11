from __future__ import annotations

from pathlib import Path, PurePosixPath


class UnsafeWorkspacePathError(ValueError):
    pass


def normalize_workspace_file_prefix(prefix: str | None) -> str:
    if prefix is None or not str(prefix).strip().strip("/"):
        return ""
    return normalize_workspace_file_key(str(prefix), require_extension=False)


def normalize_workspace_file_key(file_key: str, *, require_extension: bool = False) -> str:
    original = str(file_key or "").strip().replace("\\", "/")
    if original.startswith("/") or original.startswith("~"):
        raise UnsafeWorkspacePathError("Workspace file key must be relative.")
    raw = original.strip("/")
    if not raw:
        raise UnsafeWorkspacePathError("Workspace file key is required.")
    path = PurePosixPath(raw)
    parts = path.parts
    if any(part in {"", ".", ".."} for part in parts):
        raise UnsafeWorkspacePathError("Workspace file key contains an unsafe path segment.")
    normalized = path.as_posix()
    if normalized != raw:
        raise UnsafeWorkspacePathError("Workspace file key is not normalized.")
    if require_extension and "." not in parts[-1]:
        raise UnsafeWorkspacePathError("Workspace file key must include a filename extension.")
    return normalized


def resolve_workspace_staging_path(*, workspace_root: Path, file_key: str) -> Path:
    """Resolve a staging path after membership authorization has succeeded."""
    normalized = normalize_workspace_file_key(file_key)
    root = workspace_root.absolute()
    if root.is_symlink():
        raise UnsafeWorkspacePathError("Workspace root cannot be a symbolic link.")
    candidate = root.joinpath(*PurePosixPath(normalized).parts)
    current = root
    for part in PurePosixPath(normalized).parts:
        current = current / part
        if current.is_symlink():
            raise UnsafeWorkspacePathError("Workspace path cannot contain symbolic links.")
    resolved_root = root.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    if not resolved_candidate.is_relative_to(resolved_root):
        raise UnsafeWorkspacePathError("Workspace path escapes its authorized root.")
    return resolved_candidate
