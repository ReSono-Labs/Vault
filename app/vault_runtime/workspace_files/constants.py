from __future__ import annotations

RESERVED_WORKSPACE_FILE_KEYS = frozenset(
    {
        "DEVICE_FAMILY.md",
        "MEMORY.md",
        "SANDBOX.md",
        "TOOLS.md",
        "USER.md",
        "WORKSPACE.md",
    }
)

WORKSPACE_FILES_DIRECTORY = "files"
SHARED_FILES_ROOT = "shared"

WORKSPACE_AGENT_ROOT_GUIDANCE = (
    "Workspace path areas:\n"
    "- vault: default workspace files. Stored on Vault. Agents can read and write.\n"
    "- shared and local are dynamic. Do not assume folder names. "
    "List workspace_root or list shared/ and local/ and use only the mounts returned. "
    "Then list nested directories under those live paths. Write shared/ only when permission allows.\n"
    "- Voice can list, read, and search whatever browser-linked local mounts exist while this Vault tab is open. "
    "Helper-linked local mounts are also readable by the Background Agent.\n"
    "- Call workspace_root first. It returns pathAreas.mounts for the current shares and linked folders.\n"
    "- Listings and file reads include pathArea so you can tell which namespace you are in.\n"
    "- Hermes/OpenClaw parity tools: workspace_list_directory, workspace_read_file, workspace_search_files, "
    "workspace_write_file, workspace_save_file, workspace_patch_file, workspace_create_directory, "
    "workspace_move_path, workspace_delete_path, workspace_upload_files.\n"
    "- Use vault/shared/local path prefixes on every tool call.\n"
    "- Read WORKSPACE.md at the workspace root for the current workspace layout."
)

WORKSPACE_SEED_MARKDOWN = """# Workspace

Your files live in this workspace under the authorized files root.

- **Vault** paths are the default (for example `notes/today.md`).
- **Shared** paths start with `shared/{owner}/{mount}/...` for whatever folders other users currently share with you.
- **Local** paths start with `local/{mount}/...` for whatever computer folders are currently linked in Settings.
- List `shared/` and `local/` to see the live mounts; do not assume fixed folder names.
- The browser file browser, Voice Agent, and Background Agent all use the same tree.
- Agents should call `workspace_root` to see the current mounts.
"""

