const PATH_ALIASES = ["path", "dir", "folder", "target", "file_path", "filePath", "file_key", "fileKey"] as const;

const TOOL_FIELDS: Record<string, readonly string[]> = {
  workspace_list_directory: ["directory", "shareId"],
  workspace_read_file: ["fileKey", "shareId"],
  workspace_search_files: ["query", "directory", "limit", "shareId"],
  workspace_write_file: ["fileKey", "content", "overwriteExisting", "shareId"],
  workspace_save_file: ["fileKey", "content", "shareId"],
  workspace_patch_file: ["fileKey", "old_string", "new_string", "replaceAll", "shareId"],
  workspace_create_directory: ["directory", "shareId"],
  workspace_move_path: ["sourcePath", "destinationPath", "shareId"],
  workspace_delete_path: ["path", "recursive", "shareId"],
  workspace_upload_files: ["directory", "files", "shareId"],
  workspace_root: ["shareId"],
};

export function normalizeWorkspaceToolArguments(
  name: string,
  argumentsValue: Record<string, unknown>,
): Record<string, unknown> {
  const allowed = TOOL_FIELDS[name];
  if (!allowed) {
    return argumentsValue;
  }
  const raw: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(argumentsValue)) {
    if (value !== null && value !== undefined) {
      raw[key] = value;
    }
  }
  const normalized: Record<string, unknown> = {};
  for (const key of allowed) {
    if (key in raw) {
      normalized[key] = raw[key];
    }
  }
  if (allowed.includes("directory") && !("directory" in normalized)) {
    for (const alias of PATH_ALIASES) {
      if (alias !== "fileKey" && alias in raw) {
        normalized.directory = raw[alias];
        break;
      }
    }
  }
  if (allowed.includes("fileKey") && !("fileKey" in normalized)) {
    for (const alias of ["file_key", "fileKey", "path", "file_path", "filePath", "target"]) {
      if (alias in raw) {
        normalized.fileKey = raw[alias];
        break;
      }
    }
  }
  if (allowed.includes("path") && !("path" in normalized)) {
    for (const alias of ["fileKey", "file_key", "directory", "target"]) {
      if (alias in raw) {
        normalized.path = raw[alias];
        break;
      }
    }
  }
  if (allowed.includes("query") && !("query" in normalized)) {
    const query = raw.q ?? raw.search ?? raw.text;
    if (query !== undefined) {
      normalized.query = query;
    }
  }
  if ("limit" in normalized) {
    const limit = Number(normalized.limit);
    if (Number.isFinite(limit)) {
      normalized.limit = Math.trunc(limit);
    } else {
      delete normalized.limit;
    }
  }
  if (typeof normalized.shareId === "string" && !normalized.shareId.trim()) {
    delete normalized.shareId;
  }
  return normalized;
}

export function workspaceToolPath(name: string, args: Record<string, unknown>): string {
  const normalized = normalizeWorkspaceToolArguments(name, args);
  if (name === "workspace_read_file") {
    return String(normalized.fileKey || "").trim();
  }
  if (name === "workspace_delete_path") {
    return String(normalized.path || "").trim();
  }
  return String(normalized.directory || "").trim();
}
