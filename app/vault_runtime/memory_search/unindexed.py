from __future__ import annotations

from app.vault_runtime.memory.repository import MemoryRepository
from app.vault_runtime.memory.retrieval import MemoryRetriever, QueryEmbedder, RetrievalMatch


class UnindexedMemorySearchBackend:
    """Non-indexed search: the existing retriever without pgvector indexes; ranking and scope unchanged.

    MemoryService uses it until indexed memory has its indexes ready (and when indexed memory is off).
    """

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
