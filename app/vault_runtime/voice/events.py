from __future__ import annotations

import logging
from app.vault_runtime.memory.repository import MemoryRepository, MemoryTranscriptConflictError
from app.vault_runtime.voice.models import ProviderEvent
from app.vault_runtime.voice.repository import VoiceSessionConflictError, VoiceSessionRepository

_LOG = logging.getLogger(__name__)


class VoiceProviderEventCapture:
    """Voice donor provider-event idempotency plus scoped transcript capture."""

    def __init__(
        self, *, sessions: VoiceSessionRepository, memories: MemoryRepository,
        background_coordinator: object | None = None,
    ) -> None:
        self._sessions = sessions
        self._memories = memories
        self._background_coordinator = background_coordinator

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
        try:
            with self._sessions.transaction() as connection:
                event = self._sessions.record_provider_event_in_transaction(
                    connection, user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id, voice_session_id=voice_session_id,
                    provider_event_id=provider_event_id, event_type=event_type,
                    event_role=event_role, payload=payload,
                    transcript_entry_index=transcript_entry_index,
                )
                if transcript_text is not None and transcript_entry_index is not None:
                    self._memories.append_transcript_in_transaction(
                        connection, user_id=user_id, workspace_id=workspace_id,
                        voice_session_id=voice_session_id, entry_index=transcript_entry_index,
                        role=event_role, event_type=event_type, text_content=transcript_text,
                        metadata={"providerEventId": provider_event_id},
                        reject_conflicting_duplicate=True,
                    )
        except MemoryTranscriptConflictError as exc:
            raise VoiceSessionConflictError(str(exc)) from exc
        if (
            self._background_coordinator is not None
            and transcript_text is not None
            and transcript_entry_index is not None
            and event_role in {"user", "assistant"}
        ):
            try:
                from app.vault_runtime.background_agent.coordination_contracts import OwnerScope
                self._background_coordinator.observe(
                    OwnerScope(user_id, workspace_id),
                    "voice_transcript",
                    f"{voice_session_id}:{transcript_entry_index}",
                    {
                        "voice_session_id": voice_session_id,
                        "local_session_id": local_session_id,
                        "provider_event_id": provider_event_id,
                        "entry_index": transcript_entry_index,
                        "role": event_role,
                        "text": transcript_text,
                    },
                )
            except Exception as exc:
                _LOG.warning("voice_transcript_observe_failed voice_session_id=%s entry_index=%s error=%s", voice_session_id, transcript_entry_index, type(exc).__name__)
        return event
