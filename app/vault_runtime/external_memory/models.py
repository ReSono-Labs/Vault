from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ExternalMemoryIdentity:
    integration_id: str
    workspace_id: str
    user_id: str
    display_name: str
    adapter_kind: str
    grants: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExternalMemoryIntegration(ExternalMemoryIdentity):
    status: str
    created_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class EnrollmentResult:
    integration: ExternalMemoryIntegration
    credential: str

