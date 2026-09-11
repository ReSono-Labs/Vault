from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.vault_runtime.memory.contracts import MemoryReview, REVIEWER_CONTRACT_VERSION
from app.vault_runtime.memory.repository import MemoryRepository, transcript_fingerprint
from app.vault_runtime.memory.retrieval import QueryEmbedder


class MemoryReviewer(Protocol):
    """Review capability protocol. Implementations are not system agents."""

    def review(self, transcript: str) -> MemoryReview: ...


@dataclass(frozen=True, slots=True)
class FinalizeResult:
    voice_session_id: str
    summary: str
    memory_count: int
    embedded_count: int
    model: str
    embeddings_available: bool
    already_completed: bool = False


class MemoryPipeline:
    def __init__(self, *, repository: MemoryRepository, reviewer: MemoryReviewer) -> None:
        self._repository = repository
        self._reviewer = reviewer

    def finalize(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        embedder: QueryEmbedder | None = None,
        embedding_provider: str | None = None,
    ) -> FinalizeResult:
        entries = self._repository.transcript_entries(
            user_id=user_id, workspace_id=workspace_id, voice_session_id=voice_session_id
        )
        if not entries:
            raise ValueError("Session has no transcript to review.")
        fingerprint = transcript_fingerprint(entries)
        existing_summary = self._repository.session_summary(
            user_id=user_id, workspace_id=workspace_id,
            voice_session_id=voice_session_id, fingerprint=fingerprint,
        )
        if existing_summary is not None and self._repository.ingestion_completed(
            user_id=user_id, workspace_id=workspace_id,
            voice_session_id=voice_session_id, fingerprint=fingerprint,
        ):
            return FinalizeResult(
                voice_session_id, existing_summary, 0, 0, "", embedder is not None, True
            )
        transcript = "\n".join(
            f"[entryIndex={entry.entry_index}] [{entry.event_type}] "
            f"{entry.role}: {entry.text_content}"
            for entry in entries
        )
        review = self._reviewer.review(transcript).validated()
        if not self._repository.claim_ingestion(
            user_id=user_id, workspace_id=workspace_id,
            voice_session_id=voice_session_id, fingerprint=fingerprint,
            reviewer_model=review.model,
        ):
            existing_summary = self._repository.session_summary(
                user_id=user_id, workspace_id=workspace_id,
                voice_session_id=voice_session_id, fingerprint=fingerprint,
            )
            if existing_summary is not None:
                return FinalizeResult(
                    voice_session_id, existing_summary, 0, 0, review.model, embedder is not None, True
                )
            raise RuntimeError("Memory ingestion is already in progress.")
        self._repository.store_summary(
            user_id=user_id, workspace_id=workspace_id,
            voice_session_id=voice_session_id, summary_text=review.summary,
            fingerprint=fingerprint,
        )
        by_index = {entry.entry_index: entry for entry in entries}
        stored = []
        for reviewed in review.memories:
            cited = tuple(by_index[index] for index in reviewed.source_entry_indexes if index in by_index)
            if len(cited) != len(reviewed.source_entry_indexes):
                continue
            record = self._repository.reconcile_memory(
                user_id=user_id,
                workspace_id=workspace_id,
                voice_session_id=voice_session_id,
                candidate=reviewed.memory,
                evidence=tuple(
                    (
                        entry.entry_id,
                        "tool_result" if entry.role == "tool" else
                        "user_statement" if entry.role == "user" else "assistant_statement",
                        reviewed.memory.source_authority,
                        entry.text_content,
                    )
                    for entry in cited
                ),
            )
            if record.lifecycle_status == "active":
                stored.append(record)
        embedded = 0
        if embedder is not None and embedding_provider:
            for memory in stored:
                try:
                    vector = embedder.embed(memory.content_text)
                    self._repository.store_embedding(
                        user_id=user_id, workspace_id=workspace_id,
                        memory_id=memory.memory_id, provider=embedding_provider,
                        model=embedder.model_key, embedding=vector,
                        content_text=memory.content_text,
                    )
                    embedded += 1
                except Exception:
                    continue
        self._repository.complete_ingestion(
            user_id=user_id, workspace_id=workspace_id,
            voice_session_id=voice_session_id, fingerprint=fingerprint,
            candidate_count=len(review.memories), stored_count=len(stored),
        )
        return FinalizeResult(
            voice_session_id, review.summary, len(stored), embedded, review.model,
            embedder is not None and bool(embedding_provider), False,
        )
