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


def classify_diagnostic(item: str) -> dict[str, str]:
    """One skipped or flagged import entry as {component, status, reason} for status views.

    ``status`` is "unsupported" (a feature Vault does not run, such as stdio), "invalid"
    (the entry breaks the standard) or "warning" (installed, but worth a look).
    """
    kind, _, rest = item.partition(":")
    if kind in ("skill", "mcp") and ":" in rest:
        name, _, reason = rest.partition(":")
        reason = reason.strip()
        status = "unsupported" if reason.startswith("unsupported") else "invalid"
        return {"component": f"{kind}:{name}", "status": status, "reason": reason[:300]}
    return {"component": kind if kind in ("skills", "mcp", "migration", "workspaceImport", "review") else "package",
            "status": "warning", "reason": item[:300]}
