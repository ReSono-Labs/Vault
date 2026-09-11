from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Protocol

from app.vault_runtime.memory.models import MemoryRecord
from app.vault_runtime.memory.repository import MemoryRepository

EMBEDDING_SIMILARITY_FLOOR = 0.20
DEFAULT_RETRIEVAL_LIMIT = 8
MAX_RETRIEVAL_LIMIT = 25


class QueryEmbedder(Protocol):
    model_key: str

    def embed(self, text: str) -> list[float]: ...


@dataclass(frozen=True, slots=True)
class RetrievalMatch:
    memory: MemoryRecord
    score: float
    match_methods: tuple[str, ...]


class MemoryRetriever:
    """R1 lexical/exact/real-provider semantic merge under local scope."""

    def __init__(
        self,
        *,
        memories: MemoryRepository,
        embedder: QueryEmbedder | None,
        similarity_floor: float = EMBEDDING_SIMILARITY_FLOOR,
    ) -> None:
        self._memories = memories
        self._embedder = embedder
        self._floor = similarity_floor

    def retrieve(
        self,
        query: str,
        *,
        user_id: str,
        workspace_id: str,
        limit: int = DEFAULT_RETRIEVAL_LIMIT,
    ) -> list[RetrievalMatch]:
        normalized_limit = max(1, min(int(limit), MAX_RETRIEVAL_LIMIT))
        scores: dict[str, float] = {}
        methods: dict[str, set[str]] = {}
        records: dict[str, MemoryRecord] = {}
        for position, memory in enumerate(
            self._memories.lexical_memories(
                user_id=user_id, workspace_id=workspace_id, query=query, limit=25
            )
        ):
            records[memory.memory_id] = memory
            scores[memory.memory_id] = max(scores.get(memory.memory_id, 0.0), 0.55 - position * 0.01)
            methods.setdefault(memory.memory_id, set()).add("lexical")
            if query.strip().lower() in (memory.memory_key.lower(), memory.content_text.lower()):
                scores[memory.memory_id] = max(scores[memory.memory_id], 1.0)
                methods[memory.memory_id].add("exact")
        if self._embedder is not None:
            try:
                query_embedding = self._embedder.embed(query)
                candidates = self._memories.embeddings_for(
                    user_id=user_id, workspace_id=workspace_id, model=self._embedder.model_key
                )
            except Exception:
                query_embedding, candidates = [], ()
            for candidate in candidates:
                if len(candidate.embedding) != len(query_embedding):
                    continue
                score = cosine_similarity(query_embedding, candidate.embedding)
                if score < self._floor:
                    continue
                try:
                    memory = self._memories.memory(
                        user_id=user_id, workspace_id=workspace_id, memory_id=candidate.memory_id
                    )
                except Exception:
                    continue
                records[memory.memory_id] = memory
                scores[memory.memory_id] = max(scores.get(memory.memory_id, 0.0), score)
                methods.setdefault(memory.memory_id, set()).add("semantic")
        ranked = sorted(scores, key=lambda item: scores[item], reverse=True)[:normalized_limit]
        return [
            RetrievalMatch(
                memory=records[memory_id], score=round(scores[memory_id], 8),
                match_methods=tuple(sorted(methods[memory_id])),
            )
            for memory_id in ranked
        ]


def cosine_similarity(left: list[float] | tuple[float, ...], right: list[float] | tuple[float, ...]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return numerator / (left_norm * right_norm)
