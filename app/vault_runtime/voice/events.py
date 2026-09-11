from __future__ import annotations

from app.vault_runtime.memory.repository import MemoryRepository
from app.vault_runtime.voice.models import ProviderEvent
from app.vault_runtime.voice.repository import VoiceSessionRepository


class VoiceProviderEventCapture:
    """Voice donor provider-event idempotency plus scoped transcript capture."""

    def __init__(
        self, *, sessions: VoiceSessionRepository, memories: MemoryRepository
    ) -> None:
        self._sessions = sessions
        self._memories = memories

    def capture(
        self,
        *,
        user_id: str,
        workspace_id: str,
        local_session_id: str,
        voice_session_id: str,
        provider_event_id: str,
        event_type: str,
        event_role: str | None,
        payload: object,
        transcript_text: str | None = None,
        transcript_entry_index: int | None = None,
    ) -> ProviderEvent:
        if (transcript_text is None) != (transcript_entry_index is None):
            raise ValueError("transcript text and entry index must be supplied together")
        if transcript_text is not None and event_role not in {"user", "assistant", "tool"}:
            raise ValueError("transcript capture requires a supported role")
        event = self._sessions.record_provider_event(
            user_id=user_id, workspace_id=workspace_id,
            local_session_id=local_session_id, voice_session_id=voice_session_id,
            provider_event_id=provider_event_id, event_type=event_type,
            event_role=event_role, payload=payload,
            transcript_entry_index=transcript_entry_index,
        )
        if event.accepted and transcript_text is not None and transcript_entry_index is not None:
            self._memories.append_transcript(
                user_id=user_id, workspace_id=workspace_id,
                voice_session_id=voice_session_id, entry_index=transcript_entry_index,
                role=event_role, event_type=event_type, text_content=transcript_text,
                metadata={"providerEventId": provider_event_id},
            )
        return event
