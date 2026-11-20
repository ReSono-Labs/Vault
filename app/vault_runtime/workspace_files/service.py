from __future__ import annotations

import mimetypes
import re
import time
from collections import deque
from dataclasses import replace
from typing import Any

from app.vault_runtime.folders.search import SearchOptions, name_matches, name_words
from app.vault_runtime.folders.service import FolderService
from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.workspace_files.manager import WorkspaceFileManagerService, WorkspaceFileUpload
from app.vault_runtime.workspace_files.models import (
    WorkspaceFileDirectory,
    WorkspaceFileEntry,
    WorkspaceFileMutation,
    WorkspaceFileRead,
    WorkspaceFolderShareView,
)
from app.vault_runtime.workspace_files.repository import WorkspaceFileRepository, WorkspaceFolderShare, share_mount_name_for_path
from app.vault_runtime.workspace_files.local_operations import LocalFilesystemBridge
from app.vault_runtime.workspace_files.errors import (
    WorkspaceFileError,
    WorkspaceFileBadRequestError,
    WorkspaceFileConflictError,
    WorkspaceFileNotFoundError,
)
from app.vault_runtime.workspace_files.path_areas import (
    annotate_directory_listing,
    build_agent_path_areas,
    agent_tool_catalog,
    classify_workspace_path_area,
)
from app.vault_runtime.workspace_files.local_paths import (
    LOCAL_FILES_ROOT,
    is_local_view_path,
    parse_local_view_path,
)
from app.vault_runtime.workspace_files.shared_paths import (
    SHARED_FILES_ROOT,
    build_shared_mount_path,
    is_shared_view_path,
    join_shared_view_path,
    parse_shared_view_path,
    shared_owner_directory,
)
from app.vault_runtime.workspace_files.access import WorkspaceAccess, WorkspaceAccessResolver
from app.vault_runtime.workspace_files.store import WorkspaceFilesystemStore
from app.vault_runtime.workspace_paths import normalize_workspace_file_prefix
from app.vault_runtime.workspace_storage import WorkspaceStorage


_SEARCH_TIME_BUDGET_SECONDS = 5.0
_SEARCH_MAX_DIRECTORIES = 2_000
_SEARCH_MAX_FILE_READS = 300
_SEARCH_MAX_FILE_BYTES = 512_000
# Dependency and build folders: still matched by name, never walked into.
_SEARCH_SKIP_DIRECTORIES = frozenset({
    "node_modules", "__pycache__", "site-packages", "venv", ".venv", ".git", "target", "dist", "build",
})
_SEARCH_TEXT_TYPES = frozenset({
    "application/json", "application/xml", "application/yaml", "application/x-yaml",
    "application/javascript", "application/toml", "application/x-sh",
})


def _folder_hit_match(view_path: str, hit: Any) -> dict[str, Any]:
    mime = None if hit.kind == "directory" else (mimetypes.guess_type(view_path)[0] or "application/octet-stream")
    match = {
        "fileKey": view_path,
        "kind": hit.kind,
        "pathArea": classify_workspace_path_area(view_path),
        "mimeType": mime,
        "editable": None,
        "updatedAt": None,
        "snippet": hit.snippet,
    }
    if hit.line is not None:
        match["line"] = hit.line
    if hit.context:
        match["contextBefore"] = list(hit.context)
    return match


def _search_scope_allows(path: str, root: str, options: SearchOptions) -> bool:
    if not options.include and not options.exclude:
        return True
    from app.vault_runtime.workspace_files.discovery import _glob_match
    relative = path[len(root) + 1:] if root and path.startswith(root + "/") else path
    if options.include and not any(_glob_match(relative, item) for item in options.include):
        return False
    return not any(_glob_match(relative, item) for item in options.exclude)


def _searchable_text(entry: WorkspaceFileEntry) -> bool:
    if entry.sizeBytes is not None and entry.sizeBytes > _SEARCH_MAX_FILE_BYTES:
        return False
    mime = (entry.mimeType or "").split(";", 1)[0].lower()
    return mime.startswith("text/") or mime in _SEARCH_TEXT_TYPES


class WorkspaceFileService:
    def __init__(
        self,
        repository: WorkspaceFileRepository,
        storage: WorkspaceStorage,
        folders: FolderService | None = None,
    ) -> None:
        self._repository = repository
        self._store = WorkspaceFilesystemStore(storage)
        self._manager = WorkspaceFileManagerService(self._store)
        self._access = WorkspaceAccessResolver(repository=repository, store=self._store)
        self._folders = folders
        self._local = LocalFilesystemBridge(folders=folders)

    def workspace_root_info(
        self,
        *,
        principal: LocalPrincipal,
        share_id: str | None = None,
    ) -> dict[str, Any]:
        access = self._access.resolve(principal=principal, share_id=share_id)
        self._access.require_read(access)
        if access.virtual_shared:
            payload: dict[str, Any] = {
                "workspaceId": principal.workspace_id,
                "filesRoot": SHARED_FILES_ROOT,
                "pathStyle": "shared-view",
                "pathAreas": build_agent_path_areas(
                    shared_mounts=self._shared_mount_descriptors(principal=principal),
                    local_enabled=self._local.is_available(principal=principal),
                    local_mounts=self._local_mount_descriptors(principal=principal),
                ),
                "tools": agent_tool_catalog(),
            }
            return payload
        payload = dict(
            self._manager.workspace_root_info(
                actor=replace(principal, workspace_id=access.workspace_id),
            )
        )
        if access.share_id:
            payload["shareId"] = access.share_id
            payload["shareRoot"] = access.share_mount_path
            payload["permission"] = access.permission
            payload["pathStyle"] = "shared-view"
        payload["pathAreas"] = build_agent_path_areas(
            shared_mounts=self._shared_mount_descriptors(principal=principal),
            local_enabled=self._local.is_available(principal=principal),
            local_mounts=self._local_mount_descriptors(principal=principal),
        )
        payload["tools"] = agent_tool_catalog()
        return payload

    def list_directory(
        self,
        *,
        principal: LocalPrincipal,
        directory: str | None,
        share_id: str | None = None,
        for_agent: bool = False,
    ) -> WorkspaceFileDirectory:
        normalized_directory = normalize_workspace_file_prefix(directory)
        parsed_local = parse_local_view_path(normalized_directory)
        if parsed_local is not None:
            if not parsed_local.mount_name:
                return self._finalize_agent_listing(
                    self._local.list_root(principal=principal),
                    for_agent=for_agent,
                )
            return self._finalize_agent_listing(
                self._local.list_directory(principal=principal, view_path=normalized_directory),
                for_agent=for_agent,
            )

        parsed = parse_shared_view_path(normalized_directory)
        if parsed is not None:
            if not parsed.owner_username:
                return self._finalize_agent_listing(
                    self._list_shared_root(principal=principal),
                    for_agent=for_agent,
                )
            if not parsed.remainder:
                return self._finalize_agent_listing(
                    self._list_shared_owner(principal=principal, owner_username=parsed.owner_username),
                    for_agent=for_agent,
                )

        if not normalized_directory and share_id is None:
            return self._finalize_agent_listing(
                self._list_owner_workspace_root(principal=principal, for_agent=for_agent),
                for_agent=for_agent,
            )

        access = self._access.resolve(
            principal=principal,
            share_id=share_id,
            view_path=normalized_directory,
        )
        self._access.require_read(access)
        if access.virtual_shared:
            raise RuntimeError("Shared directory resolution failed.")

        actor = replace(principal, workspace_id=access.workspace_id)
        storage_directory = self._access.view_directory_to_storage(access=access, directory=normalized_directory or None)
        listing = self._manager.list_directory(
            actor=actor,
            directory=storage_directory or None,
            include_reserved=for_agent and not access.share_id,
        )
        entries = [self._remap_entry(access=access, entry=entry) for entry in listing.entries]
        parent = self._shared_parent_directory(normalized_directory) if access.share_id else listing.parentDirectory
        current = normalized_directory or access.share_mount_path
        return self._finalize_agent_listing(
            WorkspaceFileDirectory(
                currentDirectory=current,
                parentDirectory=parent,
                entries=entries,
                shareId=access.share_id,
                permission=access.permission,
            ),
            for_agent=for_agent,
        )

    def read_file(
        self,
        *,
        principal: LocalPrincipal,
        file_key: str,
        share_id: str | None = None,
        for_agent: bool = False,
    ) -> WorkspaceFileRead:
        if is_local_view_path(file_key):
            return self._local.read_file(principal=principal, view_path=file_key)
        access = self._access.resolve(principal=principal, share_id=share_id, view_path=file_key)
        self._access.require_read(access)
        if access.virtual_shared:
            raise RuntimeError("Shared file resolution failed.")
        actor = replace(principal, workspace_id=access.workspace_id)
        storage_key = self._access.view_path_to_storage(access=access, view_path=file_key)
        read_back = self._manager.read_file(
            actor=actor,
            file_key=storage_key,
            include_reserved=for_agent and not access.share_id,
        )
        return self._remap_read(access=access, read_back=read_back, view_path=file_key)

    def read_file_bytes(
        self,
        *,
        principal: LocalPrincipal,
        file_key: str,
        share_id: str | None = None,
    ) -> tuple[str, str, bytes]:
        if is_local_view_path(file_key):
            return self._local.read_file_bytes(principal=principal, view_path=file_key)
        access = self._access.resolve(principal=principal, share_id=share_id, view_path=file_key)
        self._access.require_read(access)
        actor = replace(principal, workspace_id=access.workspace_id)
        storage_key = self._access.view_path_to_storage(access=access, view_path=file_key)
        return self._manager.read_file_bytes(actor=actor, file_key=storage_key)

    def save_file(
        self,
        *,
        principal: LocalPrincipal,
        file_key: str,
        content_markdown: str,
        share_id: str | None = None,
    ) -> WorkspaceFileMutation:
        if is_local_view_path(file_key):
            return self._local.save_file(
                principal=principal,
                view_path=file_key,
                content_markdown=content_markdown,
            )
        access = self._access.resolve(principal=principal, share_id=share_id, view_path=file_key)
        self._access.assert_view_path_allowed_for_write(access=access, view_path=file_key)
        actor = replace(principal, workspace_id=access.workspace_id)
        storage_key = self._access.view_path_to_storage(access=access, view_path=file_key)
        result = self._manager.save_file(
            actor=actor,
            payload={"fileKey": storage_key, "contentMarkdown": content_markdown},
        )
        return self._remap_mutation(access=access, mutation=result, view_path=file_key)

    def write_text_file(
        self,
        *,
        principal: LocalPrincipal,
        file_key: str,
        content_markdown: str = "",
        share_id: str | None = None,
        overwrite_existing: bool = False,
    ) -> WorkspaceFileMutation:
        if is_local_view_path(file_key):
            return self._local.write_text_file(
                principal=principal,
                view_path=file_key,
                content_markdown=content_markdown,
                overwrite_existing=overwrite_existing,
            )
        access = self._access.resolve(principal=principal, share_id=share_id, view_path=file_key)
        self._access.assert_view_path_allowed_for_write(access=access, view_path=file_key)
        actor = replace(principal, workspace_id=access.workspace_id)
        storage_key = self._access.view_path_to_storage(access=access, view_path=file_key)
        result = self._manager.write_text_file(
            actor=actor,
            file_key=storage_key,
            content_markdown=content_markdown,
            overwrite_existing=overwrite_existing,
        )
        return self._remap_mutation(access=access, mutation=result, view_path=file_key)

    def create_directory(
        self,
        *,
        principal: LocalPrincipal,
        directory: str,
        share_id: str | None = None,
    ) -> WorkspaceFileMutation:
        if is_local_view_path(directory):
            return self._local.create_directory(principal=principal, view_path=directory)
        access = self._access.resolve(principal=principal, share_id=share_id, view_path=directory)
        self._access.assert_view_path_allowed_for_write(access=access, view_path=directory)
        actor = replace(principal, workspace_id=access.workspace_id)
        storage_directory = self._access.view_path_to_storage(access=access, view_path=directory)
        result = self._manager.create_directory(actor=actor, payload={"directory": storage_directory})
        return self._remap_mutation(access=access, mutation=result, view_path=directory)

    def upload_files(
        self,
        *,
        principal: LocalPrincipal,
        directory: str | None,
        uploads: list[WorkspaceFileUpload],
        share_id: str | None = None,
    ) -> WorkspaceFileMutation:
        if is_local_view_path(directory or ""):
            return self._local.upload_files(
                principal=principal,
                view_path=directory or LOCAL_FILES_ROOT,
                uploads=uploads,
            )
        access = self._access.resolve(principal=principal, share_id=share_id, view_path=directory or "")
        self._access.require_write(access)
        actor = replace(principal, workspace_id=access.workspace_id)
        storage_directory = self._access.view_directory_to_storage(access=access, directory=directory)
        result = self._manager.upload_files(
            actor=actor,
            directory=storage_directory or None,
            uploads=uploads,
        )
        if access.share_id:
            return WorkspaceFileMutation(
                status=result.status,
                message=result.message,
                affectedCount=result.affectedCount,
                path=directory or None,
                destinationPath=(
                    self._access.storage_path_to_view(access=access, storage_path=result.destinationPath)
                    if result.destinationPath
                    else None
                ),
            )
        return result

    def move_path(
        self,
        *,
        principal: LocalPrincipal,
        source_path: str,
        destination_path: str,
        share_id: str | None = None,
    ) -> WorkspaceFileMutation:
        if is_local_view_path(source_path) or is_local_view_path(destination_path):
            return self._local.move_path(
                principal=principal,
                source_path=source_path,
                destination_path=destination_path,
            )
        access = self._access.resolve(principal=principal, share_id=share_id, view_path=source_path)
        source_storage, destination_storage = self._access.assert_move_allowed(
            access=access,
            source_view_path=source_path,
            destination_view_path=destination_path,
        )
        actor = replace(principal, workspace_id=access.workspace_id)
        result = self._manager.move_path(
            actor=actor,
            payload={"sourcePath": source_storage, "destinationPath": destination_storage},
        )
        return WorkspaceFileMutation(
            status=result.status,
            message=result.message,
            affectedCount=result.affectedCount,
            path=source_path,
            destinationPath=destination_path,
        )

    def delete_path(
        self,
        *,
        principal: LocalPrincipal,
        path: str,
        recursive: bool,
        share_id: str | None = None,
    ) -> WorkspaceFileMutation:
        if is_local_view_path(path):
            return self._local.delete_path(principal=principal, view_path=path, recursive=recursive)
        access = self._access.resolve(principal=principal, share_id=share_id, view_path=path)
        self._access.assert_view_path_allowed_for_write(access=access, view_path=path)
        actor = replace(principal, workspace_id=access.workspace_id)
        storage_path = self._access.view_path_to_storage(access=access, view_path=path)
        result = self._manager.delete_path(
            actor=actor,
            payload={"path": storage_path, "recursive": recursive},
        )
        return self._remap_mutation(access=access, mutation=result, view_path=path)

    def search_files(
        self,
        *,
        principal: LocalPrincipal,
        query: str,
        directory: str | None = None,
        share_id: str | None = None,
        limit: int = 25,
        for_agent: bool = False,
        options: SearchOptions | None = None,
        time_budget: float | None = None,
    ) -> dict[str, Any]:
        """Search names first, then the text of small text files, within a time limit.

        Folders on the computer can hold tens of thousands of files, so one search never
        walks or reads without bounds; it returns what it found and says it stopped early.
        """
        normalized_query = query.strip().casefold()
        if not normalized_query:
            raise WorkspaceFileBadRequestError("A search query is required.")
        options = options or SearchOptions()
        pattern = None
        if options.regex:
            try:
                pattern = re.compile(query, 0 if options.case_sensitive else re.IGNORECASE)
            except re.error as exc:
                raise WorkspaceFileBadRequestError(f"That regular expression is invalid: {exc}.") from exc
        budget = _SEARCH_TIME_BUDGET_SECONDS if time_budget is None else time_budget
        bounded_limit = max(1, min(limit, 50))
        search_root = normalize_workspace_file_prefix(directory)
        deadline = time.monotonic() + budget
        names_deadline = time.monotonic() + (budget if options.names_only else budget * 0.6)
        matches: list[dict[str, Any]] = []
        matched: set[str] = set()
        candidates: list[WorkspaceFileEntry] = []
        queue = deque([search_root])
        visited: set[str] = set()
        truncated = False
        path_query = "/" in normalized_query
        words = name_words(query)
        fast = self._local.can_search_fast()
        local_roots: list[str] = []
        parsed_root = parse_local_view_path(search_root)
        if fast and parsed_root is not None and parsed_root.mount_name:
            # Inside one folder on the computer: ripgrep only.
            local_roots.append(search_root)
            queue.clear()

        # Pass 1: file and folder names (whole paths when the query has a "/").
        while queue and len(matches) < bounded_limit:
            if time.monotonic() > names_deadline or len(visited) >= _SEARCH_MAX_DIRECTORIES:
                truncated = True
                break
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            try:
                listing = self.list_directory(
                    principal=principal, directory=current or None, share_id=share_id, for_agent=for_agent,
                )
            except WorkspaceFileError:
                continue
            for entry in listing.entries:
                if not _search_scope_allows(entry.path, search_root, options):
                    if entry.kind == "directory" and entry.name.casefold() not in _SEARCH_SKIP_DIRECTORIES:
                        queue.append(entry.path)
                    continue
                if pattern is not None:
                    hit = bool(pattern.search(entry.name))
                else:
                    hit = normalized_query in entry.path.casefold() if path_query else name_matches(entry.name, words)
                if hit:
                    matches.append(self._search_match(entry, snippet=None))
                    matched.add(entry.path)
                    if len(matches) >= bounded_limit:
                        break
                if entry.kind == "directory":
                    parsed_entry = parse_local_view_path(entry.path)
                    if fast and parsed_entry is not None and parsed_entry.mount_name and not parsed_entry.remainder:
                        local_roots.append(entry.path)  # A folder on the computer: ripgrep below.
                    elif entry.name.casefold() not in _SEARCH_SKIP_DIRECTORIES and entry.path not in visited:
                        queue.append(entry.path)
                elif _searchable_text(entry) and len(candidates) < _SEARCH_MAX_FILE_READS:
                    candidates.append(entry)
        if queue:
            truncated = True

        # Folders on the computer: ripgrep (names, then text) with the time that is left.
        for root in local_roots:
            if len(matches) >= bounded_limit or time.monotonic() > deadline:
                truncated = True
                break
            share = max(0.5, (deadline - time.monotonic()) / max(1, len(local_roots)))
            found = self._local.search(
                principal=principal, view_path=root, query=query,
                limit=bounded_limit - len(matches), deadline=min(deadline, time.monotonic() + share),
                options=options,
            )
            if found is None:
                continue
            hits, cut_short = found
            truncated = truncated or cut_short
            for view_path, hit in hits:
                if hit.line is not None or view_path not in matched:
                    matched.add(view_path)
                    matches.append(_folder_hit_match(view_path, hit))

        # Pass 2: text inside small text files found above.
        for entry in [] if options.names_only else candidates:
            if len(matches) >= bounded_limit:
                break
            if time.monotonic() > deadline:
                truncated = True
                break
            if entry.path in matched:
                continue
            try:
                content = self.read_file(
                    principal=principal, file_key=entry.path, share_id=share_id, for_agent=for_agent,
                ).contentMarkdown
            except Exception:
                continue
            lines = content.splitlines()
            found_in_file = 0
            for number, line in enumerate(lines, start=1):
                if pattern is not None:
                    hit = bool(pattern.search(line))
                elif options.case_sensitive:
                    hit = query.strip() in line
                else:
                    hit = normalized_query in line.casefold()
                if not hit:
                    continue
                match = self._search_match(entry, snippet=line.strip()[:300] or None)
                match["line"] = number
                if options.context_lines:
                    match["contextBefore"] = lines[max(0, number - 1 - options.context_lines):number - 1]
                    match["contextAfter"] = lines[number:number + options.context_lines]
                matches.append(match)
                found_in_file += 1
                if found_in_file >= options.max_per_file or len(matches) >= bounded_limit:
                    break

        result: dict[str, Any] = {
            "query": query,
            "directory": search_root,
            "pathArea": classify_workspace_path_area(search_root),
            "matches": matches,
            "matchCount": len(matches),
            "truncated": truncated,
        }
        if truncated:
            result["note"] = (
                "The search stopped early because this area is large. "
                "Search inside a more specific directory to see more."
            )
        return result

    @staticmethod
    def _search_match(entry: WorkspaceFileEntry, *, snippet: str | None) -> dict[str, Any]:
        return {
            "fileKey": entry.path,
            "kind": entry.kind,
            "pathArea": classify_workspace_path_area(entry.path),
            "mimeType": entry.mimeType,
            "editable": entry.editable,
            "updatedAt": entry.updatedAt.isoformat() if entry.updatedAt else None,
            "snippet": snippet,
        }

    def patch_file(
        self,
        *,
        principal: LocalPrincipal,
        file_key: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        share_id: str | None = None,
    ) -> WorkspaceFileMutation:
        if not old_string:
            raise WorkspaceFileBadRequestError("old_string is required.")
        if old_string == new_string:
            raise WorkspaceFileBadRequestError("new_string must differ from old_string.")
        read_back = self.read_file(
            principal=principal,
            file_key=file_key,
            share_id=share_id,
            for_agent=True,
        )
        content = read_back.contentMarkdown
        occurrences = content.count(old_string)
        if occurrences == 0:
            raise WorkspaceFileNotFoundError("That text was not found in the file.")
        if occurrences > 1 and not replace_all:
            raise WorkspaceFileConflictError("old_string matched multiple times. Set replaceAll=true or include more context.")
        updated = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
        return self.save_file(
            principal=principal,
            file_key=file_key,
            content_markdown=updated,
            share_id=share_id,
        )

    def list_shares(self, *, principal: LocalPrincipal, folder_path: str) -> list[WorkspaceFolderShareView]:
        owner_access = self._access.resolve(principal=principal, share_id=None, view_path=folder_path)
        normalized = self._access.normalize_owner_target_path(folder_path)
        self._access.assert_share_target_exists(access=owner_access, target_path=normalized)
        shares = self._repository.list_shares_for_folder(
            workspace_id=principal.workspace_id,
            folder_path=normalized,
            actor_user_id=principal.user_id,
        )
        return [self._share_view(share) for share in shares]

    def save_share(
        self,
        *,
        principal: LocalPrincipal,
        folder_path: str,
        grantee_user_id: str,
        permission: str,
    ) -> WorkspaceFolderShareView:
        owner_access = self._access.resolve(principal=principal, share_id=None, view_path=folder_path)
        normalized = self._access.normalize_owner_target_path(folder_path)
        normalized, share_kind = self._access.assert_share_target_exists(
            access=owner_access,
            target_path=normalized,
        )
        share = self._repository.upsert_share(
            workspace_id=principal.workspace_id,
            folder_path=normalized,
            grantee_user_id=grantee_user_id,
            permission=permission,
            created_by_user_id=principal.user_id,
            share_kind=share_kind,
            share_mount_name=share_mount_name_for_path(target_path=normalized, share_kind=share_kind),
        )
        return self._share_view(share)

    def revoke_share(self, *, principal: LocalPrincipal, share_id: str) -> None:
        self._repository.revoke_share(
            workspace_id=principal.workspace_id,
            share_id=share_id,
            actor_user_id=principal.user_id,
        )

    def _list_shared_root(self, *, principal: LocalPrincipal) -> WorkspaceFileDirectory:
        owners = sorted(
            {
                (share.owner_username or "user")
                for share in self._repository.list_shares_for_grantee(grantee_user_id=principal.user_id)
            },
            key=str.casefold,
        )
        entries = [
            WorkspaceFileEntry(
                kind="directory",
                name=owner_username,
                path=shared_owner_directory(owner_username=owner_username),
                shared=True,
                sharedFrom=owner_username,
            )
            for owner_username in owners
        ]
        return WorkspaceFileDirectory(
            currentDirectory=SHARED_FILES_ROOT,
            parentDirectory=None,
            entries=entries,
        )

    def _list_shared_owner(
        self,
        *,
        principal: LocalPrincipal,
        owner_username: str,
    ) -> WorkspaceFileDirectory:
        shares = [
            share for share in self._repository.list_shares_for_grantee(grantee_user_id=principal.user_id)
            if (share.owner_username or "").casefold() == owner_username.casefold()
        ]
        entries = [
            WorkspaceFileEntry(
                kind="directory" if share.share_kind == "folder" else "file",
                name=share.share_mount_name,
                path=build_shared_mount_path(
                    owner_username=owner_username,
                    mount_name=share.share_mount_name,
                ),
                shared=True,
                shareId=share.share_id,
                sharedFrom=share.owner_display_name or owner_username,
                permission=share.permission,
            )
            for share in sorted(shares, key=lambda item: item.share_mount_name.casefold())
        ]
        return WorkspaceFileDirectory(
            currentDirectory=shared_owner_directory(owner_username=owner_username),
            parentDirectory=SHARED_FILES_ROOT,
            entries=entries,
        )

    def _list_owner_workspace_root(
        self,
        *,
        principal: LocalPrincipal,
        for_agent: bool,
    ) -> WorkspaceFileDirectory:
        listing = self._manager.list_directory(
            actor=principal,
            directory=None,
            include_reserved=for_agent,
        )
        entries = list(listing.entries)
        if self._local.is_available(principal=principal):
            if not any(entry.path == LOCAL_FILES_ROOT for entry in entries):
                entries.insert(
                    0,
                    WorkspaceFileEntry(
                        kind="directory",
                        name=LOCAL_FILES_ROOT,
                        path=LOCAL_FILES_ROOT,
                        childCount=len(self._local.list_root(principal=principal).entries),
                        linked=True,
                    ),
                )
        if not any(entry.path == SHARED_FILES_ROOT for entry in entries):
            entries.insert(
                0,
                WorkspaceFileEntry(
                    kind="directory",
                    name=SHARED_FILES_ROOT,
                    path=SHARED_FILES_ROOT,
                    childCount=len(self._list_shared_root(principal=principal).entries),
                ),
            )
        return WorkspaceFileDirectory(
            currentDirectory=listing.currentDirectory,
            parentDirectory=listing.parentDirectory,
            entries=entries,
        )

    def _share_view(self, share: WorkspaceFolderShare) -> WorkspaceFolderShareView:
        return WorkspaceFolderShareView(
            shareId=share.share_id,
            folderPath=share.folder_path,
            granteeUserId=share.grantee_user_id,
            granteeDisplayName=share.grantee_display_name or share.grantee_username or share.grantee_user_id,
            granteeUsername=share.grantee_username or "",
            permission=share.permission,
            shareKind=share.share_kind,
        )

    def _remap_read(
        self,
        *,
        access: WorkspaceAccess,
        read_back: WorkspaceFileRead,
        view_path: str,
    ) -> WorkspaceFileRead:
        view_key = view_path or self._access.storage_path_to_view(
            access=access,
            storage_path=read_back.fileKey,
        )
        return WorkspaceFileRead(
            fileKey=view_key,
            filename=read_back.filename,
            contentMarkdown=read_back.contentMarkdown,
            sizeBytes=read_back.sizeBytes,
            mimeType=read_back.mimeType,
            editable=read_back.editable if access.can_write else False,
            projectionVersion=read_back.projectionVersion,
            updatedAt=read_back.updatedAt,
        )

    def _remap_mutation(
        self,
        *,
        access: WorkspaceAccess,
        mutation: WorkspaceFileMutation,
        view_path: str,
    ) -> WorkspaceFileMutation:
        if not access.share_id:
            return mutation
        destination = mutation.destinationPath
        if destination is not None:
            destination = self._access.storage_path_to_view(access=access, storage_path=destination)
        return WorkspaceFileMutation(
            status=mutation.status,
            message=mutation.message,
            affectedCount=mutation.affectedCount,
            path=view_path or self._access.storage_path_to_view(access=access, storage_path=mutation.path or ""),
            destinationPath=destination,
        )

    def _remap_entry(self, *, access: WorkspaceAccess, entry: WorkspaceFileEntry) -> WorkspaceFileEntry:
        if not access.share_id:
            return entry
        view_path = self._access.storage_path_to_view(access=access, storage_path=entry.path)
        return WorkspaceFileEntry(
            kind=entry.kind,
            name=entry.name,
            path=view_path,
            sizeBytes=entry.sizeBytes,
            childCount=entry.childCount,
            mimeType=entry.mimeType,
            editable=entry.editable if access.can_write else False,
            projectionVersion=entry.projectionVersion,
            updatedAt=entry.updatedAt,
            shared=True,
            shareId=access.share_id,
            permission=access.permission,
        )

    @staticmethod
    def _shared_parent_directory(current_directory: str) -> str | None:
        if not current_directory:
            return None
        parent = "/".join(current_directory.strip("/").split("/")[:-1])
        return parent or None

    @staticmethod
    def _finalize_agent_listing(
        listing: WorkspaceFileDirectory,
        *,
        for_agent: bool,
    ) -> WorkspaceFileDirectory:
        if not for_agent:
            return listing
        return annotate_directory_listing(listing)

    def _shared_mount_descriptors(self, *, principal: LocalPrincipal) -> list[dict[str, Any]]:
        mounts: list[dict[str, Any]] = []
        for share in self._repository.list_shares_for_grantee(grantee_user_id=principal.user_id):
            owner_username = share.owner_username or "user"
            mounts.append(
                {
                    "path": build_shared_mount_path(
                        owner_username=owner_username,
                        mount_name=share.share_mount_name,
                    ),
                    "ownerUsername": owner_username,
                    "mountName": share.share_mount_name,
                    "shareId": share.share_id,
                    "permission": share.permission,
                    "shareKind": share.share_kind,
                }
            )
        return mounts

    def _local_mount_descriptors(self, *, principal: LocalPrincipal) -> list[dict[str, Any]]:
        if self._folders is None:
            return []
        return self._folders.agent_descriptors(principal=principal)
