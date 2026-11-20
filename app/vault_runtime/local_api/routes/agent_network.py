"""Agent2Agent connections, notifications and the inbound listener."""
from __future__ import annotations

from typing import Mapping
from urllib.parse import SplitResult

from app.vault_runtime.agent_network.tools import agent2agent_option_on
from .common import LocalApiResponse, _csrf_token, _json_object, _required_text, _session_token


class AgentNetworkRoutes:
    """VaultLocalApiApp routes: agent2agent connections, notifications and the inbound listener."""

    def _route_agent2agent(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_agent2agent(method=method.upper(), path=path, headers=headers, body=body)
        except Exception as exc:
            code = getattr(exc, "code", "a2a_request_failed")
            return LocalApiResponse(400 if isinstance(exc, ValueError) else 502, {"error": {"code": code, "message": str(exc)}})

    def _handle_agent2agent(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        identity, service = self._identity_service, self._a2a_service
        if identity is None or service is None:
            raise RuntimeError("Agent2Agent is unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method == "POST" and path == "/agent2agent/connections":
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            if not agent2agent_option_on(self._builtin_plugins, principal.user_id, principal.workspace_id):
                raise ValueError("Agent2Agent is turned off.")
            payload = _json_object(body)
            item = service.connect(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                display_name=_required_text(payload, "displayName"),
                card_url=_required_text(payload, "cardUrl"),
                token=str(payload.get("token") or ""),
            )
            return LocalApiResponse(201, {"connectionId": item.connection_id, "displayName": item.display_name,
                "cardUrl": item.card_url, "enabled": item.enabled, "agentCard": item.agent_card})
        repository = service.repository
        if method == "GET" and path == "/agent2agent/connections":
            return LocalApiResponse(200, {"items": [{
                "connectionId": item.connection_id, "displayName": item.display_name,
                "cardUrl": item.card_url, "enabled": item.enabled,
                "agentCard": item.agent_card,
            } for item in repository.list(user_id=principal.user_id, workspace_id=principal.workspace_id)]})
        if method == "GET" and path == "/agent2agent/notifications":
            return LocalApiResponse(200, {"items": list(repository.notifications(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
            ))})
        if method == "GET" and path == "/agent2agent/listen":
            if not agent2agent_option_on(self._builtin_plugins, principal.user_id, principal.workspace_id):
                raise ValueError("Agent2Agent is turned off.")
            info = service.listen_info(user_id=principal.user_id, workspace_id=principal.workspace_id)
            # The page polls this; never send the bearer itself, only enough to recognise it.
            token = str(info.get("token") or "")
            return LocalApiResponse(200, {"cardUrl": info["cardUrl"], "rpcUrl": info["rpcUrl"], "tokenHint": token[-4:]})
        if method == "POST" and path == "/agent2agent/listen/token":
            # Show/Copy only: an explicit, CSRF-checked request for the bearer.
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            if not agent2agent_option_on(self._builtin_plugins, principal.user_id, principal.workspace_id):
                raise ValueError("Agent2Agent is turned off.")
            info = service.listen_info(user_id=principal.user_id, workspace_id=principal.workspace_id)
            return LocalApiResponse(200, {"token": info["token"]}, (("Cache-Control", "no-store"),))
        if method == "POST" and path == "/agent2agent/listen/rotate":
            # Make a new inbound bearer; the old one stops working at once. Owner-only (repository scope).
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            if not agent2agent_option_on(self._builtin_plugins, principal.user_id, principal.workspace_id):
                raise ValueError("Agent2Agent is turned off.")
            info = service.rotate_listen_token(user_id=principal.user_id, workspace_id=principal.workspace_id)
            return LocalApiResponse(200, {"cardUrl": info["cardUrl"], "rpcUrl": info["rpcUrl"],
                                          "tokenHint": str(info["token"])[-4:]}, (("Cache-Control", "no-store"),))
        if method == "DELETE" and path.startswith("/agent2agent/connections/"):
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            repository.remove(user_id=principal.user_id, workspace_id=principal.workspace_id,
                              connection_id=path.removeprefix("/agent2agent/connections/").strip("/"))
            return LocalApiResponse(200, {"status": "removed"})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
