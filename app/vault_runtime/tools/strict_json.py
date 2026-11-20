from __future__ import annotations

import json
from math import isfinite
from typing import Any

STRICT_JSON_MAX_BYTES = 1_048_576
STRICT_JSON_MAX_DEPTH = 32
STRICT_JSON_MAX_NODES = 50_000


class StrictJSONError(ValueError):
    def __init__(self, *, reason: str) -> None:
        super().__init__("Request body must be a bounded JSON value.")
        self.reason = reason


def parse_json_object_bytes(
    raw: bytes,
    *,
    max_bytes: int = STRICT_JSON_MAX_BYTES,
    max_depth: int = STRICT_JSON_MAX_DEPTH,
    max_nodes: int = STRICT_JSON_MAX_NODES,
) -> dict[str, Any]:
    if type(raw) is not bytes:
        raise StrictJSONError(reason="raw_type")
    if len(raw) > max_bytes:
        raise StrictJSONError(reason="raw_size")
    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_without_duplicate_keys,
            parse_constant=lambda _value: _raise("non_finite"),
            parse_float=_finite_float,
        )
    except StrictJSONError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, OverflowError, RecursionError, ValueError) as exc:
        raise StrictJSONError(reason="syntax") from exc
    if type(value) is not dict:
        raise StrictJSONError(reason="object_required")
    _validate_tree(value, max_depth=max_depth, max_nodes=max_nodes)
    return value


def canonical_json_bytes(value: Any, *, max_bytes: int = STRICT_JSON_MAX_BYTES) -> bytes:
    _validate_tree(value, max_depth=STRICT_JSON_MAX_DEPTH, max_nodes=STRICT_JSON_MAX_NODES)
    try:
        encoded = json.dumps(
            value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError) as exc:
        raise StrictJSONError(reason="canonicalization") from exc
    if len(encoded) > max_bytes:
        raise StrictJSONError(reason="canonical_size")
    return encoded


def _without_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJSONError(reason="duplicate_key")
        result[key] = value
    return result


def _finite_float(raw: str) -> float:
    value = float(raw)
    if not isfinite(value):
        raise StrictJSONError(reason="non_finite")
    return value


def _raise(reason: str):
    raise StrictJSONError(reason=reason)


def _validate_tree(value: Any, *, max_depth: int, max_nodes: int) -> None:
    remaining = max_nodes
    active: set[int] = set()
    stack: list[tuple[Any, int, bool]] = [(value, 0, False)]
    while stack:
        current, depth, leaving = stack.pop()
        if leaving:
            active.remove(id(current))
            continue
        remaining -= 1
        if remaining < 0:
            raise StrictJSONError(reason="nodes")
        if depth > max_depth:
            raise StrictJSONError(reason="depth")
        if current is None or type(current) in {str, bool, int}:
            continue
        if type(current) is float:
            if not isfinite(current):
                raise StrictJSONError(reason="non_finite")
            continue
        if type(current) is dict:
            if id(current) in active:
                raise StrictJSONError(reason="cycle")
            active.add(id(current))
            stack.append((current, depth, True))
            for key, item in reversed(tuple(current.items())):
                if type(key) is not str:
                    raise StrictJSONError(reason="object_key")
                stack.append((item, depth + 1, False))
            continue
        if type(current) is list:
            if id(current) in active:
                raise StrictJSONError(reason="cycle")
            active.add(id(current))
            stack.append((current, depth, True))
            for item in reversed(current):
                stack.append((item, depth + 1, False))
            continue
        raise StrictJSONError(reason="type")
