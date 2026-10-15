import asyncio
from dataclasses import replace
import threading

import pytest

from app.vault_runtime.live_memory.current_state import CurrentLiveState, CurrentStateGuard
from app.vault_runtime.live_memory.preferences import LiveMemoryPreference
from app.vault_runtime.live_memory.stream_registry import ScopedStreamRegistry
from app.vault_runtime.memory.models import MemoryRetrievalSnapshot
from tests.unit.test_live_memory_component import Ports, snapshot, stream, until


def state(snap):
    scope = snap.scope
    return CurrentLiveState(scope, snap.identity.conversation_id, snap.identity.segment_id, 0,
        LiveMemoryPreference(scope.user_id, scope.workspace_id, True, 0),
        MemoryRetrievalSnapshot(scope.user_id, scope.workspace_id, 1, 1, ()))


def test_external_current_guard_is_required_and_fail_closed():
    with pytest.raises(ValueError):
        CurrentStateGuard(loader=object(), external_current=None)
    class Forbidden:
        def capture(self, *args, **kwargs):
            pytest.fail("Rejected external evidence must not load current state")
    guard = CurrentStateGuard(loader=Forbidden(), external_current=lambda *_: False)
    assert not guard.is_current(snapshot(), None)


def test_scoped_off_removes_pending_work_without_touching_other_user():
    async def run():
        registry = ScopedStreamRegistry(capacity=2)
        first = snapshot()
        other = replace(first, scope=replace(first.scope, user_id="other"))
        ports = Ports()
        current = stream(ports, debounce=1, max_wait=1)
        untouched = stream(debounce=1, max_wait=1)
        await current.feed_partial(first)
        await untouched.feed_partial(other)
        first_key = registry.register(state(first), "utterance", current)
        other_key = registry.register(state(other), "utterance", untouched)
        await asyncio.to_thread(registry.preference_changed, LiveMemoryPreference("user", "workspace", False, 1))
        await until(lambda: current._closed)
        assert not untouched._closed and not registry.unregister(first_key)
        assert registry.unregister(other_key)
        await current.wait_closed()
        assert not ports.calls and await current.ready() is None
        untouched.invalidate()
        await untouched.wait_closed()
    asyncio.run(run())


def test_off_invalidates_blocked_worker_but_does_not_claim_it_stopped():
    async def run():
        entered, release = threading.Event(), threading.Event()
        class Blocking(Ports):
            def recall(self, snap, retained):
                entered.set()
                if not release.wait(3):
                    raise RuntimeError("Test coordination timeout")
                return ()
        snap = snapshot()
        current = stream(Blocking())
        registry = ScopedStreamRegistry(capacity=1)
        await current.feed_partial(snap)
        registry.register(state(snap), "utterance", current)
        draining = None
        try:
            await until(entered.is_set)
            await asyncio.to_thread(registry.preference_changed, LiveMemoryPreference("user", "workspace", False, 1))
            await until(lambda: current._closed)
            draining = asyncio.create_task(current.wait_closed())
            await asyncio.sleep(0)
            assert not draining.done() and await current.ready() is None
        finally:
            release.set()
            current.invalidate()
            if draining is not None:
                await draining
            else:
                await current.wait_closed()
        assert await current.ready() is None
    asyncio.run(run())


def test_registry_capacity_binding_duplicate_and_epoch_aba():
    async def run():
        registry = ScopedStreamRegistry(capacity=1)
        snap = snapshot()
        first, second = stream(debounce=1, max_wait=1), stream(debounce=1, max_wait=1)
        try:
            with pytest.raises(ValueError, match="bound"):
                registry.register(state(snap), "utterance", first)
            await first.feed_partial(snap)
            registry.register(state(snap), "utterance", first)
            with pytest.raises(ValueError, match="already"):
                registry.register(state(snap), "utterance", first)
            other = replace(snap, identity=replace(snap.identity, utterance_id="second"))
            await second.feed_partial(other)
            with pytest.raises(ValueError, match="capacity"):
                registry.register(state(other), "second", second)
            # On after Off is still a different epoch; old On preparation dies.
            registry.preference_changed(LiveMemoryPreference("user", "workspace", True, 2))
            await until(lambda: first._closed)
        finally:
            first.invalidate()
            second.invalidate()
            await first.wait_closed()
            await second.wait_closed()
    asyncio.run(run())


def test_registry_rejects_foreign_loop_and_reports_closed_owner_loop():
    async def foreign_loop():
        snap = snapshot()
        current = stream(debounce=1, max_wait=1)
        registry = ScopedStreamRegistry(capacity=1)
        await current.feed_partial(snap)
        async def attempt():
            with pytest.raises(ValueError, match="owning loop"):
                registry.register(state(snap), "utterance", current)
        try:
            await asyncio.to_thread(lambda: asyncio.run(attempt()))
        finally:
            current.invalidate()
            await current.wait_closed()
    asyncio.run(foreign_loop())
    registry = ScopedStreamRegistry(capacity=1)
    async def closed_owner():
        snap = snapshot()
        current = stream(debounce=1, max_wait=1)
        await current.feed_partial(snap)
        registry.register(state(snap), "utterance", current)
        # asyncio.run closes this owning loop and cancels its pending debounce.
    asyncio.run(closed_owner())
    with pytest.raises(RuntimeError, match="loop is unavailable"):
        registry.preference_changed(LiveMemoryPreference("user", "workspace", False, 1))
