from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Any

from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult
from app.vault_runtime.workspace_files.constants import WORKSPACE_AGENT_ROOT_GUIDANCE
from app.vault_runtime.workspace_files.manager import WorkspaceFileUpload
from app.vault_runtime.workspace_files.path_areas import classify_workspace_path_area
from app.vault_runtime.workspace_files.service import WorkspaceFileService

PATH_PREFIX_GUIDANCE = (
    "Paths use vault (notes/foo.md), shared (shared/owner/mount/...), or local (local/mount/...) prefixes. "
    "Call workspace_root first for path area descriptors and available mounts."
)


def register_workspace_file_tools(*, catalog: ToolCatalog, service: WorkspaceFileService) -> None:
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
        read = service.read_file(
            principal=actor,
            file_key=file_key,
            share_id=share_id,
            for_agent=True,
        )
        payload = enrich_payload(read.to_dict(), actor=actor, share_id=share_id, path=file_key)
        return json_result(payload)

    def search_files(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        query = str(arguments.get("query", "")).strip()
        directory = str(arguments.get("directory", "") or "")
        limit = int(arguments.get("limit", 25) or 25)
        actor = principal(context)
        share_id = share_id_from(arguments)
        payload = enrich_payload(
            service.search_files(
                principal=actor,
                query=query,
                directory=directory or None,
                share_id=share_id,
                limit=limit,
                for_agent=True,
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
            description="Read one text workspace file. Hermes equivalent: read_file. " + PATH_PREFIX_GUIDANCE,
            input_schema={
                "type": "object",
                "properties": path_schema,
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
                "Search workspace file names and text content under a directory prefix. "
                "Hermes equivalent: search_files(target=content). "
                + PATH_PREFIX_GUIDANCE
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "directory": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
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
                "Replace the full contents of an existing text file when the final body and exact path are known. "
                "Hermes equivalent: write_file for full replacement edits. "
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
                "Apply a targeted old_string to new_string edit inside one text file. "
                "Hermes equivalent: patch(mode=replace). "
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
    for definition in definitions:
        catalog.register(definition)
