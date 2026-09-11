from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class LocalPrincipal:
    user_id: str
    username: str
    display_name: str
    experience_style: str
    is_device_owner: bool
    session_id: str
    workspace_id: str
    expires_at: datetime
    password_mode: str = "user_managed"
    must_change_password: bool = False
    age_group: str = "adult"


@dataclass(frozen=True, slots=True)
class LocalSessionTokens:
    session_token: str
    csrf_token: str
    principal: LocalPrincipal


@dataclass(frozen=True, slots=True)
class LocalWorkspace:
    workspace_id: str
    display_name: str
    owner_user_id: str
    membership_type: str


@dataclass(frozen=True, slots=True)
class LocalUserProvisioning:
    user_id: str
    workspace_id: str
    password_mode: str
    setup_credential: str | None = None
