"""Workspace files: browse, read, write, move, upload and shares."""
from __future__ import annotations

import logging
from typing import Mapping
from urllib.parse import SplitResult, parse_qs

from app.vault_runtime.workspace_files.errors import WorkspaceFileError
from app.vault_runtime.workspace_files.manager import WorkspaceFileUpload
from app.vault_runtime.workspace_files.multipart import parse_multipart_form
from .common import (
    API_LOGGER,
    LocalApiResponse,
    _csrf_token,
    _json_object,
    _optional_text,
    _query_param,
    _required_bool,
    _required_query,
    _required_text,
    _session_token,
    _workspace_error_status,
)


class WorkspaceFileRoutes:
    """VaultLocalApiApp routes: workspace files: browse, read, write, move, upload and shares."""

    def _route_workspace_files(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_workspace_files(
                method=method.upper(), path=path, query=target_parts.query,
                headers=headers, body=body,
            )
        except WorkspaceFileError as exc:
            return LocalApiResponse(_workspace_error_status(exc), {"error": {"code": exc.code, "message": str(exc)}})
        except ValueError as exc:
            return LocalApiResponse(400, {"error": {"code": "invalid_request", "message": str(exc)}})
        except Exception as exc:
            from app.vault_runtime.local_identity.repository import LocalSessionError

            if isinstance(exc, LocalSessionError):
                return LocalApiResponse(401, {"error": {"code": "unauthorized", "message": str(exc)}})
            logging.getLogger(API_LOGGER).exception("workspace-files request failed")
            return LocalApiResponse(500, {"error": {"code": "workspace_request_failed", "message": "Workspace request failed."}})

    def _handle_workspace_files(
        self, *, method: str, path: str, query: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        service = self._workspace_files
        identity = self._identity_service
        if service is None or identity is None:
            raise RuntimeError("Workspace files are unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        params = parse_qs(query, keep_blank_values=True)
        share_id = _query_param(params, "shareId")
        if method == "GET" and path == "/workspace-files":
            directory = _query_param(params, "directory")
            listing = service.list_directory(principal=principal, directory=directory, share_id=share_id)
            return LocalApiResponse(200, listing.to_dict())
        if method == "GET" and path == "/workspace-files/read":
            file_key = _required_query(params, "fileKey")
            read_back = service.read_file(principal=principal, file_key=file_key, share_id=share_id)
            return LocalApiResponse(200, read_back.to_dict())
        if method == "GET" and path == "/workspace-files/download":
            file_key = _required_query(params, "fileKey")
            filename, media_type, content = service.read_file_bytes(
                principal=principal, file_key=file_key, share_id=share_id,
            )
            safe_filename = filename.replace('"', "")
            return LocalApiResponse(
                200, {}, body=content, content_type=media_type,
                headers=(("Content-Disposition", f'attachment; filename="{safe_filename}"'),),
            )
        if method == "GET" and path == "/workspace-files/shares":
            folder_path = _required_query(params, "folderPath")
            items = service.list_shares(principal=principal, folder_path=folder_path)
            return LocalApiResponse(200, {"items": [item.to_dict() for item in items]})
        if method in {"POST", "PUT", "DELETE"}:
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        if method == "PUT" and path == "/workspace-files/files":
            payload = _json_object(body)
            result = service.save_file(
                principal=principal,
                file_key=_required_text(payload, "fileKey"),
                content_markdown=_required_text(payload, "contentMarkdown"),
                share_id=share_id or _optional_text(payload, "shareId"),
            )
            return LocalApiResponse(200, result.to_dict())
        if method == "POST" and path == "/workspace-files/text":
            payload = _json_object(body)
            result = service.write_text_file(
                principal=principal,
                file_key=_required_text(payload, "fileKey"),
                content_markdown=str(payload.get("contentMarkdown") or ""),
                share_id=share_id or _optional_text(payload, "shareId"),
            )
            return LocalApiResponse(201, result.to_dict())
        if method == "POST" and path == "/workspace-files/directories":
            payload = _json_object(body)
            result = service.create_directory(
                principal=principal,
                directory=_required_text(payload, "directory"),
                share_id=share_id or _optional_text(payload, "shareId"),
            )
            return LocalApiResponse(201, result.to_dict())
        if method == "POST" and path == "/workspace-files/move":
            payload = _json_object(body)
            result = service.move_path(
                principal=principal,
                source_path=_required_text(payload, "sourcePath"),
                destination_path=_required_text(payload, "destinationPath"),
                share_id=share_id or _optional_text(payload, "shareId"),
            )
            return LocalApiResponse(200, result.to_dict())
        if method == "POST" and path == "/workspace-files/delete":
            payload = _json_object(body)
            result = service.delete_path(
                principal=principal,
                path=_required_text(payload, "path"),
                recursive=_required_bool(payload, "recursive"),
                share_id=share_id or _optional_text(payload, "shareId"),
            )
            return LocalApiResponse(200, result.to_dict())
        if method == "POST" and path == "/workspace-files/upload":
            content_type = headers.get("Content-Type") or headers.get("content-type") or ""
            if "multipart/form-data" not in content_type.lower():
                raise ValueError("Workspace upload requires multipart form data.")
            fields, files = parse_multipart_form(body, content_type)
            uploads = [
                WorkspaceFileUpload(filename=filename, content=content)
                for field_name, filename, content in files
                if field_name == "files"
            ]
            result = service.upload_files(
                principal=principal,
                directory=fields.get("directory") or None,
                uploads=uploads,
                share_id=share_id or fields.get("shareId"),
            )
            return LocalApiResponse(201, result.to_dict())
        if method == "POST" and path == "/workspace-files/shares":
            payload = _json_object(body)
            item = service.save_share(
                principal=principal,
                folder_path=_required_text(payload, "folderPath"),
                grantee_user_id=_required_text(payload, "granteeUserId"),
                permission=_required_text(payload, "permission"),
            )
            return LocalApiResponse(200, item.to_dict())
        if method == "POST" and path.startswith("/workspace-files/shares/") and path.endswith("/revoke"):
            share_id_value = path.removeprefix("/workspace-files/shares/").removesuffix("/revoke").strip("/")
            service.revoke_share(principal=principal, share_id=share_id_value)
            return LocalApiResponse(200, {"status": "revoked"})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
