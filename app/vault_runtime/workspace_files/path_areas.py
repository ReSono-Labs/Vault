from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.vault_runtime.workspace_files.local_paths import LOCAL_FILES_ROOT, is_local_view_path
from app.vault_runtime.workspace_files.models import WorkspaceFileDirectory, WorkspaceFileEntry
from app.vault_runtime.workspace_files.shared_paths import SHARED_FILES_ROOT, is_shared_view_path


VAULT_PATH_AREA = "vault"
SHARED_PATH_AREA = "shared"
LOCAL_PATH_AREA = "local"

WORKSPACE_PATH_AREA_DESCRIPTORS: dict[str, dict[str, Any]] = {
    VAULT_PATH_AREA: {
        "id": VAULT_PATH_AREA,
        "label": "Vault",
        "rootPrefix": "",
        "pathPattern": "{folder}/{file}",
        "pathExample": "notes/today.md",
        "description": (
            "Default workspace storage on Vault for this user. Paths do not start with shared/ or local/."
        ),
        "agentRead": True,
        "agentWrite": True,
        "notes": (
            "Reserved files such as WORKSPACE.md live here. This is where the user normally stores notes and uploads."
        ),
    },
    SHARED_PATH_AREA: {
        "id": SHARED_PATH_AREA,
        "label": "Shared with me",
        "rootPrefix": SHARED_FILES_ROOT,
        "pathPattern": f"{SHARED_FILES_ROOT}/{{ownerUsername}}/{{mountName}}/...",
        "pathExample": f"{SHARED_FILES_ROOT}/alice/Reports/Q1.pdf",
        "description": (
            "Folders and files that other Vault users shared with this user. Each mount is read-only at the "
            "workspace root until you enter the mount path."
        ),
        "agentRead": True,
        "agentWrite": "Only when the share permission is write.",
        "notes": (
            "Pass shareId to workspace tools when the session is scoped to one shared folder. "
            "Otherwise browse with paths under shared/."
        ),
    },
    LOCAL_PATH_AREA: {
        "id": LOCAL_PATH_AREA,
        "label": "Computer folders",
        "rootPrefix": LOCAL_FILES_ROOT,
        "pathPattern": f"{LOCAL_FILES_ROOT}/{{mountName}}/...",
        "pathExample": f"{LOCAL_FILES_ROOT}/Documents/invoice.pdf",
        "description": (
            "Folders linked from the user's computer. Mount names come from Settings > Computer folders."
        ),
        "agentRead": "Helper-linked mounts only. Browser-linked mounts appear in listings but file content is not available server-side.",
        "agentWrite": "Only helper-linked mounts with write permission.",
        "notes": (
            "source=helper means the host helper can serve files to agents. "
            "source=browser means the user browses those files in the Vault browser tab."
        ),
    },
}


def classify_workspace_path_area(path: str | None) -> str:
    if is_local_view_path(path):
        return LOCAL_PATH_AREA
    if is_shared_view_path(path):
        return SHARED_PATH_AREA
    return VAULT_PATH_AREA


def annotate_directory_listing(listing: WorkspaceFileDirectory) -> WorkspaceFileDirectory:
    current_area = classify_workspace_path_area(listing.currentDirectory)
    entries = [
        replace(entry, pathArea=classify_workspace_path_area(entry.path))
        for entry in listing.entries
    ]
    return replace(listing, pathArea=current_area, entries=entries)


WORKSPACE_AGENT_FILE_TOOLS: tuple[dict[str, str], ...] = (
    {
        "name": "workspace_root",
        "effect": "read",
        "hermesEquivalent": "(path guidance)",
        "description": "Return path area descriptors, available mounts, and workspace path rules.",
    },
    {
        "name": "workspace_list_directory",
        "effect": "read",
        "hermesEquivalent": "search_files(target=files) / list",
        "description": "List folders and files at vault, shared/, or local/ paths.",
    },
    {
        "name": "workspace_read_file",
        "effect": "read",
        "hermesEquivalent": "read_file",
        "description": "Read a text workspace file by relative path.",
    },
    {
        "name": "workspace_search_files",
        "effect": "read",
        "hermesEquivalent": "search_files(target=content)",
        "description": "Search file names and text content under a directory prefix.",
    },
    {
        "name": "workspace_write_file",
        "effect": "write",
        "hermesEquivalent": "write_file",
        "description": "Create a new text file. Fails if the path already exists unless overwriteExisting is true.",
    },
    {
        "name": "workspace_save_file",
        "effect": "write",
        "hermesEquivalent": "write_file (replace existing)",
        "description": "Replace the full contents of an existing text file.",
    },
    {
        "name": "workspace_patch_file",
        "effect": "write",
        "hermesEquivalent": "patch(mode=replace)",
        "description": "Apply a targeted old_string to new_string edit inside one text file.",
    },
    {
        "name": "workspace_create_directory",
        "effect": "write",
        "hermesEquivalent": "(mkdir via terminal in Hermes)",
        "description": "Create a folder at the requested path.",
    },
    {
        "name": "workspace_move_path",
        "effect": "write",
        "hermesEquivalent": "(mv via terminal in Hermes)",
        "description": "Rename or move a file or folder.",
    },
    {
        "name": "workspace_delete_path",
        "effect": "delete",
        "hermesEquivalent": "(rm via terminal in Hermes)",
        "description": "Delete a file or folder. Set recursive=true for non-empty folders.",
    },
    {
        "name": "workspace_upload_files",
        "effect": "write",
        "hermesEquivalent": "write_file (binary/base64)",
        "description": "Upload one or more files into a directory using base64 payloads.",
    },
)


def build_agent_path_areas(
    *,
    shared_mounts: list[dict[str, Any]],
    local_enabled: bool,
    local_mounts: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    vault = dict(WORKSPACE_PATH_AREA_DESCRIPTORS[VAULT_PATH_AREA])
    shared = dict(WORKSPACE_PATH_AREA_DESCRIPTORS[SHARED_PATH_AREA])
    shared["mounts"] = shared_mounts
    local = dict(WORKSPACE_PATH_AREA_DESCRIPTORS[LOCAL_PATH_AREA])
    local["enabled"] = local_enabled
    local["mounts"] = local_mounts
    return {
        VAULT_PATH_AREA: vault,
        SHARED_PATH_AREA: shared,
        LOCAL_PATH_AREA: local,
    }


def agent_tool_catalog() -> list[dict[str, str]]:
    return [dict(item) for item in WORKSPACE_AGENT_FILE_TOOLS]
