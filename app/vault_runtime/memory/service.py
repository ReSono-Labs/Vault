from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.vault_runtime.memory.contracts import MemoryCandidate
from app.vault_runtime.memory.models import MemoryRecord
from app.vault_runtime.memory.repository import MemoryRepository
from app.vault_runtime.memory.retrieval import QueryEmbedder, RetrievalMatch
from app.vault_runtime.memory_search.contracts import MemorySearchBackend
from app.vault_runtime.memory_search.legacy import LegacyMemorySearchBackend


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
        search_backend: MemorySearchBackend | None = None,
        reviewer_factory: Callable | None = None,
    ) -> None:
        self._repository = repository
        self._embedder_factory = embedder_factory
        self._reviewer_factory = reviewer_factory
        self._search_backend = (
            LegacyMemorySearchBackend(memories=repository)
            if search_backend is None else search_backend
        )

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
        after_memory_id: str | None = None, progress: Callable[[str], None] | None = None,
        cancel_requested: Callable[[], bool] | None = None,
    ) -> tuple[int, int]:
        if self._embedder_factory is None:
            return (0, 0)
        try:
            embedder = self._embedder_factory(user_id, workspace_id)
            missing = self._repository.memories_missing_embeddings(
                user_id=user_id, workspace_id=workspace_id,
                model=embedder.model_key, limit=limit,
                **({"after_memory_id": after_memory_id} if after_memory_id is not None else {}),
            )
        except Exception:
            return (0, 0)
        stored = failed = 0
        for memory in missing:
            if cancel_requested is not None and cancel_requested():
                break
            try:
                self._repository.store_embedding(
                    user_id=user_id, workspace_id=workspace_id,
                    memory_id=memory.memory_id, provider=getattr(embedder,"provider_key","openai"),
                    model=embedder.model_key, embedding=embedder.embed(memory.content_text),
                    content_text=memory.content_text, expected_version=memory.current_version,
                )
                stored += 1
            except Exception:
                failed += 1
            finally:
                if progress is not None:
                    progress(memory.memory_id)
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
            if self._search_backend.repairs_vectors_during_query:
                self.ensure_vectors(user_id=user_id, workspace_id=workspace_id)
            try:
                effective_embedder = self._embedder_factory(user_id, workspace_id)
            except Exception:
                effective_embedder = None
        return self._search_backend.retrieve(
            query, user_id=user_id, workspace_id=workspace_id,
            limit=limit, embedder=effective_embedder,
        )

    def confirm_action(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str | None = None,
        action_id: str,
        confirmation_entry_index: int | None = None,
        conversation_id: str | None = None,
        turn_id: str | None = None,
        local_session_id: str | None = None,
    ) -> ConfirmedActionResult:
        semantic_proof=None
        if self._reviewer_factory is not None:
            # Qualify a proposed correction before consuming confirmation or
            # taking canonical locks. Forget itself never needs a model call.
            with self._repository._connect() as read,read.cursor() as cursor:
                self._repository._require_membership(cursor,user_id=user_id,workspace_id=workspace_id)
                cursor.execute("""SELECT memory_id,proposed_content FROM vault_private.vault_memory_pending_actions
                  WHERE user_id=%s AND workspace_id=%s AND action_id=%s AND status='pending'
                    AND action_kind='correct' AND voice_session_id IS NOT DISTINCT FROM %s
                    AND conversation_id IS NOT DISTINCT FROM %s""",
                  (user_id,workspace_id,action_id,voice_session_id,conversation_id))
                pending=cursor.fetchone()
                current=self._repository._memory_by_id_cursor(cursor,user_id=user_id,workspace_id=workspace_id,
                    memory_id=pending[0]) if pending else None
                cursor.execute("""SELECT EXISTS(SELECT 1 FROM vault_private.vault_memory_suppressions
                  WHERE workspace_id=%s AND (visibility='workspace' OR user_id=%s))""",(workspace_id,user_id))
                has_suppression=cursor.fetchone()[0]
            if current is not None and has_suppression:
                candidate=self._correction_candidate(current,pending[1])
                reviewer=self._reviewer_factory(user_id,workspace_id)
                _,model=reviewer.model_identity()
                semantic_proof=self._repository.prepare_suppression_reviews(user_id=user_id,workspace_id=workspace_id,
                    candidates=[candidate],reviewer=reviewer,model=model)[0]
        with self._repository._connect() as connection:
            if conversation_id is not None:
                from app.vault_runtime.local_identity.authority import has_current_session_scope
                from .repository import MemoryConfirmationError
                with connection.cursor() as cursor:
                    if not local_session_id or not has_current_session_scope(cursor,user_id=user_id,
                        workspace_id=workspace_id,local_session_id=local_session_id,lock=True):
                        raise MemoryConfirmationError("Current local session is required.")
            action = self._repository.consume_action(
                user_id=user_id, workspace_id=workspace_id,
                voice_session_id=voice_session_id, action_id=action_id,
                confirmation_entry_index=confirmation_entry_index,
                conversation_id=conversation_id,turn_id=turn_id,_connection=connection,
            )
            if action.action_kind == "forget":
                self._repository.delete_memory(
                    user_id=user_id, workspace_id=workspace_id, memory_id=action.memory_id,_connection=connection
                )
                return ConfirmedActionResult("forgotten", action.memory_id, None)
            current = self._repository.memory(
                user_id=user_id, workspace_id=workspace_id, memory_id=action.memory_id
            )
            updated = self._repository.reconcile_memory(
                user_id=user_id,
                workspace_id=workspace_id,
                voice_session_id=conversation_id or voice_session_id,
                candidate=self._correction_candidate(current,action.proposed_content),
                **({'semantic_proof':semantic_proof} if semantic_proof is not None else {}),
                _connection=connection,
                evidence_source_refs=(action.confirmation_source_ref,) if action.confirmation_source_ref else None,
                evidence=((
                    action.confirmation_entry_id,
                    "explicit_memory_intent",
                    "user_asserted",
                    action.confirmation_text,
                ),),
            )
            return ConfirmedActionResult("corrected", action.memory_id, updated)

    @staticmethod
    def _correction_candidate(current,content):
        return MemoryCandidate(subject_id=current.subject_id,domain=current.domain,
            memory_type=current.memory_type,memory_key=current.memory_key,content_text=content or '',
            source_authority='user_asserted',confidence='high',sensitivity=current.sensitivity,
            intent='correct',visibility=current.visibility).validated()
