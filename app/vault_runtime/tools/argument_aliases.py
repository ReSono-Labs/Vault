from __future__ import annotations

from collections.abc import Iterable

_PATH_ALIASES = ("path", "dir", "folder", "target", "file_path", "filePath", "file_key", "fileKey")

# Fields kept when the caller has no schema to hand. The catalog passes the tool's own
# schema fields, so these lists never hide a field the tool declares.
_TOOL_FIELDS: dict[str, tuple[str, ...]] = {
    "workspace_list_directory": ("directory", "shareId"),
    "workspace_read_file": ("fileKey", "startLine", "endLine", "head", "tail", "shareId"),
    "workspace_search_files": (
        "query", "directory", "limit", "regex", "caseSensitive", "include", "exclude",
        "contextLines", "maxPerFile", "namesOnly", "shareId",
    ),
    "workspace_write_file": ("fileKey", "content", "overwriteExisting", "shareId"),
    "workspace_save_file": ("fileKey", "contentMarkdown", "overwriteExisting", "shareId"),
    "workspace_patch_file": ("fileKey", "oldString", "newString", "replaceAll", "shareId"),
    "workspace_create_directory": ("directory", "shareId"),
    "workspace_move_path": ("sourcePath", "destinationPath", "shareId"),
    "workspace_delete_path": ("path", "recursive", "shareId"),
    "workspace_upload_files": ("directory", "files", "shareId"),
    "workspace_root": ("shareId",),
    "workspace_read_files": ("fileKeys", "shareId"),
    "workspace_glob": ("pattern", "directory", "shareId"),
    "workspace_tree": ("directory", "depth", "shareId"),
    "workspace_file_info": ("path", "shareId"),
    "workspace_copy_path": ("sourcePath", "destinationPath", "shareId"),
}

_PATH_FIELDS = ("fileKey", "directory", "path", "sourcePath", "destinationPath")
# Vault's own files have no prefix, but models name the area "vault" (vault/notes.md,
# vault://notes.md). Like shared/ and local/, a top-level "vault" means the area itself.
_VAULT_AREA_PREFIXES = ("vault://", "vault:/", "vault:", "vault/")


def _strip_vault_area(value: object) -> object:
    if not isinstance(value, str):
        return value
    text = value.strip()
    lowered = text.casefold()
    if lowered == "vault":
        return ""
    for prefix in _VAULT_AREA_PREFIXES:
        if lowered.startswith(prefix):
            return text[len(prefix):].lstrip("/")
    return value

# Other spellings models use for the same field: target field -> accepted spellings.
_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "contentMarkdown": ("content", "content_markdown", "text", "body"),
    "content": ("contentMarkdown", "content_markdown", "text", "body"),
    "oldString": ("old_string", "old", "oldText", "old_text", "search"),
    "newString": ("new_string", "new", "newText", "new_text", "replacement", "replace"),
    "replaceAll": ("replace_all",),
    "overwriteExisting": ("overwrite_existing", "overwrite"),
    "startLine": ("start_line",),
    "endLine": ("end_line",),
    "caseSensitive": ("case_sensitive",),
    "contextLines": ("context_lines",),
    "maxPerFile": ("max_per_file",),
    "namesOnly": ("names_only",),
    "shareId": ("share_id",),
}


def normalize_tool_arguments(
    name: object, arguments: object, *, schema_fields: Iterable[str] | None = None,
) -> object:
    if not isinstance(name, str) or not isinstance(arguments, dict):
        return arguments
    known = _TOOL_FIELDS.get(name)
    if known is None:
        return arguments
    allowed = set(known) | set(schema_fields or ())
    raw = {str(key): value for key, value in arguments.items() if value is not None}
    normalized: dict[str, object] = {}
    for key, value in raw.items():
        if key in allowed:
            normalized[key] = value
    for field, spellings in _FIELD_ALIASES.items():
        if field not in allowed or field in normalized:
            continue
        for alias in spellings:
            if alias in raw and alias not in allowed:
                normalized[field] = raw[alias]
                break
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
    if "shareId" not in normalized:   # inside a share, paths are relative to that share
        for field in _PATH_FIELDS:
            if field in normalized:
                normalized[field] = _strip_vault_area(normalized[field])
        keys = normalized.get("fileKeys")
        if isinstance(keys, list):
            normalized["fileKeys"] = [_strip_vault_area(key) for key in keys]
    return normalized
