import asyncio
from dataclasses import replace
import threading

import pytest

from app.vault_runtime.live_memory.canonical_ports import CanonicalPreparationPorts
from app.vault_runtime.live_memory.contracts import PreparedContext, StalePreparation
from app.vault_runtime.live_memory.preparation import ParallelPreparation, WorkerBudget
from tests.unit.test_live_memory_component import snapshot, memory, choice


class Guard:
    def __init__(self):
        self.allowed = True
    def is_current(self, snapshot, prepared):
        return self.allowed


class Backend:
    repairs_vectors_during_query = False
    def __init__(self):
        self.calls = []
    def retrieve(self, query, **scope):
        self.calls.append((query, scope))
        return (memory(query),)


def ports(**changes):
    settings = dict(guard=Guard(), search_backend=Backend(), limit=8,
                    query_builder=lambda snap: snap.text,
                    decision_retriever=lambda snap, memories, retained: (),
                    embedder_factory=None)
    settings.update(changes)
    return CanonicalPreparationPorts(**settings)


@pytest.mark.parametrize("limit", [True, 0, 26, "8"])
def test_bad_limit(limit):
    with pytest.raises(ValueError):
        ports(limit=limit)


def test_repair_backend_and_missing_context_ports_denied():
    backend = Backend()
    backend.repairs_vectors_during_query = True
    for changed in [dict(guard=None), dict(search_backend=backend), dict(query_builder=None), dict(decision_retriever=None)]:
        with pytest.raises(ValueError):
            ports(**changed)


def test_exact_reuse_needs_current_context_and_changed_input_drops():
    adapter = ports()
    snap = snapshot()
    previous = PreparedContext(snap, (memory(),), (choice("invoice"),))
    revised = replace(snap, identity=replace(snap.identity, revision=2))
    reused = adapter.reuse(revised, previous)
    assert reused.memory_complete and reused.decisions_complete
    for changed in [snapshot("Sarah invoice", 2), snapshot("not ABC invoice", 2),
                    replace(revised, context_fingerprint="changed"),
                    replace(revised, validity_fingerprint="changed")]:
        assert not adapter.reuse(changed, previous).memory_complete
    adapter.guard.allowed = False
    assert not adapter.reuse(revised, previous).memory_complete


def test_parallel_recall_and_decisions_share_snapshot_and_fresh_memory():
    async def run():
        barrier = threading.Barrier(2, timeout=2)
        observed = []
        class Concurrent(Backend):
            def retrieve(self, query, **scope):
                barrier.wait()
                return super().retrieve(query, **scope)
        def decide(snap, memories, retained):
            observed.append((snap, memories, retained))
            if not memories:
                barrier.wait()
            return (choice("memory" if memories else "initial"),)
        adapter = ports(search_backend=Concurrent(), decision_retriever=decide)
        preparation = ParallelPreparation(ports=adapter,
            workers=WorkerBudget(global_limit=4, user_limits={"user": 4}))
        snap = snapshot()
        ready = await preparation.prepare(snap, None, lambda: True)
        assert ready.decisions == (choice("memory"),)
        assert len(observed) == 2 and all(item[0] is snap for item in observed)
        assert observed[-1][1] == ready.memories
        revised = replace(snap, identity=replace(snap.identity, revision=2))
        reused = await preparation.prepare(revised, ready, lambda: True)
        assert reused.memories == ready.memories and len(adapter.search_backend.calls) == 1
        adapter.guard.allowed = False
        with pytest.raises(StalePreparation):
            await preparation.prepare(snap, ready, lambda: True)
    asyncio.run(run())


def test_scope_factory_fallback_and_malformed_results():
    backend = Backend()
    scopes = []
    def unavailable(user, workspace):
        scopes.append((user, workspace))
        raise RuntimeError("Synthetic unavailability")
    adapter = ports(search_backend=backend, embedder_factory=unavailable)
    adapter.recall(snapshot(), ())
    assert scopes == [("user", "workspace")] and backend.calls[0][1]["embedder"] is None
    with pytest.raises(Exception):
        ports(query_builder=lambda _: "").recall(snapshot(), ())
    backend.retrieve = lambda *args, **kwargs: []
    with pytest.raises(ValueError):
        adapter.recall(snapshot(), ())
    with pytest.raises(Exception):
        ports(decision_retriever=lambda *_: (choice("same"), choice("same"))).decisions(snapshot(), (), ())
