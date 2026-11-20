from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class VaultSessionToolRuntimeError(Exception):
    status_code: int
    code: str
    message: str
    details: dict[str, Any] | None = None


class VaultSessionToolPreEffectError(VaultSessionToolRuntimeError):
    """Failure positively known to occur before any tool/provider effect."""
