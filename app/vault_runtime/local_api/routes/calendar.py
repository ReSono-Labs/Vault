"""Local calendar accounts and events."""
from __future__ import annotations

from typing import Mapping
from urllib.parse import SplitResult
from .common import LocalApiResponse, _csrf_token, _json_object, _session_token


class CalendarRoutes:
    """VaultLocalApiApp routes: local calendar accounts and events."""

    def _route_calendar(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_calendar(method=method.upper(), path=path, headers=headers, body=body)
        except Exception as exc:
            code = getattr(exc, "code", "calendar_request_failed")
            status = 404 if isinstance(exc, LookupError) else 400 if isinstance(exc, ValueError) else 403
            return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})

    def _handle_calendar(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        identity, runtime = self._identity_service, self._calendar_runtime
        if identity is None or runtime is None:
            raise RuntimeError("Local Calendar is unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method == "GET" and path == "/calendar/accounts":
            return LocalApiResponse(200, {"items": runtime.accounts(principal)})
        if method == "GET" and path == "/calendar/events":
            return LocalApiResponse(200, {"items": runtime.events(principal)})
        if method not in {"POST", "DELETE"}:
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        if method == "POST" and path == "/calendar/accounts":
            payload = _json_object(body)
            return LocalApiResponse(201, runtime.connect(
                principal, payload, validate=bool(payload.get("validateConnection", True)),
            ))
        suffix = path.removeprefix("/calendar/accounts/")
        calendar_account_id, _, operation = suffix.partition("/")
        if method == "POST" and calendar_account_id and operation == "sync":
            return LocalApiResponse(200, runtime.sync(principal, calendar_account_id))
        if method == "DELETE" and calendar_account_id and not operation:
            runtime.remove(principal, calendar_account_id)
            return LocalApiResponse(200, {"status": "removed"})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
