"""Notifications: list and clear."""
from __future__ import annotations

from typing import Mapping
from urllib.parse import SplitResult
from .common import LocalApiResponse, _csrf_token, _session_token


class NotificationRoutes:
    """VaultLocalApiApp routes: notifications: list and clear."""

    def _route_notifications(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_notifications(method=method.upper(), path=path, headers=headers, body=body)
        except ValueError as exc:
            return LocalApiResponse(400, {"error": {"code": "invalid_request", "message": str(exc)}})
        except PermissionError as exc:
            return LocalApiResponse(403, {"error": {"code": "forbidden", "message": str(exc)}})

    def _handle_notifications(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        repository = self._notifications
        identity = self._identity_service
        if repository is None or identity is None:
            raise RuntimeError("Notifications are unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method in {"POST", "DELETE"}:
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        if method == "GET" and path == "/notifications":
            items = repository.list_active(user_id=principal.user_id, workspace_id=principal.workspace_id)
            return LocalApiResponse(200, {"items": items, "unreadCount": len(items)})
        if method == "POST" and path == "/notifications/clear":
            count = repository.dismiss_all(user_id=principal.user_id, workspace_id=principal.workspace_id)
            return LocalApiResponse(200, {"status": "cleared", "clearedCount": count})
        if method == "POST" and path.startswith("/notifications/") and path.endswith("/clear"):
            notification_id = path.removeprefix("/notifications/").removesuffix("/clear").strip("/")
            if not notification_id:
                raise ValueError("Notification id is required.")
            cleared = repository.dismiss(
                user_id=principal.user_id, workspace_id=principal.workspace_id, notification_id=notification_id,
            )
            if not cleared:
                return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Notification was not found."}})
            return LocalApiResponse(200, {"status": "cleared", "notificationId": notification_id})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
