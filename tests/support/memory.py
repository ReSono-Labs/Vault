"""Shared test helpers moved out of test modules (TST-01)."""

from __future__ import annotations

from app.vault_runtime.memory.contracts import MemoryCandidate
from app.vault_runtime.memory.repository import MemoryRepository


def _candidate(*, content: str, visibility: str = "private", intent: str = "create", sensitivity: str = "normal"):
    return MemoryCandidate(
        subject_id="user", domain="personal", memory_type="preference",
        memory_key="drink", content_text=content, source_authority="user_asserted",
        confidence="high", sensitivity=sensitivity, intent=intent, visibility=visibility,
    )


def _entry(memories: MemoryRepository, principal, *, session: str, index: int, text: str):
    return memories.append_transcript(
        user_id=principal.user_id, workspace_id=principal.workspace_id,
        voice_session_id=session, entry_index=index, role="user",
        event_type="voice.user.final", text_content=text,
    )
