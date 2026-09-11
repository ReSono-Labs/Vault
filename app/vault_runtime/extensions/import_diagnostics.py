"""Separate blocking validation errors from owner-review warnings during import."""

from __future__ import annotations


def blocking_import_diagnostics(diagnostics: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Return diagnostics that should prevent confirm; warnings may still install."""
    blocked: list[str] = []
    for item in diagnostics:
        if item.startswith("review:"):
            continue
        if item.startswith("skill:"):
            continue
        if item.startswith("mcp:"):
            continue
        if "unknown top-level field" in item:
            continue
        blocked.append(item)
    return tuple(blocked)
