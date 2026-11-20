"""Local contacts."""
from __future__ import annotations

from typing import Mapping
from urllib.parse import SplitResult
from uuid import uuid4

from app.vault_runtime.session_tools.brokers.contacts import contacts_tool_result
from .common import LocalApiResponse, _csrf_token, _json_object, _session_token


class ContactRoutes:
    """VaultLocalApiApp routes: local contacts."""

    def _route_contacts(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_contacts(method=method.upper(), path=path, headers=headers, body=body)
        except Exception as exc:
            code = getattr(exc, "code", "contacts_request_failed")
            return LocalApiResponse(400 if isinstance(exc, ValueError) else 403,
                                    {"error": {"code": code, "message": str(exc)}})

    def _handle_contacts(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        identity, store = self._identity_service, self._personal_data
        if identity is None or store is None:
            raise RuntimeError("Local Contacts is unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method == "GET" and path == "/contacts":
            items = store.list_private_records(
                account_id=principal.user_id, workspace_id=principal.workspace_id,
                source_table="contacts_entries", limit=250,
            )
            return LocalApiResponse(200, {"items": items})
        if method != "POST":
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        payload = _json_object(body)
        operation = path.removeprefix("/contacts/")
        tool_name = {
            "search": "contacts_search", "prepare": "contacts_prepare_save",
            "confirm": "contacts_confirm_pending",
        }.get(operation)
        if tool_name is None:
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        result = contacts_tool_result(
            store=store, account_id=principal.user_id, workspace_id=principal.workspace_id,
            voice_realtime_session_id="web-management", tool_call_id=str(uuid4()),
            tool_name=tool_name, arguments=payload,
        )
        return LocalApiResponse(200, result)
