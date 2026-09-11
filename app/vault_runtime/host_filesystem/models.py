from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class HostFilesystemSettings:
    user_id: str
    workspace_id: str
    enabled: bool
    helper_base_url: str


@dataclass(frozen=True, slots=True)
class HostFilesystemIntegration:
    integration_id: str
    workspace_id: str
    user_id: str
    display_name: str
    adapter_kind: str
    status: str
    created_at: datetime
    revoked_at: datetime | None


@dataclass(frozen=True, slots=True)
class HostFilesystemMount:
    mount_id: str
    integration_id: str
    workspace_id: str
    user_id: str
    mount_name: str
    permission: str
    source: str
    status: str
    created_at: datetime
    revoked_at: datetime | None
