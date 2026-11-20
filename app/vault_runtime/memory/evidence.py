from __future__ import annotations

import json

SECRET_KEYS = frozenset(
    {
        "password", "passcode", "secret", "token", "api_key", "apikey",
        "authorization", "credential", "private_key", "seed_phrase", "cvv",
    }
)


def redact_evidence(value: object) -> object:
    """R1 recursive evidence redaction; key comparison is case-insensitive."""
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if str(key).lower() in SECRET_KEYS else redact_evidence(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_evidence(item) for item in value]
    return value


def bounded_tool_evidence(
    *, name: str, arguments: dict[str, object], result: object, is_error: bool
) -> str:
    payload = json.dumps(
        {
            "tool": name,
            "arguments": redact_evidence(arguments),
            "result": redact_evidence(result),
            "isError": bool(is_error),
        },
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return payload[:16384]
