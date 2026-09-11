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
    "- vault: default workspace files (example notes/today.md). Stored on Vault. Agents can read and write.\n"
    "- shared: other users' shares (example shared/alice/Reports/file.pdf). Paths start with shared/. "
    "Write only when the share permission allows it.\n"
    "- local: linked computer folders (example local/Documents/invoice.pdf). Paths start with local/. "
    "Helper-linked mounts are agent-readable; browser-linked mounts are listed but not readable server-side.\n"
    "- Call workspace_root first. It returns pathAreas with descriptors, examples, mounts, and the tool catalog.\n"
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
- **Shared** paths start with `shared/{owner}/{mount}/...` for folders other users shared with you.
- **Local** paths start with `local/{mount}/...` for computer folders linked in Settings.
- The browser file browser, Voice Agent, and Background Agent all use the same tree.
- Agents should call `workspace_root` to see path area descriptors and available mounts.
"""

