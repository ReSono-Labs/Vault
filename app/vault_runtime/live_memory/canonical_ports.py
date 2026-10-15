"""Join canonical read-only search to the existing shared preparation lifecycle."""
from collections.abc import Callable
from dataclasses import replace

from app.vault_runtime.conversation.contracts import text_fingerprint
from app.vault_runtime.decision_routing.contracts import CandidateChoice
from app.vault_runtime.decision_routing.selector import candidate_set_fingerprint
from app.vault_runtime.memory.retrieval import MAX_RETRIEVAL_LIMIT, QueryEmbedder, RetrievalMatch
from app.vault_runtime.memory_search.contracts import MemorySearchBackend
from .contracts import InputSnapshot, PreparedContext, ReusePlan
from .current_state import CurrentStateGuard


class CanonicalPreparationPorts:
    """Internal ports for ParallelPreparation, not a standalone unguarded API.

    Query interpretation and procedural lookup consume the same trusted snapshot.
    Changed meaning requires fresh retrieval, not approximate cache equivalence.
    """

    def __init__(self, *, guard: CurrentStateGuard, search_backend: MemorySearchBackend,
                 limit: int, query_builder: Callable[[InputSnapshot], str],
                 decision_retriever: Callable[
                     [InputSnapshot, tuple[RetrievalMatch, ...], tuple[CandidateChoice, ...]],
                     tuple[CandidateChoice, ...]],
                 embedder_factory: Callable[[str, str], QueryEmbedder | None] | None,
                 decisions_depend_on_memory: bool = True):
        if not callable(getattr(guard, "is_current", None)):
            raise ValueError("Current-state guard is required.")
        if search_backend.repairs_vectors_during_query is not False:
            raise ValueError("Speculative recall requires a read-only search backend.")
        if type(limit) is not int or not 1 <= limit <= MAX_RETRIEVAL_LIMIT:
            raise ValueError("Explicit bounded recall limit required.")
        if not callable(query_builder) or not callable(decision_retriever):
            raise ValueError("Shared-context query and decision retrieval are required.")
        if embedder_factory is not None and not callable(embedder_factory):
            raise ValueError("Scoped embedder factory must be callable or explicitly unavailable.")
        self.guard, self.search_backend, self.limit = guard, search_backend, limit
        self.query_builder, self.decision_retriever = query_builder, decision_retriever
        self.embedder_factory = embedder_factory
        self.decisions_depend_on_memory = decisions_depend_on_memory

    def is_current(self, snapshot: InputSnapshot, prepared: PreparedContext | None) -> bool:
        return self.guard.is_current(snapshot, prepared)

    def reuse(self, snapshot: InputSnapshot, previous: PreparedContext | None) -> ReusePlan:
        if previous is None:
            return ReusePlan()
        old = previous.snapshot
        if (old.scope != snapshot.scope or old.text != snapshot.text
                or old.context_sources != snapshot.context_sources
                or old.context_fingerprint != snapshot.context_fingerprint
                or old.validity_fingerprint != snapshot.validity_fingerprint
                or (old.identity.conversation_id, old.identity.segment_id, old.identity.utterance_id)
                != (snapshot.identity.conversation_id, snapshot.identity.segment_id, snapshot.identity.utterance_id)):
            return ReusePlan()
        if not self.guard.is_current(snapshot, replace(previous, snapshot=snapshot)):
            return ReusePlan()
        return ReusePlan(previous.memories, previous.decisions, True, True)

    def recall(self, snapshot: InputSnapshot,
               retained: tuple[RetrievalMatch, ...]) -> tuple[RetrievalMatch, ...]:
        # ParallelPreparation validates current scope before invoking this port
        # and again before publication. No second ranker or vector repair here.
        query = self.query_builder(snapshot)
        text_fingerprint(query)  # Existing UTF8/NUL/nonblank/byte contract.
        embedder = None
        if self.embedder_factory is not None:
            try:
                embedder = self.embedder_factory(snapshot.scope.user_id, snapshot.scope.workspace_id)
            except Exception:
                pass  # Same honest lexical-only availability fallback as MemoryService.
        matches = self.search_backend.retrieve(query, user_id=snapshot.scope.user_id,
            workspace_id=snapshot.scope.workspace_id, limit=self.limit, embedder=embedder)
        if (type(matches) is not tuple or len(matches) > self.limit
                or any(type(match) is not RetrievalMatch for match in matches)):
            raise ValueError("Search backend returned invalid bounded canonical matches.")
        return matches

    def decisions(self, snapshot: InputSnapshot, memories: tuple[RetrievalMatch, ...],
                  retained: tuple[CandidateChoice, ...]) -> tuple[CandidateChoice, ...]:
        choices = self.decision_retriever(snapshot, memories, retained)
        candidate_set_fingerprint(choices)  # Reuse C17A's validator, not permissions.
        return choices
