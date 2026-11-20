"""Read-only discovery tools: glob, tree, line-range reads, several files at once, file info, copy.

Folders on the computer (local/{name}) use ripgrep; Vault's own files use the normal listing.
Every call is bounded by time and result count, smaller for Voice (it answers out loud).
"""

from __future__ import annotations

import fnmatch
import os
import shutil
import time
from collections import deque
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from app.vault_runtime.folders.errors import FolderExistsError, FolderInvalidRequestError
from app.vault_runtime.folders.paths import resolve_inside
from app.vault_runtime.folders.search import SKIP_DIRECTORIES, glob_folder, ripgrep
from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.workspace_files.errors import WorkspaceFileError
from app.vault_runtime.workspace_files.local_paths import join_local_view_path, parse_local_view_path
from app.vault_runtime.workspace_files.manager import WorkspaceFileUpload
from app.vault_runtime.workspace_files.path_areas import classify_workspace_path_area
from app.vault_runtime.workspace_paths import normalize_workspace_file_prefix


@dataclass(frozen=True, slots=True)
class Budget:
    seconds: float
    results: int

    @staticmethod
    def for_agent(voice: bool) -> "Budget":
        return Budget(1.5, 50) if voice else Budget(5.0, 500)


def _is_local_folder(path: str) -> bool:
    parsed = parse_local_view_path(path)
    return parsed is not None and bool(parsed.mount_name)


class WorkspaceDiscovery:
    def __init__(self, files: Any) -> None:
        self._files = files  # WorkspaceFileService
        self._local = files._local  # LocalFilesystemBridge

    # glob

    def glob(self, *, principal: LocalPrincipal, pattern: str, directory: str | None, budget: Budget,
             share_id: str | None = None) -> dict[str, Any]:
        pattern = str(pattern or "").strip()
        if not pattern or pattern.startswith("/") or ".." in pattern.split("/") or len(pattern) > 200:
            raise FolderInvalidRequestError("Use a relative pattern like **/*.md or docs/*.pdf.")
        root = normalize_workspace_file_prefix(directory)
        deadline = time.monotonic() + budget.seconds
        matches: list[str] = []
        truncated = False
        if _is_local_folder(root) and ripgrep():
            access = self._local._resolve(principal=principal, view_path=root)
            base = resolve_inside(access.root, access.relative_path, allow_hidden=access.include_hidden)
            result = glob_folder(base=base, pattern=pattern, include_hidden=access.include_hidden,
                                 limit=budget.results, deadline=deadline, executable=ripgrep())
            prefix = join_local_view_path(access.view_root, access.relative_path)
            matches = [join_local_view_path(prefix, hit.relative_path) for hit in result.hits]
            truncated = result.truncated
        else:
            for entry, relative in self._walk(principal, root, deadline, share_id):
                if entry is None:
                    truncated = True
                    break
                if entry.kind == "file" and _glob_match(relative, pattern):
                    matches.append(entry.path)
                    if len(matches) >= budget.results:
                        truncated = True
                        break
        return {"pattern": pattern, "directory": root, "pathArea": classify_workspace_path_area(root),
                "matches": matches, "matchCount": len(matches), "truncated": truncated,
                **({"note": "Stopped early. Use a more specific directory or pattern."} if truncated else {})}

    # tree

    def tree(self, *, principal: LocalPrincipal, directory: str | None, depth: int, budget: Budget,
             share_id: str | None = None) -> dict[str, Any]:
        depth = max(1, min(int(depth or 2), 5))
        root = normalize_workspace_file_prefix(directory)
        deadline = time.monotonic() + budget.seconds
        count = 0
        truncated = False

        def build(path: str, level: int) -> list[dict[str, Any]]:
            nonlocal count, truncated
            if truncated:
                return []
            if time.monotonic() > deadline or count >= budget.results:
                truncated = True
                return []
            try:
                listing = self._files.list_directory(principal=principal, directory=path or None,
                                                     share_id=share_id, for_agent=True)
            except WorkspaceFileError:
                return []
            nodes = []
            for entry in listing.entries:
                if count >= budget.results:
                    truncated = True
                    break
                count += 1
                node: dict[str, Any] = {"name": entry.name, "path": entry.path, "kind": entry.kind}
                if entry.kind == "file" and entry.sizeBytes is not None:
                    node["sizeBytes"] = entry.sizeBytes
                if entry.kind == "directory":
                    if entry.name.casefold() in SKIP_DIRECTORIES:
                        node["skipped"] = "dependency or build folder"
                    elif level < depth:
                        node["children"] = build(entry.path, level + 1)
                nodes.append(node)
            return nodes

        return {"directory": root, "depth": depth, "pathArea": classify_workspace_path_area(root),
                "tree": build(root, 1), "entryCount": count, "truncated": truncated,
                **({"note": "Stopped early. Lower the depth or pick a deeper directory."} if truncated else {})}

    # read with line ranges

    def read_lines(self, *, principal: LocalPrincipal, file_key: str, start_line: int | None, end_line: int | None,
                   head: int | None, tail: int | None, share_id: str | None = None, max_chars: int = 60_000,
                   ) -> dict[str, Any]:
        read = self._files.read_file(principal=principal, file_key=file_key, share_id=share_id, for_agent=True)
        payload = read.to_dict()
        text = read.contentMarkdown or ""
        lines = text.splitlines()
        total = len(lines)
        if head is not None and tail is not None:
            raise FolderInvalidRequestError("Use head or tail, not both.")
        selected: list[str] | None = None
        first = 1
        if head is not None:
            selected = lines[: max(0, head)]
        elif tail is not None:
            selected = lines[max(0, total - max(0, tail)):] if tail else []
            first = max(1, total - len(selected) + 1)
        elif start_line is not None or end_line is not None:
            first = max(1, int(start_line or 1))
            last = min(total, int(end_line or total))
            selected = lines[first - 1:last] if last >= first else []
        if selected is not None:
            payload["contentMarkdown"] = "\n".join(selected)
            payload["startLine"] = first if selected else None
            payload["endLine"] = first + len(selected) - 1 if selected else None
        payload["totalLines"] = total
        if len(payload["contentMarkdown"]) > max_chars:
            shown = payload["contentMarkdown"][:max_chars]
            payload["contentMarkdown"] = shown
            payload["truncated"] = True
            payload["note"] = (f"Showing the first {shown.count(chr(10)) + 1} lines of the selection. "
                               "Read more with startLine/endLine.")
        return payload

    def read_many(self, *, principal: LocalPrincipal, file_keys: list[str], share_id: str | None = None,
                  max_chars_each: int = 20_000) -> dict[str, Any]:
        if not file_keys or len(file_keys) > 10:
            raise FolderInvalidRequestError("Read between 1 and 10 files at a time.")
        results = []
        for key in file_keys:
            try:
                results.append(self.read_lines(principal=principal, file_key=key, start_line=None, end_line=None,
                                               head=None, tail=None, share_id=share_id, max_chars=max_chars_each))
            except WorkspaceFileError as exc:
                results.append({"fileKey": key, "error": str(exc), "code": exc.code})
        return {"files": results, "count": len(results)}

    # file info

    def info(self, *, principal: LocalPrincipal, path: str, share_id: str | None = None) -> dict[str, Any]:
        normalized = normalize_workspace_file_prefix(path)
        if not normalized:
            raise FolderInvalidRequestError("A path is required.")
        parent = str(PurePosixPath(normalized).parent)
        parent = "" if parent == "." else parent
        listing = self._files.list_directory(principal=principal, directory=parent or None,
                                             share_id=share_id, for_agent=True)
        entry = next((item for item in listing.entries if item.path.casefold() == normalized.casefold()), None)
        if entry is None:
            raise FolderInvalidRequestError("That path wasn't found.")
        payload = entry.to_dict()
        if entry.kind == "file" and (entry.sizeBytes or 0) <= 2_000_000:
            try:
                text = self._files.read_file(principal=principal, file_key=entry.path, share_id=share_id,
                                             for_agent=True).contentMarkdown
                if text:
                    payload["lineCount"] = text.count("\n") + (0 if text.endswith("\n") else 1)
            except WorkspaceFileError:
                pass
        payload["pathArea"] = classify_workspace_path_area(entry.path)
        return payload

    # copy

    def copy(self, *, principal: LocalPrincipal, source: str, destination: str,
             share_id: str | None = None) -> dict[str, Any]:
        source_key = normalize_workspace_file_prefix(source)
        destination_key = normalize_workspace_file_prefix(destination)
        if not source_key or not destination_key:
            raise FolderInvalidRequestError("Source and destination are required.")
        if _is_local_folder(source_key) and _is_local_folder(destination_key):
            src = self._local._resolve(principal=principal, view_path=source_key)
            dst = self._local._resolve(principal=principal, view_path=destination_key, write=True)
            if not src.relative_path or not dst.relative_path:
                raise FolderInvalidRequestError("Copy one file to a new file path inside a folder.")
            source_path = resolve_inside(src.root, src.relative_path, allow_hidden=src.include_hidden)
            destination_path = resolve_inside(dst.root, dst.relative_path, allow_hidden=dst.include_hidden)
            if not source_path.is_file() or source_path.is_symlink():
                raise FolderInvalidRequestError("Only single files can be copied.")
            if os.path.lexists(destination_path):
                raise FolderExistsError("Something already exists at the destination.")
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            resolve_inside(dst.root, dst.relative_path, allow_hidden=dst.include_hidden)
            shutil.copy2(source_path, destination_path, follow_symlinks=False)
        else:
            filename, mime, content = self._files.read_file_bytes(principal=principal, file_key=source_key,
                                                                  share_id=share_id)
            parent = str(PurePosixPath(destination_key).parent)
            name = PurePosixPath(destination_key).name or filename
            try:
                self._files.read_file(principal=principal, file_key=destination_key, share_id=share_id)
                raise FolderExistsError("Something already exists at the destination.")
            except WorkspaceFileError as exc:
                if isinstance(exc, FolderExistsError):
                    raise
            self._files.upload_files(principal=principal, directory=None if parent == "." else parent,
                                     uploads=[WorkspaceFileUpload(filename=name, content=content, mime_type=mime)],
                                     share_id=share_id)
        return {"status": "completed", "message": "File copied.", "path": source_key, "destinationPath": destination_key}

    # helpers

    def _walk(self, principal: LocalPrincipal, root: str, deadline: float, share_id: str | None):
        queue = deque([root])
        visited: set[str] = set()
        while queue:
            if time.monotonic() > deadline or len(visited) > 2_000:
                yield None, ""
                return
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            try:
                listing = self._files.list_directory(principal=principal, directory=current or None,
                                                     share_id=share_id, for_agent=True)
            except WorkspaceFileError:
                continue
            for entry in listing.entries:
                relative = entry.path[len(root) + 1:] if root and entry.path.startswith(root + "/") else entry.path
                if entry.kind == "directory":
                    if entry.name.casefold() not in SKIP_DIRECTORIES:
                        queue.append(entry.path)
                yield entry, relative


def _glob_match(relative: str, pattern: str) -> bool:
    """**/x matches at any depth; other patterns match the whole relative path."""
    if fnmatch.fnmatchcase(relative, pattern):
        return True
    if pattern.startswith("**/"):
        return _glob_match(relative, pattern[3:]) or any(
            fnmatch.fnmatchcase("/".join(relative.split("/")[i:]), pattern[3:])
            for i in range(1, relative.count("/") + 1)
        )
    return False
