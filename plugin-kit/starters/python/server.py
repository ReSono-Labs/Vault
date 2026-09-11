"""Starter application logic; connect this to your preferred MCP Python server."""

from __future__ import annotations


def greeting(name: str = "there", *, configured_greeting: str = "Hello") -> dict[str, object]:
    """Return the structured value the MCP `starter_greeting` tool should expose."""
    clean_name = name.strip()[:80] or "there"
    clean_greeting = configured_greeting.strip()[:40] or "Hello"
    message = f"{clean_greeting}, {clean_name}!"
    return {"content": [{"type": "text", "text": message}], "structuredContent": {"message": message}}
