from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: str
    workspace_id: str
    user_id: str
    visibility: str
    subject_id: str
    domain: str
    memory_type: str
    memory_key: str
    content_text: str
    source_authority: str
    confidence: str
    sensitivity: str
    lifecycle_status: str
    current_version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TranscriptEntry:
    entry_id: str
    workspace_id: str
    user_id: str
    voice_session_id: str
    entry_index: int
    role: str
    event_type: str
    text_content: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PendingMemoryAction:
    action_id: str
    action_kind: str
    memory_id: str
    proposed_content: str | None
    confirmation_entry_id: str
    confirmation_text: str


@dataclass(frozen=True, slots=True)
class MemoryEmbedding:
    memory_id: str
    provider: str
    model: str
    dimensions: int
    embedding: tuple[float, ...]
    content_fingerprint: str
