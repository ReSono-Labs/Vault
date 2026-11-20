from __future__ import annotations

from typing import Protocol

from app.vault_runtime.memory.retrieval import QueryEmbedder, RetrievalMatch


class MemorySearchBackend(Protocol):
    repairs_vectors_during_query: bool

    def retrieve(
        self, query: str, *, user_id: str, workspace_id: str,
        limit: int, embedder: QueryEmbedder | None,
    ) -> tuple[RetrievalMatch, ...]: ...
