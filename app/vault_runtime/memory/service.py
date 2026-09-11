from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.vault_runtime.memory.contracts import MemoryCandidate
from app.vault_runtime.memory.models import MemoryRecord
from app.vault_runtime.memory.repository import MemoryRepository
from app.vault_runtime.memory.retrieval import MemoryRetriever, QueryEmbedder, RetrievalMatch


@dataclass(frozen=True, slots=True)
class ConfirmedActionResult:
    action: str
    memory_id: str
    memory: MemoryRecord | None


class MemoryService:
    """Bounded memory capability used by Voice and Background Agent paths."""

    def __init__(
        self, *, repository: MemoryRepository,
        embedder_factory: Callable[[str, str], QueryEmbedder] | None = None,
    ) -> None:
        self._repository = repository
        self._embedder_factory = embedder_factory

    def embeddings_available(self, *, user_id: str, workspace_id: str) -> bool:
        if self._embedder_factory is None:
            return False
        try:
            self._embedder_factory(user_id, workspace_id)
            return True
        except Exception:
            return False

    def ensure_vectors(
        self, *, user_id: str, workspace_id: str, limit: int = 256,
    ) -> tuple[int, int]:
        if self._embedder_factory is None:
            return (0, 0)
        try:
            embedder = self._embedder_factory(user_id, workspace_id)
            missing = self._repository.memories_missing_embeddings(
                user_id=user_id, workspace_id=workspace_id,
                model=embedder.model_key, limit=limit,
            )
        except Exception:
            return (0, 0)
        stored = failed = 0
        for memory in missing:
            try:
                self._repository.store_embedding(
                    user_id=user_id, workspace_id=workspace_id,
                    memory_id=memory.memory_id, provider="openai",
                    model=embedder.model_key, embedding=embedder.embed(memory.content_text),
                    content_text=memory.content_text,
                )
                stored += 1
            except Exception:
                failed += 1
        return stored, failed

    def search(
        self,
        *,
        user_id: str,
        workspace_id: str,
        query: str,
        limit: int = 8,
        embedder: QueryEmbedder | None = None,
    ) -> tuple[RetrievalMatch, ...]:
        effective_embedder = embedder
        if effective_embedder is None and self._embedder_factory is not None:
            self.ensure_vectors(user_id=user_id, workspace_id=workspace_id)
            try:
                effective_embedder = self._embedder_factory(user_id, workspace_id)
            except Exception:
                effective_embedder = None
        return tuple(
            MemoryRetriever(memories=self._repository, embedder=effective_embedder).retrieve(
                query, user_id=user_id, workspace_id=workspace_id, limit=limit
            )
        )

    def confirm_action(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        action_id: str,
        confirmation_entry_index: int,
    ) -> ConfirmedActionResult:
        action = self._repository.consume_action(
            user_id=user_id, workspace_id=workspace_id,
            voice_session_id=voice_session_id, action_id=action_id,
            confirmation_entry_index=confirmation_entry_index,
        )
        if action.action_kind == "forget":
            self._repository.delete_memory(
                user_id=user_id, workspace_id=workspace_id, memory_id=action.memory_id
            )
            return ConfirmedActionResult("forgotten", action.memory_id, None)
        current = self._repository.memory(
            user_id=user_id, workspace_id=workspace_id, memory_id=action.memory_id
        )
        updated = self._repository.reconcile_memory(
            user_id=user_id,
            workspace_id=workspace_id,
            voice_session_id=voice_session_id,
            candidate=MemoryCandidate(
                subject_id=current.subject_id,
                domain=current.domain,
                memory_type=current.memory_type,
                memory_key=current.memory_key,
                content_text=action.proposed_content or "",
                source_authority="user_asserted",
                confidence="high",
                sensitivity=current.sensitivity,
                intent="correct",
                visibility=current.visibility,
            ),
            evidence=((
                action.confirmation_entry_id,
                "explicit_memory_intent",
                "user_asserted",
                action.confirmation_text,
            ),),
        )
        return ConfirmedActionResult("corrected", action.memory_id, updated)
