from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json


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
class MemoryRetrievalState:
    memory: MemoryRecord
    retrieval_epoch: int

    def __post_init__(self) -> None:
        if type(self.retrieval_epoch) is not int or self.retrieval_epoch < 1:
            raise ValueError("Record retrieval epoch must be a positive integer.")


@dataclass(frozen=True, slots=True)
class MemoryRetrievalSnapshot:
    user_id: str
    workspace_id: str
    workspace_epoch: int
    private_epoch: int
    records: tuple[MemoryRetrievalState, ...]

    def __post_init__(self) -> None:
        for epoch in (self.workspace_epoch, self.private_epoch):
            if type(epoch) is not int or epoch < 0:
                raise ValueError("Scope retrieval epochs must be nonnegative integers.")

    @property
    def fingerprint(self) -> str:
        # The corpus counters cover additions/empty results too. No content or
        # another user's private activity is included in this cache identity.
        payload = [1, self.user_id, self.workspace_id,
                   self.workspace_epoch, self.private_epoch]
        return sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


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
    confirmation_entry_id: str | None
    confirmation_text: str
    confirmation_source_ref: dict | None = None


@dataclass(frozen=True, slots=True)
class MemoryEmbedding:
    memory_id: str
    provider: str
    model: str
    dimensions: int
    embedding: tuple[float, ...]
    content_fingerprint: str
