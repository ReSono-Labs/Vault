from datetime import datetime, timezone

import pytest

from app.vault_runtime.memory.models import MemoryEmbedding, MemoryRecord
from app.vault_runtime.memory.retrieval import MemoryRetriever
from app.vault_runtime.memory.service import MemoryService


def record(index=0):
    now = datetime(2026, 10, 7, tzinfo=timezone.utc)
    return MemoryRecord(
        f"m{index}", "w", "u", "private", "u", "project", "fact",
        "invoice" if index == 0 else f"key{index}", f"invoice fact {index}",
        "user_asserted", "high", "normal", "active", index + 1, now, now,
    )


class Embedder:
    model_key = "fake-model"

    def embed(self, text):
        return [1.0, 0.0]


class ScopedRepository:
    """Read-only fixture, not evidence of real SQL authorization."""

    def __init__(self, count=30):
        self.records = tuple(record(i) for i in range(count))
        self.calls = []

    def scope(self, user_id, workspace_id):
        self.calls.append((user_id, workspace_id))
        if (user_id, workspace_id) != ("u", "w"):
            raise PermissionError("inactive membership")

    def lexical_memories(self, *, user_id, workspace_id, query, limit):
        self.scope(user_id, workspace_id)
        return self.records[:limit] if query == "invoice" else ()

    def embeddings_for(self, *, user_id, workspace_id, model):
        self.scope(user_id, workspace_id)
        assert model == "fake-model"
        return tuple(MemoryEmbedding(
            item.memory_id, "fake", model, 2,
            (1.0, i / 10), "fixture",
        ) for i, item in enumerate(self.records))

    def memory(self, *, user_id, workspace_id, memory_id):
        self.scope(user_id, workspace_id)
        return next(item for item in self.records if item.memory_id == memory_id)


class Backend:
    def __init__(self, repairs=False, result=()):
        self.repairs_vectors_during_query = repairs
        self.calls = []
        self.result = result

    def retrieve(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return self.result


class RepairProbeService(MemoryService):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.repairs = []

    def ensure_vectors(self, **kwargs):
        self.repairs.append(kwargs)
        return (0, 0)


@pytest.mark.parametrize("limit", [1, 8, 25])
@pytest.mark.parametrize("semantic", [False, True])
def test_default_matches_real_legacy_ranking_and_payload(limit, semantic):
    repository = ScopedRepository()
    before = repository.records
    embedder = Embedder() if semantic else None
    expected = tuple(MemoryRetriever(memories=repository, embedder=embedder).retrieve(
        "invoice", user_id="u", workspace_id="w", limit=limit,
    ))
    service = MemoryService(repository=repository)
    for _ in range(2):
        actual = service.search(user_id="u", workspace_id="w", query="invoice",
                                limit=limit, embedder=embedder)
        assert isinstance(actual, tuple)
        assert actual == expected
        assert len(actual) == limit
        assert actual[0].memory.current_version == 1
        assert actual[0].match_methods == (
            ("exact", "lexical", "semantic") if semantic else ("exact", "lexical")
        )
    assert repository.records == before
    assert set(repository.calls) == {("u", "w")}


@pytest.mark.parametrize("query,count", [("", 30), ("unmatched", 30), ("invoice", 0)])
def test_empty_and_no_match_parity(query, count):
    repository = ScopedRepository(count)
    assert MemoryService(repository=repository).search(
        user_id="u", workspace_id="w", query=query,
    ) == tuple(MemoryRetriever(memories=repository, embedder=None).retrieve(
        query, user_id="u", workspace_id="w",
    )) == ()


def test_default_denied_scope_propagates():
    with pytest.raises(PermissionError, match="inactive membership"):
        MemoryService(repository=ScopedRepository()).search(
            user_id="other", workspace_id="w", query="invoice",
        )


@pytest.mark.parametrize("repairs", [False, True])
def test_injected_backend_repair_policy_and_exact_arguments(repairs):
    embedder = Embedder()
    factory_calls = []

    def factory(user_id, workspace_id):
        factory_calls.append((user_id, workspace_id))
        return embedder

    backend = Backend(repairs, result=("sentinel",))
    service = RepairProbeService(repository=object(), embedder_factory=factory,
                                 search_backend=backend)
    assert service.search(user_id="u", workspace_id="w", query=" raw draft ", limit=17) == ("sentinel",)
    assert backend.calls == [(" raw draft ", dict(user_id="u", workspace_id="w",
                                                limit=17, embedder=embedder))]
    assert factory_calls == [("u", "w")]
    assert service.repairs == ([dict(user_id="u", workspace_id="w")] if repairs else [])


def test_default_factory_repairs_and_failure_falls_back_to_lexical():
    calls = []

    def failing_factory(user_id, workspace_id):
        calls.append((user_id, workspace_id))
        raise RuntimeError("not configured")

    service = RepairProbeService(repository=ScopedRepository(), embedder_factory=failing_factory)
    result = service.search(user_id="u", workspace_id="w", query="invoice")
    assert result[0].match_methods == ("exact", "lexical")
    assert service.repairs == [dict(user_id="u", workspace_id="w")]
    assert calls == [("u", "w")]


def test_default_successful_factory_preserves_semantic_search():
    service = RepairProbeService(repository=ScopedRepository(), embedder_factory=lambda u, w: Embedder())
    assert "semantic" in service.search(user_id="u", workspace_id="w", query="invoice")[0].match_methods
    assert service.repairs == [dict(user_id="u", workspace_id="w")]


@pytest.mark.parametrize("injected", [False, True])
def test_explicit_embedder_bypasses_factory_and_repair(injected):
    def forbidden_factory(*args):
        pytest.fail("explicit embedder must bypass factory")

    backend = Backend(True) if injected else None
    service = RepairProbeService(repository=ScopedRepository(), embedder_factory=forbidden_factory,
                                 search_backend=backend)
    embedder = Embedder()
    result = service.search(user_id="u", workspace_id="w", query="invoice", embedder=embedder)
    assert service.repairs == []
    if backend:
        assert backend.calls[0][1]["embedder"] is embedder
    else:
        assert "semantic" in result[0].match_methods


def test_no_factory_never_repairs():
    service = RepairProbeService(repository=ScopedRepository())
    assert service.search(user_id="u", workspace_id="w", query="invoice")
    assert service.repairs == []


def test_backend_failure_is_not_empty_success():
    class FailingBackend(Backend):
        def retrieve(self, query, **kwargs):
            raise RuntimeError("backend failed")

    with pytest.raises(RuntimeError, match="backend failed"):
        MemoryService(repository=object(), search_backend=FailingBackend()).search(
            user_id="u", workspace_id="w", query="invoice",
        )
