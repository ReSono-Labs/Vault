from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class VoiceSession:
    voice_session_id: str
    user_id: str
    workspace_id: str
    local_session_id: str
    provider_key: str
    model_key: str
    connection_mode: str
    status: str
    provider_session_id: str | None
    opened_at: datetime
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class VoiceContext:
    voice_session_id: str
    user_id: str
    workspace_id: str
    display_name: str
    experience_style: str
    instructions: str
    memory_items: tuple[dict[str, str], ...]
    previous_summary: str | None = None
    skill_names: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ProviderEvent:
    provider_event_id: str
    voice_session_id: str
    event_type: str
    event_role: str | None
    transcript_entry_index: int | None
    accepted: bool
