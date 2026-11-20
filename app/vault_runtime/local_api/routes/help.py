"""Vault Help questions."""
from __future__ import annotations

import httpx
from typing import Mapping
from urllib.parse import SplitResult

from app.vault_runtime.help_assistant import HelpAssistantError
from .common import LocalApiResponse, _csrf_token, _json_object, _required_text, _session_token


class HelpRoutes:
    """VaultLocalApiApp routes: vault help questions."""

    def _route_help(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_help(
                method=method.upper(), path=path, headers=headers, body=body,
            )
        except Exception as exc:
            code = getattr(exc, "code", "help_request_failed")
            status = 502 if isinstance(exc, (HelpAssistantError, httpx.HTTPError)) else 400 if isinstance(exc, ValueError) else 403
            return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})

    def _handle_help(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        identity, assistant = self._identity_service, self._help_assistant
        if identity is None or assistant is None:
            raise RuntimeError("Vault Help is unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method != "POST" or path != "/help/ask":
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        payload = _json_object(body)
        raw_history = payload.get("history", [])
        if not isinstance(raw_history, list) or len(raw_history) > 8:
            raise ValueError("Help conversation history is invalid.")
        history: list[dict[str, str]] = []
        for item in raw_history:
            if not isinstance(item, dict) or not isinstance(item.get("role"), str) or not isinstance(item.get("content"), str):
                raise ValueError("Help conversation history is invalid.")
            history.append({"role": item["role"], "content": item["content"]})
        return LocalApiResponse(200, assistant.ask(
            principal,
            message=_required_text(payload, "message"),
            history=tuple(history),
            allow_web=bool(payload.get("searchWeb", False)),
        ))
