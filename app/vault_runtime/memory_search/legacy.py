from __future__ import annotations

from app.vault_runtime.memory.repository import MemoryRepository
from app.vault_runtime.memory.retrieval import MemoryRetriever, QueryEmbedder, RetrievalMatch


class LegacyMemorySearchBackend:
    """Delegate to the existing retriever without changing ranking or scope."""

    repairs_vectors_during_query = True

    def __init__(self, *, memories: MemoryRepository) -> None:
        self._memories = memories

    def retrieve(
        self, query: str, *, user_id: str, workspace_id: str,
        limit: int, embedder: QueryEmbedder | None,
    ) -> tuple[RetrievalMatch, ...]:
        return tuple(MemoryRetriever(memories=self._memories, embedder=embedder).retrieve(
            query, user_id=user_id, workspace_id=workspace_id, limit=limit,
        ))
