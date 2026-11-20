import pytest

from app.vault_runtime.live_memory.current_state import LiveStateLoader


class SerializationConflict(Exception):
    sqlstate = "40001"


def test_snapshot_retry_is_bounded_and_materializes_ids_once():
    class Loader(LiveStateLoader):
        def _capture(self, scope, identity, *, memory_ids):
            calls.append(memory_ids)
            if len(calls)<3:
                raise SerializationConflict()
            return "snapshot"
    calls=[]
    loader=Loader(database_url="unused", memories=None, preferences=None)
    assert loader.capture(None,None,memory_ids=iter(["m"])) == "snapshot"
    assert calls==[("m",)]*3
    calls.clear()
    def fail(*args, **kwargs):
        calls.append(1)
        raise SerializationConflict()
    loader._capture=fail
    with pytest.raises(SerializationConflict):
        loader.capture(None,None)
    assert len(calls)==3


def test_other_errors_are_not_retried():
    loader=LiveStateLoader(database_url="unused",memories=None,preferences=None)
    calls=[]
    def fail(*args,**kwargs):
        calls.append(1)
        raise ValueError("invalid identity")
    loader._capture=fail
    with pytest.raises(ValueError):
        loader.capture(None,None)
    assert calls==[1]
