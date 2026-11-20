"""Live memory on/off and live tool routing on/off, per person."""
from __future__ import annotations

from typing import Mapping
from urllib.parse import SplitResult

from app.vault_runtime.local_identity.repository import LocalIdentityError
from app.vault_runtime.live_memory.preferences import PreferenceConflictError
from .common import LocalApiResponse, _csrf_token, _json_object, _session_token


class LiveMemoryRoutes:
    """VaultLocalApiApp routes: live memory on/off and live tool routing on/off, per person."""

    def _route_live_memory(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_live_memory(
                method=method.upper(), headers=headers, body=body,
            )
        except (LocalIdentityError, PreferenceConflictError, ValueError) as exc:
            code = getattr(exc, "code", "invalid_request")
            status = (409 if isinstance(exc, PreferenceConflictError) else
                      400 if isinstance(exc, ValueError) else
                      401 if code in {"invalid_credentials", "local_session_invalid"} else 403)
            return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}},
                                    (("Cache-Control", "no-store"),))

    def _handle_live_memory(self, *, method: str, headers: Mapping[str, str],
                            body: bytes) -> LocalApiResponse:
        no_store = (("Cache-Control", "no-store"),)
        identity, preferences = self._identity_service, self._live_memory_preferences
        if identity is None or preferences is None:
            return LocalApiResponse(503, {"error": {"code": "live_memory_unavailable"}}, no_store)
        principal = identity.authenticate(session_token=_session_token(headers))
        if method == "GET":
            preference = preferences.get(principal)
        elif method == "POST":
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            payload = _json_object(body)
            if set(payload) != {"enabled", "expectedEpoch"}:
                raise ValueError("Expected only enabled and expectedEpoch.")
            preference = preferences.set(principal, enabled=payload["enabled"],
                                         expected_epoch=payload["expectedEpoch"])
            if self._live_memory_invalidator is not None:
                try:
                    self._live_memory_invalidator(preference)
                except Exception:
                    return LocalApiResponse(503, {"error": {"code": "live_memory_invalidation_failed"},
                        "enabled": preference.enabled, "epoch": preference.epoch}, no_store)
        else:
            return LocalApiResponse(404, {"error": {"code": "not_found"}}, no_store)
        return LocalApiResponse(200, {"enabled": preference.enabled, "epoch": preference.epoch}, no_store)

    def _route_live_tool_routing(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_tool_routing(method=method.upper(), headers=headers, body=body)
        except (LocalIdentityError, ValueError) as exc:
            code = getattr(exc, "code", "invalid_request")
            status = (400 if isinstance(exc, ValueError) else
                      401 if code in {"invalid_credentials", "local_session_invalid"} else 403)
            return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}},
                                    (("Cache-Control", "no-store"),))

    def _handle_tool_routing(self, *, method: str, headers: Mapping[str, str], body: bytes) -> LocalApiResponse:
        """Live tool routing on/off (per person), plus whether it can run (needs an OpenAI API key)."""
        no_store = (("Cache-Control", "no-store"),)
        identity, routing = self._identity_service, self._tool_routing
        if identity is None or routing is None:
            return LocalApiResponse(503, {"error": {"code": "tool_routing_unavailable"}}, no_store)
        principal = identity.authenticate(session_token=_session_token(headers))
        if method == "GET":
            return LocalApiResponse(200, routing.status(principal).payload(), no_store)
        if method == "POST":
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
            payload = _json_object(body)
            if set(payload) != {"enabled"}:
                raise ValueError("Expected only enabled.")
            return LocalApiResponse(200, routing.set(principal, enabled=payload["enabled"]).payload(), no_store)
        return LocalApiResponse(404, {"error": {"code": "not_found"}}, no_store)
