"""Bounded donor type slice used by admitted personal-data imports."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class VaultMigrationExportItem:
    domain: str
    source_id: str
    payload: dict[str, Any]

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> "VaultMigrationExportItem":
        item_payload = payload.get("payload")
        return cls(
            domain=str(payload["domain"]),
            source_id=str(payload["sourceId"]),
            payload=item_payload if isinstance(item_payload, dict) else {},
        )
