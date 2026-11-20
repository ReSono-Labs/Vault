"""Request and response helpers shared by the local API dispatcher and its route modules."""
from __future__ import annotations

from dataclasses import dataclass
from http.cookies import SimpleCookie
from hmac import compare_digest
from typing import Any, Iterable, Mapping

from app.vault_runtime.tools.strict_json import (
    STRICT_JSON_MAX_BYTES,
    StrictJSONError,
    parse_json_object_bytes,
)
from app.vault_runtime.workspace_files.errors import WorkspaceFileError

API_LOGGER = "app.vault_runtime.local_api.app"


@dataclass(frozen=True, slots=True)
class LocalApiResponse:
    status_code: int
    payload: dict[str, Any]
    headers: tuple[tuple[str, str], ...] = ()
    body: bytes | None = None
    content_type: str | None = None
    stream: Iterable[bytes] | None = None


def _workspace_error_status(exc: WorkspaceFileError) -> int:
    status = getattr(exc, "status", None)
    if isinstance(status, int):
        return status
    return 404 if exc.code == "not_found" else 409 if exc.code == "conflict" else 403 if exc.code == "forbidden" else 400


def _id_action(path: str, prefix: str) -> tuple[str, str]:
    """'/folders/{id}/remove' -> ('{id}', 'remove'); anything else -> ('', '')."""
    if not path.startswith(prefix):
        return "", ""
    parts = path.removeprefix(prefix).strip("/").split("/")
    if len(parts) != 2 or not parts[0] or parts[0] in {"setup", "browse", "places", "settings", "pending"}:
        return "", ""
    return parts[0], parts[1]


def _query_param(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key, [])
    return values[0] if len(values) == 1 and values[0] else None


def _required_query(params: dict[str, list[str]], key: str) -> str:
    value = _query_param(params, key)
    if not value:
        raise ValueError(f"{key} is required.")
    return value


def _json_object(body: bytes, *, max_bytes: int = STRICT_JSON_MAX_BYTES) -> dict[str, Any]:
    try:
        return parse_json_object_bytes(body or b"{}", max_bytes=max_bytes)
    except StrictJSONError as exc:
        if exc.reason == "raw_size":
            raise ValueError(
                "Request body exceeds the upload size limit for this endpoint.",
            ) from exc
        raise ValueError("Request body must be a JSON object.") from exc


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} is required.")
    return value


def _optional_text(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _required_bool(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be boolean.")
    return value


def _required_nonnegative_int(payload: Mapping[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer.")
    return value


def _required_object(payload: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object.")
    return value


def _cookie_value(headers: Mapping[str, str], name: str) -> str:
    cookie = SimpleCookie()
    cookie.load(_header(headers, "cookie") or "")
    morsel = cookie.get(name)
    return morsel.value if morsel is not None else ""


def _session_token(headers: Mapping[str, str]) -> str:
    authorization = _header(headers, "authorization") or ""
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    token = _cookie_value(headers, "resono_refresh")
    if not token:
        from app.vault_runtime.local_identity.repository import LocalSessionError
        raise LocalSessionError("Local session is required.")
    return token


def _bearer_token(headers: Mapping[str, str]) -> str:
    authorization = _header(headers, "authorization") or ""
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    from app.vault_runtime.external_memory.repository import ExternalMemoryAuthorizationError
    raise ExternalMemoryAuthorizationError("Integration bearer credential is required.")


def _csrf_token(headers: Mapping[str, str]) -> str:
    cookie_token = _cookie_value(headers, "resono_csrf")
    header_token = _header(headers, "x-resono-csrf") or ""
    if not cookie_token or not header_token or not compare_digest(cookie_token, header_token):
        from app.vault_runtime.local_identity.repository import LocalSessionError
        raise LocalSessionError("CSRF proof is invalid.")
    return header_token


def _header(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def _text_tuple(payload: Mapping[str, Any], key: str, *, required: bool = False) -> tuple[str, ...]:
    value = payload.get(key)
    if value is None and not required:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{key} must be a list of strings.")
    result = tuple(item.strip() for item in value if item.strip())
    if required and not result:
        raise ValueError(f"{key} is required.")
    return result
