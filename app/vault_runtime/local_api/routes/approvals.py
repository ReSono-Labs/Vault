"""Owner approvals on the website: waiting questions and their answer."""
from __future__ import annotations

from typing import Mapping
from urllib.parse import SplitResult
from .common import LocalApiResponse, _csrf_token, _id_action, _json_object, _required_text, _session_token


class ApprovalRoutes:
    """VaultLocalApiApp routes: owner approvals on the website: waiting questions and their answer."""

    def _route_approvals(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_approvals(method=method.upper(), path=path, headers=headers, body=body)
        except Exception as exc:
            from app.vault_runtime.background_agent.errors import (
                BackgroundRunAuthorizationError, BackgroundRunConflictError)
            if isinstance(exc, BackgroundRunConflictError):
                return LocalApiResponse(409, {"error": {"code": "approval_already_answered", "message": str(exc)}})
            if isinstance(exc, BackgroundRunAuthorizationError):
                return LocalApiResponse(404, {"error": {"code": "approval_unavailable", "message": "Not found."}})
            if isinstance(exc, ValueError):
                return LocalApiResponse(400, {"error": {"code": "invalid_approval_answer", "message": str(exc)}})
            # Sign-in and CSRF failures (as the Commands routes answer them).
            return LocalApiResponse(403, {"error": {"code": getattr(exc, "code", "approvals_request_failed"),
                                                    "message": str(exc)}})

    def _handle_approvals(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        """Owner approvals on the website: the signed-in account's own waiting questions and its answer.
        GET /approvals; POST /approvals/<id>/decision {"choice": "allow_once" | "deny"}."""
        runtime = self._conversation_runtime
        approvals = getattr(runtime, "approvals", None) if runtime is not None else None
        if approvals is None:
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        identity = self._identity_service
        principal = identity.authenticate(session_token=_session_token(headers))
        no_store = (("Cache-Control", "no-store"),)
        if method == "GET" and path == "/approvals":
            return LocalApiResponse(200, {"items": approvals.waiting(principal)}, no_store)
        approval_id, action = _id_action(path, "/approvals/")
        if method != "POST" or not approval_id or action != "decision":
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        payload = _json_object(body)
        if set(payload) - {"choice"}:
            raise ValueError("Only choice is accepted")
        result = approvals.answer(principal, approval_id, _required_text(payload, "choice"), channel="browser")
        return LocalApiResponse(200, {"id": approval_id, "result": result}, no_store)
