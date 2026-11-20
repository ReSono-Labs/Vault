from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Any

from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult
from app.vault_runtime.folders.search import SearchOptions
from app.vault_runtime.workspace_files.constants import WORKSPACE_AGENT_ROOT_GUIDANCE
from app.vault_runtime.workspace_files.discovery import Budget, WorkspaceDiscovery
from app.vault_runtime.workspace_files.manager import WorkspaceFileUpload
from app.vault_runtime.workspace_files.path_areas import classify_workspace_path_area
from app.vault_runtime.workspace_files.service import WorkspaceFileService

PATH_PREFIX_GUIDANCE = (
    "Paths: Vault's own files have no prefix (e.g. Idea Lab/README.md, never vault/...); "
    "folders shared by others are under shared/{owner}/{mount}/...; folders on the user's computer are under "
    "local/{mount}/.... Paths are relative, with single slashes. "
    "Call workspace_root or list shared/ and local/ for the current mounts; do not assume folder names."
)


def _int(value: object, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ValueError("Line numbers and counts must be whole numbers.") from exc


def _patterns(value: object) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value[:20])
    raise ValueError("include and exclude must be glob strings or lists of them.")


def register_workspace_file_tools(*, catalog: ToolCatalog, service: WorkspaceFileService) -> None:
    discovery = WorkspaceDiscovery(service)

    def budget(context: ToolInvocationContext) -> Budget:
        # Voice answers out loud while the person waits; Chat and Background get more room.
        return Budget.for_agent(voice=bool(context.voice_session_id))
    def principal(context: ToolInvocationContext) -> LocalPrincipal:
        return LocalPrincipal(
            user_id=context.user_id,
            username="agent",
            display_name="Agent",
            experience_style="balanced",
            is_device_owner=False,
            session_id=context.local_session_id or context.execution_id,
            workspace_id=context.workspace_id,
            expires_at=datetime.now(UTC),
        )

    def share_id_from(arguments: dict[str, object]) -> str | None:
        value = str(arguments.get("shareId", "") or "").strip()
        return value or None

    def enrich_payload(
        payload: dict[str, Any],
        *,
        actor: LocalPrincipal,
        share_id: str | None,
        path: str | None = None,
    ) -> dict[str, Any]:
        payload["workspaceRoot"] = service.workspace_root_info(principal=actor, share_id=share_id)
        resolved_path = path
        if resolved_path is None:
            resolved_path = str(payload.get("fileKey") or payload.get("currentDirectory") or payload.get("directory") or "")
        if resolved_path:
            payload["pathArea"] = classify_workspace_path_area(resolved_path)
        return payload

    def json_result(payload: dict[str, Any]) -> ToolInvocationResult:
        return ToolInvocationResult(json.dumps(payload, separators=(",", ":")), payload)

    def list_directory(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        directory = str(arguments.get("directory", "") or "")
        actor = principal(context)
        share_id = share_id_from(arguments)
        listing = service.list_directory(
            principal=actor,
            directory=directory or None,
            share_id=share_id,
            for_agent=True,
        )
        payload = enrich_payload(
            listing.to_dict(),
            actor=actor,
            share_id=share_id,
            path=listing.currentDirectory,
        )
        return json_result(payload)

    def read_file(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        file_key = str(arguments.get("fileKey", "")).strip()
        actor = principal(context)
        share_id = share_id_from(arguments)
        read = discovery.read_lines(
            principal=actor, file_key=file_key, share_id=share_id,
            start_line=_int(arguments.get("startLine")), end_line=_int(arguments.get("endLine")),
            head=_int(arguments.get("head")), tail=_int(arguments.get("tail")),
        )
        payload = enrich_payload(read, actor=actor, share_id=share_id, path=file_key)
        return json_result(payload)

    def read_files(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        keys = arguments.get("fileKeys")
        if not isinstance(keys, list) or not all(isinstance(item, str) for item in keys):
            raise ValueError("fileKeys must be a list of paths.")
        return json_result(discovery.read_many(principal=principal(context), file_keys=[k.strip() for k in keys],
                                               share_id=share_id_from(arguments)))

    def glob_files(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        return json_result(discovery.glob(
            principal=principal(context), pattern=str(arguments.get("pattern", "")),
            directory=str(arguments.get("directory", "") or "") or None, budget=budget(context),
            share_id=share_id_from(arguments),
        ))

    def tree(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        return json_result(discovery.tree(
            principal=principal(context), directory=str(arguments.get("directory", "") or "") or None,
            depth=_int(arguments.get("depth"), 2) or 2, budget=budget(context), share_id=share_id_from(arguments),
        ))

    def file_info(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        return json_result(discovery.info(principal=principal(context), path=str(arguments.get("path", "")),
                                          share_id=share_id_from(arguments)))

    def copy_path(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        return json_result(discovery.copy(
            principal=principal(context), source=str(arguments.get("sourcePath", "")),
            destination=str(arguments.get("destinationPath", "")), share_id=share_id_from(arguments),
        ))

    def search_files(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        query = str(arguments.get("query", "")).strip()
        directory = str(arguments.get("directory", "") or "")
        limit = int(arguments.get("limit", 25) or 25)
        actor = principal(context)
        share_id = share_id_from(arguments)
        options = SearchOptions(
            regex=arguments.get("regex") is True,
            case_sensitive=arguments.get("caseSensitive") is True,
            include=_patterns(arguments.get("include")),
            exclude=_patterns(arguments.get("exclude")),
            context_lines=_int(arguments.get("contextLines"), 0) or 0,
            max_per_file=_int(arguments.get("maxPerFile"), 1) or 1,
            names_only=arguments.get("namesOnly") is True,
        )
        limits = budget(context)
        payload = enrich_payload(
            service.search_files(
                principal=actor,
                query=query,
                directory=directory or None,
                share_id=share_id,
                limit=min(limit, limits.results),
                for_agent=True,
                options=options,
                time_budget=limits.seconds,
            ),
            actor=actor,
            share_id=share_id,
            path=directory,
        )
        return json_result(payload)

    def write_file(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        file_key = str(arguments.get("fileKey", "")).strip()
        content = str(arguments.get("content", ""))
        overwrite = bool(arguments.get("overwriteExisting", False))
        actor = principal(context)
        share_id = share_id_from(arguments)
        mutation = service.write_text_file(
            principal=actor,
            file_key=file_key,
            content_markdown=content,
            share_id=share_id,
            overwrite_existing=overwrite,
        )
        payload = enrich_payload(mutation.to_dict(), actor=actor, share_id=share_id, path=file_key)
        return json_result(payload)

    def save_file(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        file_key = str(arguments.get("fileKey", "")).strip()
        content = str(arguments.get("contentMarkdown", arguments.get("content", "")))
        overwrite = bool(arguments.get("overwriteExisting", True))
        actor = principal(context)
        share_id = share_id_from(arguments)
        mutation = service.write_text_file(
            principal=actor,
            file_key=file_key,
            content_markdown=content,
            share_id=share_id,
            overwrite_existing=overwrite,
        )
        payload = enrich_payload(mutation.to_dict(), actor=actor, share_id=share_id, path=file_key)
        return json_result(payload)

    def patch_file(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        file_key = str(arguments.get("fileKey", "")).strip()
        old_string = str(arguments.get("oldString", ""))
        new_string = str(arguments.get("newString", ""))
        replace_all = bool(arguments.get("replaceAll", False))
        actor = principal(context)
        share_id = share_id_from(arguments)
        mutation = service.patch_file(
            principal=actor,
            file_key=file_key,
            old_string=old_string,
            new_string=new_string,
            replace_all=replace_all,
            share_id=share_id,
        )
        payload = enrich_payload(mutation.to_dict(), actor=actor, share_id=share_id, path=file_key)
        return json_result(payload)

    def create_directory(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        directory = str(arguments.get("directory", "")).strip()
        actor = principal(context)
        share_id = share_id_from(arguments)
        mutation = service.create_directory(
            principal=actor,
            directory=directory,
            share_id=share_id,
        )
        payload = enrich_payload(mutation.to_dict(), actor=actor, share_id=share_id, path=directory)
        return json_result(payload)

    def move_path(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        source_path = str(arguments.get("sourcePath", "")).strip()
        destination_path = str(arguments.get("destinationPath", "")).strip()
        actor = principal(context)
        share_id = share_id_from(arguments)
        mutation = service.move_path(
            principal=actor,
            source_path=source_path,
            destination_path=destination_path,
            share_id=share_id,
        )
        payload = enrich_payload(mutation.to_dict(), actor=actor, share_id=share_id, path=source_path)
        return json_result(payload)

    def delete_path(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        path = str(arguments.get("path", "")).strip()
        recursive = bool(arguments.get("recursive", False))
        actor = principal(context)
        share_id = share_id_from(arguments)
        mutation = service.delete_path(
            principal=actor,
            path=path,
            recursive=recursive,
            share_id=share_id,
        )
        payload = enrich_payload(mutation.to_dict(), actor=actor, share_id=share_id, path=path)
        return json_result(payload)

    def upload_files(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        directory = str(arguments.get("directory", "") or "")
        raw_files = arguments.get("files")
        if not isinstance(raw_files, list) or not raw_files:
            raise ValueError("files must be a non-empty array.")
        uploads: list[WorkspaceFileUpload] = []
        for item in raw_files:
            if not isinstance(item, dict):
                raise ValueError("Each file entry must be an object.")
            filename = str(item.get("filename", "")).strip()
            if not filename:
                raise ValueError("Each file entry requires filename.")
            if "contentBase64" in item:
                content = base64.b64decode(str(item.get("contentBase64") or "").encode("ascii"))
            else:
                content = str(item.get("content", "")).encode("utf-8")
            uploads.append(WorkspaceFileUpload(filename=filename, content=content))
        actor = principal(context)
        share_id = share_id_from(arguments)
        mutation = service.upload_files(
            principal=actor,
            directory=directory or None,
            uploads=uploads,
            share_id=share_id,
        )
        payload = enrich_payload(mutation.to_dict(), actor=actor, share_id=share_id, path=directory)
        return json_result(payload)

    def workspace_root(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        actor = principal(context)
        share_id = share_id_from(arguments)
        payload = {
            "guidance": WORKSPACE_AGENT_ROOT_GUIDANCE,
            **service.workspace_root_info(principal=actor, share_id=share_id),
        }
        return json_result(payload)

    share_id_schema = {"shareId": {"type": "string"}}
    path_schema = {
        "fileKey": {"type": "string", "minLength": 1},
        **share_id_schema,
    }

    definitions = (
        ToolDefinition(
            tool_id="builtin.workspace-root.v1",
            name="workspace_root",
            description=(
                "Return authorized workspace path rules, path area descriptors (vault, shared, local), "
                "available mounts, and the workspace file tool catalog."
            ),
            input_schema={"type": "object", "properties": share_id_schema, "additionalProperties": False},
            handler=workspace_root,
            effect_class="read",
            audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}),
        ),
        ToolDefinition(
            tool_id="builtin.workspace-list-directory.v1",
            name="workspace_list_directory",
            description=(
                "List folders and files. Hermes equivalent: list/search file names. "
                + PATH_PREFIX_GUIDANCE
            ),
            input_schema={
                "type": "object",
                "properties": {"directory": {"type": "string"}, **share_id_schema},
                "additionalProperties": False,
            },
            handler=list_directory,
            effect_class="read",
            audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}),
        ),
        ToolDefinition(
            tool_id="builtin.workspace-read-file.v1",
            name="workspace_read_file",
            description=(
                "Read one text file. For long files read part of it with startLine/endLine (1-based, inclusive), "
                "or the first/last lines with head/tail; totalLines tells you how long it is. "
                "Hermes equivalent: read_file. " + PATH_PREFIX_GUIDANCE
            ),
            input_schema={
                "type": "object",
                "properties": {
                    **path_schema,
                    "startLine": {"type": "integer", "minimum": 1},
                    "endLine": {"type": "integer", "minimum": 1},
                    "head": {"type": "integer", "minimum": 0, "maximum": 5000},
                    "tail": {"type": "integer", "minimum": 0, "maximum": 5000},
                },
                "required": ["fileKey"],
                "additionalProperties": False,
            },
            handler=read_file,
            effect_class="read",
            audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}),
        ),
        ToolDefinition(
            tool_id="builtin.workspace-search-files.v1",
            name="workspace_search_files",
            description=(
                "Search file and folder names, then the text of small text files, under a directory prefix. "
                "Large areas stop early with truncated=true; then search a more specific directory. "
                "Hermes equivalent: search_files(target=content). "
                + PATH_PREFIX_GUIDANCE
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "directory": {"type": "string", "description": "Search here, e.g. local/Projects/app. Narrower is faster."},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                    "regex": {"type": "boolean", "description": "Treat query as a regular expression (default: plain text)."},
                    "caseSensitive": {"type": "boolean"},
                    "include": {"type": "array", "items": {"type": "string"}, "description": "Only paths matching these globs, e.g. **/*.py"},
                    "exclude": {"type": "array", "items": {"type": "string"}, "description": "Skip paths matching these globs."},
                    "contextLines": {"type": "integer", "minimum": 0, "maximum": 3, "description": "Lines before each match to include."},
                    "maxPerFile": {"type": "integer", "minimum": 1, "maximum": 20},
                    "namesOnly": {"type": "boolean", "description": "Match file and folder names only, never contents."},
                    **share_id_schema,
                },
                "required": ["query"],
                "additionalProperties": False,
            },
            handler=search_files,
            effect_class="read",
            audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}),
        ),
        ToolDefinition(
            tool_id="builtin.workspace-write-file.v1",
            name="workspace_write_file",
            description=(
                "Create a new text workspace file. Hermes equivalent: write_file for new files. "
                + PATH_PREFIX_GUIDANCE
            ),
            input_schema={
                "type": "object",
                "properties": {
                    **path_schema,
                    "content": {"type": "string"},
                    "overwriteExisting": {"type": "boolean"},
                },
                "required": ["fileKey", "content"],
                "additionalProperties": False,
            },
            handler=write_file,
            effect_class="write",
            audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}),
        ),
        ToolDefinition(
            tool_id="builtin.workspace-save-file.v1",
            name="workspace_save_file",
            description=(
                "Replace the full contents of an existing text file with contentMarkdown. For a small change use "
                "workspace_patch_file instead. Hermes equivalent: write_file for full replacement edits. "
                + PATH_PREFIX_GUIDANCE
            ),
            input_schema={
                "type": "object",
                "properties": {
                    **path_schema,
                    "contentMarkdown": {"type": "string"},
                    "overwriteExisting": {"type": "boolean"},
                },
                "required": ["fileKey", "contentMarkdown"],
                "additionalProperties": False,
            },
            handler=save_file,
            effect_class="write",
            audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}),
        ),
        ToolDefinition(
            tool_id="builtin.workspace-patch-file.v1",
            name="workspace_patch_file",
            description=(
                "Change part of one existing text file: oldString is the exact text to find (it must appear once "
                "unless replaceAll=true) and newString replaces it. Read the file first. Prefer this to rewriting "
                "the whole file. Hermes equivalent: patch(mode=replace). "
                + PATH_PREFIX_GUIDANCE
            ),
            input_schema={
                "type": "object",
                "properties": {
                    **path_schema,
                    "oldString": {"type": "string", "minLength": 1},
                    "newString": {"type": "string"},
                    "replaceAll": {"type": "boolean"},
                },
                "required": ["fileKey", "oldString", "newString"],
                "additionalProperties": False,
            },
            handler=patch_file,
            effect_class="write",
            audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}),
        ),
        ToolDefinition(
            tool_id="builtin.workspace-create-directory.v1",
            name="workspace_create_directory",
            description="Create a workspace folder. " + PATH_PREFIX_GUIDANCE,
            input_schema={
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "minLength": 1},
                    **share_id_schema,
                },
                "required": ["directory"],
                "additionalProperties": False,
            },
            handler=create_directory,
            effect_class="write",
            audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}),
        ),
        ToolDefinition(
            tool_id="builtin.workspace-move-path.v1",
            name="workspace_move_path",
            description="Rename or move a workspace file or folder. " + PATH_PREFIX_GUIDANCE,
            input_schema={
                "type": "object",
                "properties": {
                    "sourcePath": {"type": "string", "minLength": 1},
                    "destinationPath": {"type": "string", "minLength": 1},
                    **share_id_schema,
                },
                "required": ["sourcePath", "destinationPath"],
                "additionalProperties": False,
            },
            handler=move_path,
            effect_class="write",
            audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}),
        ),
        ToolDefinition(
            tool_id="builtin.workspace-delete-path.v1",
            name="workspace_delete_path",
            description=(
                "Delete a workspace file or folder. Set recursive=true for non-empty folders. "
                + PATH_PREFIX_GUIDANCE
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "recursive": {"type": "boolean"},
                    **share_id_schema,
                },
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=delete_path,
            effect_class="delete",
            audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}),
        ),
        ToolDefinition(
            tool_id="builtin.workspace-upload-files.v1",
            name="workspace_upload_files",
            description=(
                "Upload one or more files into a directory using base64 or text content payloads. "
                + PATH_PREFIX_GUIDANCE
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "directory": {"type": "string"},
                    "files": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "type": "object",
                            "properties": {
                                "filename": {"type": "string", "minLength": 1},
                                "contentBase64": {"type": "string"},
                                "content": {"type": "string"},
                            },
                            "required": ["filename"],
                            "additionalProperties": False,
                        },
                    },
                    **share_id_schema,
                },
                "required": ["files"],
                "additionalProperties": False,
            },
            handler=upload_files,
            effect_class="write",
            audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}),
        ),
    )
    every_agent = frozenset({AgentKind.VOICE, AgentKind.BACKGROUND})
    discovery_definitions = (
        ToolDefinition(
            tool_id="builtin.workspace-glob.v1",
            name="workspace_glob",
            description=(
                "Find files by path pattern, like **/*.pdf, **/README* or src/**/*.ts. Skips dependency and "
                "build folders and anything in .gitignore. Use directory to start inside a folder. "
                + PATH_PREFIX_GUIDANCE
            ),
            input_schema={
                "type": "object",
                "properties": {"pattern": {"type": "string", "minLength": 1, "maxLength": 200},
                               "directory": {"type": "string"}, **share_id_schema},
                "required": ["pattern"],
                "additionalProperties": False,
            },
            handler=glob_files, effect_class="read", audiences=every_agent,
        ),
        ToolDefinition(
            tool_id="builtin.workspace-tree.v1",
            name="workspace_tree",
            description=(
                "Show a folder's tree in one call, depth 1-5 (default 2), with file sizes. Use it to get an "
                "overview of a project instead of listing folders one by one. " + PATH_PREFIX_GUIDANCE
            ),
            input_schema={
                "type": "object",
                "properties": {"directory": {"type": "string"}, "depth": {"type": "integer", "minimum": 1, "maximum": 5},
                               **share_id_schema},
                "additionalProperties": False,
            },
            handler=tree, effect_class="read", audiences=every_agent,
        ),
        ToolDefinition(
            tool_id="builtin.workspace-read-files.v1",
            name="workspace_read_files",
            description="Read up to 10 text files in one call. A file that fails doesn't stop the others. " + PATH_PREFIX_GUIDANCE,
            input_schema={
                "type": "object",
                "properties": {"fileKeys": {"type": "array", "items": {"type": "string", "minLength": 1},
                                            "minItems": 1, "maxItems": 10}, **share_id_schema},
                "required": ["fileKeys"],
                "additionalProperties": False,
            },
            handler=read_files, effect_class="read", audiences=every_agent,
        ),
        ToolDefinition(
            tool_id="builtin.workspace-file-info.v1",
            name="workspace_file_info",
            description="Size, type, modified time and line count of one file or folder. " + PATH_PREFIX_GUIDANCE,
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "minLength": 1}, **share_id_schema},
                "required": ["path"],
                "additionalProperties": False,
            },
            handler=file_info, effect_class="read", audiences=every_agent,
        ),
        ToolDefinition(
            tool_id="builtin.workspace-copy-path.v1",
            name="workspace_copy_path",
            description="Copy one file to a new path. Never overwrites. " + PATH_PREFIX_GUIDANCE,
            input_schema={
                "type": "object",
                "properties": {"sourcePath": {"type": "string", "minLength": 1},
                               "destinationPath": {"type": "string", "minLength": 1}, **share_id_schema},
                "required": ["sourcePath", "destinationPath"],
                "additionalProperties": False,
            },
            handler=copy_path, effect_class="write", audiences=every_agent,
        ),
    )
    for definition in definitions + discovery_definitions:
        catalog.register(definition)
