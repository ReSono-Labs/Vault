from types import SimpleNamespace

from app.vault_runtime.memory_search.maintenance import IndexedMemoryMaintenance
from app.vault_runtime.memory.service import MemoryService


def test_repair_advances_past_failed_rows_wraps_and_stops():
    calls = []
    pages = [["a", "b"], [], ["a"]]
    def repair(**kwargs):
        calls.append(kwargs)
        for key in pages.pop(0):
            kwargs["progress"](key)
        return 0, 1
    owner = IndexedMemoryMaintenance(database_url="unused", service=SimpleNamespace(ensure_vectors=repair),
        identities=SimpleNamespace(active_storage_identities=lambda:(("user", "workspace"),)))
    owner.repair_batch()
    owner.repair_batch()
    owner.repair_batch()
    assert [c["after_memory_id"] for c in calls] == ["", "b", ""]
    assert all(c["limit"] == 2 for c in calls)
    owner.close()
    assert calls[-1]["cancel_requested"]()
    owner.repair_batch()
    assert len(calls) == 3


def test_disabled_rollback_does_not_connect_or_cut_over():
    service = SimpleNamespace(_search_backend="legacy")
    owner = IndexedMemoryMaintenance(database_url="invalid", service=service, identities=None, enabled=False)
    owner.initialize_indexes()
    assert service._search_backend == "legacy"
    assert not owner.ready.is_set() and owner.state == "disabled"


def test_canonical_repair_reports_failed_cursor_and_cancels_between_records():
    calls, progress = [], []
    records = [SimpleNamespace(memory_id=k,content_text=k,current_version=1) for k in ("a","b","c")]
    def missing(**kwargs):
        assert kwargs["after_memory_id"] == "" and kwargs["limit"] == 32
        return records
    def embed(text):
        calls.append(text)
        if text=="a":
            raise ValueError("synthetic failure")
        return [1.]
    writes=[]
    repository=SimpleNamespace(memories_missing_embeddings=missing,store_embedding=lambda **kwargs:writes.append(kwargs))
    service=MemoryService(repository=repository,embedder_factory=lambda *args:SimpleNamespace(model_key="test",embed=embed))
    assert service.ensure_vectors(user_id="u",workspace_id="w",limit=32,after_memory_id="",progress=progress.append,
        cancel_requested=lambda:len(calls)>=2) == (1,1)
    assert calls==["a","b"] and progress==["a","b"]
    assert writes[0]["memory_id"]=="b" and writes[0]["expected_version"]==1


def test_lookups_use_unindexed_search_until_indexes_are_ready_then_pgvector(monkeypatch):  # BE-07
    from contextlib import nullcontext

    import psycopg

    from app.vault_runtime.memory_search import maintenance
    from app.vault_runtime.memory_search.unindexed import UnindexedMemorySearchBackend

    calls = []
    monkeypatch.setattr(UnindexedMemorySearchBackend, "retrieve",
                        lambda self, query, **_: calls.append(("unindexed", query)) or ())

    class Pgvector:
        repairs_vectors_during_query = False

        def retrieve(self, query, **_):
            calls.append(("pgvector", query))
            return ()

    pgvector = Pgvector()
    service = MemoryService(repository=SimpleNamespace())
    owner = IndexedMemoryMaintenance(database_url="postgresql://unused", service=service, identities=None,
                                     indexed_backend=pgvector)
    service.search(user_id="u", workspace_id="w", query="before")
    monkeypatch.setattr(psycopg, "connect", lambda *_, **__: nullcontext(SimpleNamespace(execute=lambda *_: None)))
    monkeypatch.setattr(maintenance, "ensure_indexes", lambda connection: None)
    owner.initialize_indexes()
    service.search(user_id="u", workspace_id="w", query="after")
    assert calls == [("unindexed", "before"), ("pgvector", "after")]
    assert owner.ready.is_set() and owner.state == "ready"
    assert service._search_backend is pgvector  # The instance composition shares with Chat preparation.
