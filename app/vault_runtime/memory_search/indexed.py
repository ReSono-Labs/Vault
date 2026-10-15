"""Optional C01 SQL backend, reusing Vault's one lexical/semantic ranking policy."""
from app.vault_runtime.memory.retrieval import MemoryRetriever
from app.vault_runtime.memory_search.postgres import MODEL, PgvectorMemoryQueries, QueryOptions, vector_literal


class _IndexedRetriever(MemoryRetriever):
    def __init__(self, *, queries, embedder):
        super().__init__(memories=queries.memories, embedder=embedder)
        self._queries = queries

    def _lexical_candidates(self, query, *, user_id, workspace_id):
        return self._queries.lexical(query, user_id=user_id, workspace_id=workspace_id)

    def _semantic_candidates(self, query, *, user_id, workspace_id):
        values = None
        if self._embedder is not None and self._embedder.model_key == MODEL:
            try:
                values = getattr(self._embedder,"embed_query",self._embedder.embed)(query)
                vector_literal(values)
            except Exception:
                values = None
        if values is None:
            # Revocation during a failed/unsupported provider call cannot expose
            # the lexical payload fetched before that call.
            self._queries.authorize(user_id=user_id, workspace_id=workspace_id)
            return ()
        return self._queries.semantic(values, user_id=user_id, workspace_id=workspace_id, floor=self._floor)


class PgvectorMemorySearchBackend:
    repairs_vectors_during_query = False

    def __init__(self, *, memories, options: QueryOptions):
        self._queries = PgvectorMemoryQueries(memories=memories, options=options)

    def retrieve(self, query, *, user_id, workspace_id, limit, embedder):
        return tuple(_IndexedRetriever(queries=self._queries, embedder=embedder).retrieve(
            query, user_id=user_id, workspace_id=workspace_id, limit=limit))
