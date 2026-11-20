"""Version/identity guards for server-written SDK checkpoints.

These bind saved execution state; they do not grant tool authority or approve actions.
Domain decisions and live scope checks remain mandatory before resuming a side effect.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from .coordination_contracts import WorkScope

SDK_VERSION = "0.18.3"
GEMINI_ADAPTER_VERSION = "gemini-rest-v1"
MAX_CHECKPOINT_BYTES = 262_144
FORBIDDEN_SECRET_KEYS = frozenset({
    "tracing_api_key",
    "tracingapikey",
    "api_key",
    "apikey",
    "authorization",
    "client_secret",
    "access_token",
    "refresh_token",
})


def scope_envelope(scope: WorkScope) -> dict[str, object]:
    return {
        "user_id": scope.user_id,
        "workspace_id": scope.workspace_id,
        "work_id": scope.work_id,
        "intent_version": scope.intent_version,
        "worker_id": scope.worker_id,
        "worker_generation": scope.worker_generation,
        "grant_id": scope.grant_id,
    }


def _contains_forbidden_secret_key(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower().replace("-", "_")
            if normalized in FORBIDDEN_SECRET_KEYS and item not in (None, "", False):
                return True
            if _contains_forbidden_secret_key(item):
                return True
    elif isinstance(value, list):
        return any(_contains_forbidden_secret_key(item) for item in value)
    return False


def validate_sdk_checkpoint(
    payload: Any,
    *,
    provider_key: str,
    model_id: str,
    sdk_version: str,
    scope: WorkScope | None = None,
    max_bytes: int = MAX_CHECKPOINT_BYTES,
) -> None:
    if not isinstance(payload, dict) or type(payload.get("version")) is not int or payload["version"] != 1:
        raise ValueError("Unsupported SDK checkpoint version")
    if any(payload.get(key) != value for key, value in (
        ("provider_key", provider_key), ("model_id", model_id), ("sdk_version", sdk_version),
    )) or not isinstance(payload.get("state"), dict):
        raise ValueError("SDK checkpoint execution identity changed")
    if scope is not None and "scope" in payload and payload.get("scope") != scope_envelope(scope):
        raise ValueError("SDK checkpoint work scope changed")
    try:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("SDK checkpoint is not valid JSON") from exc
    if len(encoded) > max_bytes:
        raise ValueError("SDK checkpoint exceeds maximum size bound")
    if _contains_forbidden_secret_key(payload):
        raise ValueError("SDK checkpoint contains forbidden credential material")


def approval_fingerprint(approval: Any) -> str:
    raw = approval.raw_item
    name, call_id = raw.name, raw.call_id
    arguments = json.loads(raw.arguments) if isinstance(raw.arguments, str) else raw.arguments
    if not isinstance(arguments, dict) or not isinstance(name, str) or not name or not isinstance(call_id, str) or not call_id:
        raise ValueError("Invalid SDK approval request")
    canonical = json.dumps(
        {"name": name, "call_id": call_id, "arguments": arguments},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def build_sdk_checkpoint(
    *,
    provider_key: str,
    model_id: str,
    sdk_version: str,
    approval_hash: str,
    state: dict[str, object],
    scope: WorkScope | None = None,
    pending_action_id: str | None = None,
    tool_name: str | None = None,
    call_id: str | None = None,
    action_mode: str | None = None,
    budget: dict[str, object] | None = None,
    memories: tuple[dict[str, object], ...] = (),
    max_bytes: int = MAX_CHECKPOINT_BYTES,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "version": 1,
        "provider_key": provider_key,
        "model_id": model_id,
        "sdk_version": sdk_version,
        "approval_hash": approval_hash,
        "state": state,
    }
    if scope is not None:
        payload["scope"] = scope_envelope(scope)
    if pending_action_id is not None:
        payload["pending_action_id"] = pending_action_id
    if tool_name is not None:
        payload["tool_name"] = tool_name
    if call_id is not None:
        payload["call_id"] = call_id
    if action_mode is not None:
        payload["action_mode"] = action_mode
    if budget is not None:
        payload["budget"] = dict(budget)
    if memories:
        payload["memories"] = [dict(item) for item in memories]
    validate_sdk_checkpoint(
        payload, provider_key=provider_key, model_id=model_id,
        sdk_version=sdk_version, scope=scope, max_bytes=max_bytes,
    )
    return payload
