"""Shared test helpers moved out of test modules (TST-01)."""

from datetime import datetime, timezone

from app.vault_runtime.memory.models import MemoryRecord


def record(index=0):
    now = datetime(2026, 10, 7, tzinfo=timezone.utc)
    return MemoryRecord(
        f"m{index}", "w", "u", "private", "u", "project", "fact",
        "invoice" if index == 0 else f"key{index}", f"invoice fact {index}",
        "user_asserted", "high", "normal", "active", index + 1, now, now,
    )
