import pytest

from app.vault_runtime.memory.models import MemoryRetrievalSnapshot, MemoryRetrievalState
from app.vault_runtime.memory.repository import MemoryRepository


def test_scope_fingerprint_tracks_scope_and_corpus_not_result_subset():
    initial = MemoryRetrievalSnapshot("u", "w", 1, 1, ())
    assert initial.fingerprint == MemoryRetrievalSnapshot("u", "w", 1, 1, ()).fingerprint
    for changed in [("v", "w", 1, 1), ("u", "x", 1, 1),
                    ("u", "w", 2, 1), ("u", "w", 1, 2)]:
        assert MemoryRetrievalSnapshot(*changed, ()).fingerprint != initial.fingerprint


@pytest.mark.parametrize("epoch", [True, -1, 1.5, "1"])
def test_invalid_scope_epoch(epoch):
    with pytest.raises(ValueError):
        MemoryRetrievalSnapshot("u", "w", epoch, 0, ())


@pytest.mark.parametrize("epoch", [True, 0, -1, "1"])
def test_invalid_record_epoch(epoch):
    with pytest.raises(ValueError):
        MemoryRetrievalState(None, epoch)


@pytest.mark.parametrize("ids", ["abc", b"abc", [""], [" x"], ["x "], [None], ["x", "x"],
                                  list(map(str, range(26)))])
def test_bad_batch_rejected_before_connect(ids):
    def unexpected_connection(*args):
        pytest.fail("Invalid input must not open the database")
    repository = MemoryRepository(database_url="unused", connector=unexpected_connection)
    with pytest.raises(ValueError):
        repository.retrieval_snapshot(user_id="u", workspace_id="w", memory_ids=ids)


def test_oversized_generator_consumption_is_bounded():
    def ids():
        yield from map(str, range(26))
        pytest.fail("Loader must not consume more than the bounded batch")
    repository = MemoryRepository(database_url="unused")
    with pytest.raises(ValueError):
        repository.retrieval_snapshot(user_id="u", workspace_id="w", memory_ids=ids())
