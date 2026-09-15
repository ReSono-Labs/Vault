from __future__ import annotations

_PATH_ALIASES = ("path", "dir", "folder", "target", "file_path", "filePath", "file_key", "fileKey")

_TOOL_FIELDS: dict[str, tuple[str, ...]] = {
    "workspace_list_directory": ("directory", "shareId"),
    "workspace_read_file": ("fileKey", "shareId"),
    "workspace_search_files": ("query", "directory", "limit", "shareId"),
    "workspace_write_file": ("fileKey", "content", "overwriteExisting", "shareId"),
    "workspace_save_file": ("fileKey", "content", "shareId"),
    "workspace_patch_file": ("fileKey", "old_string", "new_string", "replaceAll", "shareId"),
    "workspace_create_directory": ("directory", "shareId"),
    "workspace_move_path": ("sourcePath", "destinationPath", "shareId"),
    "workspace_delete_path": ("path", "recursive", "shareId"),
    "workspace_upload_files": ("directory", "files", "shareId"),
    "workspace_root": ("shareId",),
}


def normalize_tool_arguments(name: object, arguments: object) -> object:
    if not isinstance(name, str) or not isinstance(arguments, dict):
        return arguments
    allowed = _TOOL_FIELDS.get(name)
    if allowed is None:
        return arguments
    raw = {str(key): value for key, value in arguments.items() if value is not None}
    normalized: dict[str, object] = {}
    for key, value in raw.items():
        if key in allowed:
            normalized[key] = value
    if "directory" in allowed and "directory" not in normalized:
        for alias in _PATH_ALIASES:
            if alias in raw and alias != "fileKey":
                normalized["directory"] = raw[alias]
                break
    if "fileKey" in allowed and "fileKey" not in normalized:
        for alias in ("file_key", "fileKey", "path", "file_path", "filePath", "target"):
            if alias in raw:
                normalized["fileKey"] = raw[alias]
                break
    if "path" in allowed and "path" not in normalized:
        for alias in ("fileKey", "file_key", "directory", "target"):
            if alias in raw:
                normalized["path"] = raw[alias]
                break
    if "query" in allowed and "query" not in normalized:
        query = raw.get("q") or raw.get("search") or raw.get("text")
        if query is not None:
            normalized["query"] = query
    if "limit" in allowed and "limit" in normalized:
        try:
            normalized["limit"] = int(normalized["limit"])  # type: ignore[arg-type]
        except (TypeError, ValueError):
            normalized.pop("limit", None)
    share_id = normalized.get("shareId")
    if isinstance(share_id, str) and not share_id.strip():
        normalized.pop("shareId", None)
    return normalized
