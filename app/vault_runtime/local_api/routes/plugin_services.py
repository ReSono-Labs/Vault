"""Plugin services called by imported plugins with their bearer token."""
from __future__ import annotations

from typing import Mapping
from urllib.parse import SplitResult
from .common import LocalApiResponse, _bearer_token, _header, _json_object


class PluginServiceRoutes:
    """VaultLocalApiApp routes: plugin services called by imported plugins with their bearer token."""

    def _route_plugin_services(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_plugin_services(
                method=method.upper(), path=path, headers=headers, body=body,
            )
        except Exception as exc:
            code = getattr(exc, "code", "plugin_service_request_failed")
            return LocalApiResponse(
                400 if isinstance(exc, ValueError) else 403,
                {"error": {"code": code, "message": str(exc)}},
                (("Cache-Control", "no-store"),),
            )

    def _handle_plugin_services(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        service = self._plugin_services
        if service is None:
            raise RuntimeError("Plugin services are unavailable.")
        if method != "POST":
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        names = {
            "/plugin-services/v1/memory/search": "memory.search",
            "/plugin-services/v1/memory/propose": "memory.propose",
            "/plugin-services/v1/context/locale": "context.locale",
            "/plugin-services/v1/activity/report": "activity.report",
        }
        name = names.get(path)
        if name is None:
            return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
        invocation_id = (_header(headers, "x-vault-invocation-id") or "").strip()
        if not invocation_id or len(invocation_id) > 256:
            raise ValueError("Vault invocation identifier is required")
        status, payload = service.call(
            token=_bearer_token(headers), invocation_id=invocation_id,
            service=name, payload=_json_object(body),
        )
        return LocalApiResponse(status, payload, (("Cache-Control", "no-store"),))
