"""Voice capture/finalize composition from Voice close semantics and R1 learning."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace

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

_LOG = logging.getLogger(__name__)


class VoiceMemoryLearning:
    """Scoped production boundary; review is a capability, not another agent."""

    def __init__(
        self, *, memories: MemoryRepository, sessions: VoiceSessionRepository,
        credentials: VoiceProviderCredentialStore,
        reviewer_factory: Callable[[str, str], MemoryReviewer] | None = None,
        embedder_factory: Callable[[str, str], QueryEmbedder] | None = None,
        decision_finalize: Callable[...,dict[str,object]] | None = None,
        background_coordinator: object | None = None,
    ) -> None:
        self._memories = memories
        self._capture = VoiceProviderEventCapture(
            sessions=sessions, memories=memories, background_coordinator=background_coordinator,
        )
        self._credentials = credentials
        self._reviewer_factory = reviewer_factory
        self._embedder_factory = embedder_factory
        self._decision_finalize = decision_finalize
        self._background_coordinator = background_coordinator

    def capture(
        self, *, principal: LocalPrincipal, voice_session_id: str,
        provider_event_id: str, event_type: str, role: str,
        transcript_text: str | None, transcript_entry_index: int | None, payload: object,
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
        entries = self._memories.transcript_entries(
            user_id=principal.user_id, workspace_id=principal.workspace_id,
            voice_session_id=voice_session_id,
        )
        if not entries:
            return None
        decision_status = None
        try:
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
                    embedder = self._embedder_factory(principal.user_id,principal.workspace_id)
                except Exception:
                    embedder = None
            result = MemoryPipeline(repository=self._memories, reviewer=reviewer).finalize(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                voice_session_id=voice_session_id,
                embedder=embedder,
                embedding_provider=getattr(embedder,"provider_key","openai") if embedder is not None else None,
            )
        finally:
            # Independent post-session capability: a memory failure must not
            # suppress Decisions, and Decisions cannot undo memory publication.
            if self._decision_finalize is not None:
                try:
                    decision_status = self._decision_finalize(principal=principal,voice_session_id=voice_session_id)
                except Exception:
                    decision_status = {"state":"failed","errorCode":"decision_review_failed"}
            if self._background_coordinator is not None:
                try:
                    from app.vault_runtime.background_agent.coordination_contracts import OwnerScope
                    self._background_coordinator.observe(
                        OwnerScope(principal.user_id, principal.workspace_id),
                        "voice_session",
                        voice_session_id,
                        {
                            "voice_session_id": voice_session_id,
                            "local_session_id": principal.session_id,
                            "transcript": [
                                {"role": item.role, "text": item.text_content, "entry_index": item.entry_index}
                                for item in entries
                                if item.role in {"user", "assistant"}
                            ],
                        },
                    )
                except Exception as exc:
                    _LOG.warning("voice_session_observe_failed voice_session_id=%s error=%s", voice_session_id, type(exc).__name__)
        return replace(result,decision_review=decision_status)
