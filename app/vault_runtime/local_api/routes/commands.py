"""Commands: the global switch and the Run / Don't run decision."""
from __future__ import annotations

from typing import Mapping
from urllib.parse import SplitResult, parse_qs

from app.vault_runtime.workspace_files.errors import WorkspaceFileError
from .common import (
    LocalApiResponse,
    _csrf_token,
    _id_action,
    _json_object,
    _required_bool,
    _required_query,
    _session_token,
    _workspace_error_status,
)


class CommandRoutes:
    """VaultLocalApiApp routes: commands: the global switch and the run / don't run decision."""

    def _route_commands(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_commands(
                method=method.upper(), path=path, query=target_parts.query, headers=headers, body=body,
            )
        except WorkspaceFileError as exc:
            return LocalApiResponse(_workspace_error_status(exc), {"error": {"code": exc.code, "message": str(exc)}})
        except ValueError as exc:
            return LocalApiResponse(400, {"error": {"code": "invalid_request", "message": str(exc)}})
        except Exception as exc:
            code = getattr(exc, "code", "commands_request_failed")
            return LocalApiResponse(403, {"error": {"code": code, "message": str(exc)}})

    def _handle_commands(
        self, *, method: str, path: str, query: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        """Commands: the global switch (master account) and the person's Run / Don't run decision in Chat."""
        service = self._commands
        identity = self._identity_service
        if service is None or identity is None:
            raise RuntimeError("Commands are unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        no_store = (("Cache-Control", "no-store"),)
        if method == "GET" and path == "/commands/settings":
            return LocalApiResponse(200, service.settings(), no_store)
        if method == "GET" and path == "/commands/pending":
            conversation_id = _required_query(parse_qs(query, keep_blank_values=True), "conversationId")
            return LocalApiResponse(200, {"items": service.pending(principal=principal, conversation_id=conversation_id)},
                                    no_store)
        if method != "POST":
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        payload = _json_object(body)
        if path == "/admin/commands/settings":
            return LocalApiResponse(200, service.set_enabled(
                principal=principal, enabled=_required_bool(payload, "enabled"),
            ), no_store)
        request_id, action = _id_action(path, "/commands/")
        if request_id and action in {"approve", "deny"}:
            return LocalApiResponse(200, service.decide(
                principal=principal, request_id=request_id, approve=action == "approve",
            ), no_store)
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
