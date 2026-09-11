from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Mapping

from app.vault_runtime.session_tools.errors import VaultSessionToolRuntimeError


MAX_PRIVATE_QUERY_CHARS = 20_000
MAX_PRIVATE_LIST_ITEMS = 100
SUPPORT_SAFE_TEXT_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "._:/@+-"
)
SLUG_STOP_WORDS = frozenset({"a", "an", "and", "for", "into", "of", "or", "save", "the", "this", "to", "write"})


def source_payload(item: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = item.get("sourcePayload")
    return payload if isinstance(payload, Mapping) else {}


def payload_text(payload: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def payload_bool(payload: Mapping[str, Any], *keys: str) -> bool | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        if isinstance(value, (int, float)):
            return bool(value)
    return None


def payload_mapping(payload: Mapping[str, Any], *keys: str) -> Mapping[str, Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def normalize_search_text(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def slug_words(value: str) -> list[str]:
    words: list[str] = []
    current: list[str] = []
    for char in value.lower():
        if char.isalnum():
            current.append(char)
            continue
        if current:
            word = "".join(current)
            if word not in SLUG_STOP_WORDS:
                words.append(word[:24])
            current = []
    if current:
        word = "".join(current)
        if word not in SLUG_STOP_WORDS:
            words.append(word[:24])
    return words


def slug_text(value: str, *, fallback: str, max_words: int = 4, max_length: int = 64) -> str:
    words = slug_words(value)
    if not words:
        return fallback
    return "-".join(words[:max_words])[:max_length].strip("-") or fallback


def private_query(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise VaultSessionToolRuntimeError(
            400,
            "invalid_private_tool_query",
            "Private tool query must be text.",
            details={"fieldPath": "$.arguments.query"},
        )
    text = str(value).strip()
    if len(text) > MAX_PRIVATE_QUERY_CHARS:
        raise VaultSessionToolRuntimeError(
            413,
            "private_tool_query_too_large",
            "Private tool query exceeds the Vault private tool limit.",
            details={"fieldPath": "$.arguments.query", "maxChars": MAX_PRIVATE_QUERY_CHARS},
        )
    return text


def private_argument_text(
    arguments: Mapping[str, Any],
    key: str,
    *,
    required: bool,
    max_chars: int = MAX_PRIVATE_QUERY_CHARS,
) -> str:
    value = arguments.get(key)
    if value is None:
        if required:
            raise VaultSessionToolRuntimeError(
                400,
                "missing_private_tool_argument",
                f"{key} is required.",
                details={"fieldPath": f"$.arguments.{key}"},
            )
        return ""
    if not isinstance(value, str):
        raise VaultSessionToolRuntimeError(
            400,
            "invalid_private_tool_argument",
            "Private tool argument must be text.",
            details={"fieldPath": f"$.arguments.{key}"},
        )
    text = value.strip()
    if required and not text:
        raise VaultSessionToolRuntimeError(
            400,
            "missing_private_tool_argument",
            f"{key} is required.",
            details={"fieldPath": f"$.arguments.{key}"},
        )
    if len(text) > max_chars:
        raise VaultSessionToolRuntimeError(
            413,
            "private_tool_argument_too_large",
            "Private tool argument exceeds the Vault private tool limit.",
            details={"fieldPath": f"$.arguments.{key}", "maxChars": max_chars},
        )
    return text


def optional_private_argument_text(arguments: Mapping[str, Any], key: str) -> str | None:
    text = private_argument_text(arguments, key, required=False)
    return text or None


def optional_arg_text(arguments: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        text = optional_private_argument_text(arguments, key)
        if text:
            return text
    return None


def required_arg_text(arguments: Mapping[str, Any], *keys: str) -> str:
    text = optional_arg_text(arguments, *keys)
    if text:
        return text
    field = keys[0] if keys else "value"
    raise VaultSessionToolRuntimeError(
        400,
        "missing_contact_argument",
        f"{field} is required.",
        details={"fieldPath": f"$.arguments.{field}"},
    )


def argument_bool(arguments: Mapping[str, Any], key: str, *, default: bool) -> bool:
    value = arguments.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def private_string_list(value: Any, *, key: str) -> list[str]:
    if not isinstance(value, list):
        raise VaultSessionToolRuntimeError(
            400,
            "invalid_private_tool_argument",
            "Private tool argument must be a list of text values.",
            details={"fieldPath": f"$.arguments.{key}"},
        )
    if not value:
        raise VaultSessionToolRuntimeError(
            400,
            "missing_private_tool_argument",
            f"{key} is required.",
            details={"fieldPath": f"$.arguments.{key}"},
        )
    if len(value) > MAX_PRIVATE_LIST_ITEMS:
        raise VaultSessionToolRuntimeError(
            413,
            "private_tool_argument_too_large",
            "Private tool argument list exceeds the Vault private tool limit.",
            details={"fieldPath": f"$.arguments.{key}", "maxItems": MAX_PRIVATE_LIST_ITEMS},
        )
    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise VaultSessionToolRuntimeError(
                400,
                "invalid_private_tool_argument",
                "Private tool argument must be text.",
                details={"fieldPath": f"$.arguments.{key}[{index}]"},
            )
        text = item.strip()
        if not text:
            raise VaultSessionToolRuntimeError(
                400,
                "missing_private_tool_argument",
                f"{key} entries must not be empty.",
                details={"fieldPath": f"$.arguments.{key}[{index}]"},
            )
        if len(text) > MAX_PRIVATE_QUERY_CHARS:
            raise VaultSessionToolRuntimeError(
                413,
                "private_tool_argument_too_large",
                "Private tool argument exceeds the Vault private tool limit.",
                details={"fieldPath": f"$.arguments.{key}[{index}]", "maxChars": MAX_PRIVATE_QUERY_CHARS},
            )
        normalized.append(text)
    return normalized


def private_bool(value: Any, *, key: str, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    raise VaultSessionToolRuntimeError(
        400,
        "invalid_private_tool_argument",
        "Private tool argument must be a boolean.",
        details={"fieldPath": f"$.arguments.{key}"},
    )


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_support_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def support_safe_text(value: Any, *, field: str, max_length: int) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise VaultSessionToolRuntimeError(
            400,
            "private_tool_support_text_denied",
            "Vault private tool control fields must be support-safe identifier text.",
            details={"fieldPath": field},
        )
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_length or any(character not in SUPPORT_SAFE_TEXT_CHARS for character in text):
        raise VaultSessionToolRuntimeError(
            400,
            "private_tool_support_text_denied",
            "Vault private tool control fields must be support-safe identifier text.",
            details={"fieldPath": field},
        )
    return text


def bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def list_items_result(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "ok",
        "executionBackend": "vault",
        "source": "vault_cache",
        "freshness": {"source": "vault_cache", "resultsMayBePartial": True},
        "cloudFallback": False,
        "items": items,
    }


def read_item_result(*, items: list[dict[str, Any]], lookup: str, id_key: str) -> dict[str, Any]:
    for item in items:
        if lookup in {str(item.get(id_key) or ""), str(item.get("sourceId") or "")}:
            return {
                "status": "ok",
                "executionBackend": "vault",
                "source": "vault_cache",
                "cloudFallback": False,
                "item": item,
            }
    return {
        "status": "not_found",
        "executionBackend": "vault",
        "source": "vault_cache",
        "cloudFallback": False,
        "item": None,
    }
