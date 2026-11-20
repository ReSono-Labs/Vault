"""Active tasks."""
from __future__ import annotations

from typing import Mapping
from urllib.parse import SplitResult

from app.vault_runtime.tasks.repository import task_view
from .common import LocalApiResponse, _session_token


class TaskRoutes:
    """VaultLocalApiApp routes: active tasks."""

    def _route_tasks(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_tasks(method=method.upper(), path=path, headers=headers)
        except ValueError as exc:
            return LocalApiResponse(400, {"error": {"code": "invalid_request", "message": str(exc)}})
        except PermissionError as exc:
            return LocalApiResponse(403, {"error": {"code": "forbidden", "message": str(exc)}})

    def _handle_tasks(self, *, method: str, path: str, headers: Mapping[str, str]) -> LocalApiResponse:
        repository = self._tasks
        identity = self._identity_service
        if repository is None or identity is None:
            raise RuntimeError("Tasks are unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        if method == "GET" and path == "/tasks/active":
            items = repository.list_active(user_id=principal.user_id, workspace_id=principal.workspace_id)
            return LocalApiResponse(200, {"tasks": [task_view(item) for item in items]})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
