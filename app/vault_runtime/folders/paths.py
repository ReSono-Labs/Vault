"""Path rules for host folders.

Every check starts again from a trusted root, so a directory replaced by a
symlink after it was added is refused on the next request.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from app.vault_runtime.folders.errors import FolderHiddenPathError, FolderOutsideAccessError
from app.vault_runtime.workspace_paths import (
    UnsafeWorkspacePathError,
    normalize_workspace_file_prefix,
    resolve_workspace_staging_path,
)


def normalize_relative(path: str | None, *, allow_hidden: bool = False) -> str:
    """Normalize a relative path. '' means the root itself.

    Hidden segments (names starting with ".") are refused unless hidden files were
    switched on for the folder the path is inside.
    """
    try:
        normalized = normalize_workspace_file_prefix(path)
    except (UnsafeWorkspacePathError, ValueError) as exc:
        raise FolderOutsideAccessError("That path is outside this folder.") from exc
    if not allow_hidden and any(part.startswith(".") for part in PurePosixPath(normalized).parts):
        raise FolderHiddenPathError("Hidden files and folders can't be used.")
    return normalized


def resolve_inside(root: Path, relative: str | None, *, allow_hidden: bool = False) -> Path:
    """Resolve relative under root, refusing traversal, symlinks and (unless allowed) hidden segments."""
    normalized = normalize_relative(relative, allow_hidden=allow_hidden)
    if root.is_symlink():
        raise FolderOutsideAccessError("That path is outside this folder.")
    if not normalized:
        return root
    try:
        return resolve_workspace_staging_path(workspace_root=root, file_key=normalized)
    except (UnsafeWorkspacePathError, ValueError) as exc:
        raise FolderOutsideAccessError("That path is outside this folder.") from exc


def join_relative(*parts: str) -> str:
    return "/".join(part.strip("/") for part in parts if part and part.strip("/"))


def last_segment(relative: str) -> str:
    return PurePosixPath(relative).name if relative else ""
