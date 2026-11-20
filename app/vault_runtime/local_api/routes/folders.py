"""Host folders: the signed-in user's folders and master-account folder access."""
from __future__ import annotations

from typing import Mapping
from urllib.parse import SplitResult, parse_qs

from app.vault_runtime.workspace_files.errors import WorkspaceFileError
from .common import (
    LocalApiResponse,
    _csrf_token,
    _id_action,
    _json_object,
    _optional_text,
    _query_param,
    _required_bool,
    _required_query,
    _required_text,
    _session_token,
    _workspace_error_status,
)


class FolderRoutes:
    """VaultLocalApiApp routes: host folders: the signed-in user's folders and master-account folder access."""

    def _route_folders(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_folders(
                method=method.upper(), path=path, query=target_parts.query,
                headers=headers, body=body,
            )
        except WorkspaceFileError as exc:
            return LocalApiResponse(_workspace_error_status(exc), {"error": {"code": exc.code, "message": str(exc)}})
        except ValueError as exc:
            return LocalApiResponse(400, {"error": {"code": "invalid_request", "message": str(exc)}})
        except Exception as exc:
            code = getattr(exc, "code", "folders_request_failed")
            return LocalApiResponse(403, {"error": {"code": code, "message": str(exc)}})

    def _handle_folders(
        self, *, method: str, path: str, query: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        """Host folders. /folders/* is the signed-in user's own folders; /admin/* is master-account only."""
        service = self._folders
        identity = self._identity_service
        if service is None or identity is None:
            raise RuntimeError("Folders are unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        no_store = (("Cache-Control", "no-store"),)
        if method == "GET":
            params = parse_qs(query, keep_blank_values=True)
            if path == "/folders":
                return LocalApiResponse(200, service.list_folders(principal=principal), no_store)
            if path == "/folders/places":
                return LocalApiResponse(200, {"items": service.places(principal=principal)}, no_store)
            if path == "/folders/browse":
                return LocalApiResponse(200, service.browse(
                    principal=principal, grant_id=_required_query(params, "grantId"),
                    path=_query_param(params, "path"),
                ), no_store)
            if path == "/admin/folders/locations":
                return LocalApiResponse(200, service.admin_locations(principal=principal), no_store)
            if path == "/admin/folders/browse":
                return LocalApiResponse(200, service.admin_browse(
                    principal=principal, location_id=_required_query(params, "locationId"),
                    path=_query_param(params, "path"),
                ), no_store)
            user_id = _folder_access_user(path)
            if user_id:
                return LocalApiResponse(200, {
                    "items": service.list_user_access(principal=principal, user_id=user_id),
                }, no_store)
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        if method != "POST":
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        payload = _json_object(body)
        if path == "/folders":
            item = service.add_folder(
                principal=principal,
                grant_id=_required_text(payload, "grantId"),
                path=_optional_text(payload, "path"),
                name=_required_text(payload, "name"),
                permission=_required_text(payload, "permission"),
                create=bool(payload.get("create")),
                new_folder_name=_optional_text(payload, "newFolderName"),
                include_hidden=payload.get("includeHidden") is True,
            )
            return LocalApiResponse(201, item, no_store)
        if path == "/folders/setup/vault-folder":
            return LocalApiResponse(200, service.setup_vault_folder(principal=principal), no_store)
        if path == "/admin/folders/add":
            item = service.admin_add_folder(
                principal=principal,
                location_id=_required_text(payload, "locationId"),
                path=_optional_text(payload, "path"),
                permission=_required_text(payload, "permission"),
                name=_optional_text(payload, "name"),
                create=bool(payload.get("create")),
                new_folder_name=_optional_text(payload, "newFolderName"),
                include_hidden=payload.get("includeHidden") is True,
            )
            return LocalApiResponse(201, item, no_store)
        if path == "/folders/setup/add":
            item = service.setup_add(
                principal=principal,
                location_id=_required_text(payload, "locationId"),
                path=_optional_text(payload, "path"),
                permission=_required_text(payload, "permission"),
            )
            return LocalApiResponse(201, item, no_store)
        folder_id, action = _id_action(path, "/folders/")
        if folder_id and action == "permission":
            return LocalApiResponse(200, service.set_folder_permission(
                principal=principal, folder_id=folder_id, permission=_required_text(payload, "permission"),
            ), no_store)
        if folder_id and action == "hidden":
            return LocalApiResponse(200, service.set_folder_hidden(
                principal=principal, folder_id=folder_id, include_hidden=_required_bool(payload, "includeHidden"),
            ), no_store)
        if folder_id and action == "remove":
            service.remove_folder(principal=principal, folder_id=folder_id)
            return LocalApiResponse(200, {"status": "removed"}, no_store)
        user_id = _folder_access_user(path)
        if user_id:
            item = service.give_access(
                principal=principal, user_id=user_id,
                location_id=_required_text(payload, "locationId"),
                path=_optional_text(payload, "path"),
                max_permission=_required_text(payload, "maxPermission"),
                include_hidden=payload.get("includeHidden") is True,
            )
            return LocalApiResponse(201, item, no_store)
        grant_id, action = _id_action(path, "/admin/folder-access/")
        if grant_id and action == "permission":
            return LocalApiResponse(200, service.set_access_permission(
                principal=principal, grant_id=grant_id,
                max_permission=_required_text(payload, "maxPermission"),
            ), no_store)
        if grant_id and action == "hidden":
            return LocalApiResponse(200, service.set_access_hidden(
                principal=principal, grant_id=grant_id, include_hidden=_required_bool(payload, "includeHidden"),
            ), no_store)
        if grant_id and action == "remove":
            service.remove_access(principal=principal, grant_id=grant_id)
            return LocalApiResponse(200, {"status": "removed"}, no_store)
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})


def _folder_access_user(path: str) -> str:
    """'/admin/users/{userId}/folder-access' -> '{userId}'."""
    parts = path.strip("/").split("/")
    if len(parts) == 4 and parts[:2] == ["admin", "users"] and parts[3] == "folder-access" and parts[2]:
        return parts[2]
    return ""
