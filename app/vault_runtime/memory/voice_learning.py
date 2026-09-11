"""Voice capture/finalize composition from Voice close semantics and R1 learning."""

from __future__ import annotations

from collections.abc import Callable

from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.memory.openai_reviewer import OpenAIMemoryReviewer
from app.vault_runtime.memory.pipeline import FinalizeResult, MemoryPipeline
from app.vault_runtime.memory.pipeline import MemoryReviewer
from app.vault_runtime.memory.repository import MemoryRepository
from app.vault_runtime.memory.retrieval import QueryEmbedder
from app.vault_runtime.voice.credentials import VoiceProviderCredentialStore
from app.vault_runtime.voice.events import VoiceProviderEventCapture
from app.vault_runtime.voice.models import ProviderEvent
from app.vault_runtime.voice.repository import VoiceSessionRepository


class VoiceMemoryLearning:
    """Scoped production boundary; review is a capability, not another agent."""

    def __init__(
        self, *, memories: MemoryRepository, sessions: VoiceSessionRepository,
        credentials: VoiceProviderCredentialStore,
        reviewer_factory: Callable[[str, str], MemoryReviewer] | None = None,
        embedder_factory: Callable[[str, str], QueryEmbedder] | None = None,
    ) -> None:
        self._memories = memories
        self._capture = VoiceProviderEventCapture(sessions=sessions, memories=memories)
        self._credentials = credentials
        self._reviewer_factory = reviewer_factory
        self._embedder_factory = embedder_factory

    def capture(
        self, *, principal: LocalPrincipal, voice_session_id: str,
        provider_event_id: str, event_type: str, role: str,
        transcript_text: str, transcript_entry_index: int, payload: object,
    ) -> ProviderEvent:
        return self._capture.capture(
            user_id=principal.user_id, workspace_id=principal.workspace_id,
            local_session_id=principal.session_id, voice_session_id=voice_session_id,
            provider_event_id=provider_event_id, event_type=event_type,
            event_role=role, payload=payload, transcript_text=transcript_text,
            transcript_entry_index=transcript_entry_index,
        )

    def finalize(
        self, *, principal: LocalPrincipal, voice_session_id: str,
    ) -> FinalizeResult | None:
        if not self._memories.transcript_entries(
            user_id=principal.user_id, workspace_id=principal.workspace_id,
            voice_session_id=voice_session_id,
        ):
            return None
        reviewer = (
            self._reviewer_factory(principal.user_id, principal.workspace_id)
            if self._reviewer_factory is not None else OpenAIMemoryReviewer(
                credentials=self._credentials, user_id=principal.user_id,
                workspace_id=principal.workspace_id,
            )
        )
        embedder = None
        if self._embedder_factory is not None:
            try:
                embedder = self._embedder_factory(
                    principal.user_id, principal.workspace_id,
                )
            except Exception:
                embedder = None
        return MemoryPipeline(repository=self._memories, reviewer=reviewer).finalize(
            user_id=principal.user_id, workspace_id=principal.workspace_id,
            voice_session_id=voice_session_id,
            embedder=embedder,
            embedding_provider="openai" if embedder is not None else None,
        )
