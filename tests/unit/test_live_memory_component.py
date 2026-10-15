import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import threading
import tomllib

import pytest

from app.vault_runtime.decision_routing.contracts import CandidateChoice, InputIdentity, ScopedPrincipalRef
from app.vault_runtime.live_memory.contracts import InputSnapshot, ReusePlan
from app.vault_runtime.live_memory.preparation import ParallelPreparation, WorkerBudget
from app.vault_runtime.live_memory.voicemem_stream import VoiceMemStream
from app.vault_runtime.memory.models import MemoryRecord
from app.vault_runtime.memory.retrieval import RetrievalMatch


def snapshot(text="ABC invoice", revision=1, *, final=False, **changes):
    return replace(InputSnapshot(
        ScopedPrincipalRef("user", "workspace", "login"),
        InputIdentity("conversation", "segment", "utterance", revision,
                      "turn" if final else None, sha256(text.encode()).hexdigest()),
        text, (), "context-1", "authority-memory-preference-generation-1",
    ), **changes)


def memory(content="ABC invoice"):
    now = datetime(2026, 10, 7, tzinfo=timezone.utc)
    return RetrievalMatch(MemoryRecord(
        "memory", "workspace", "user", "private", "user", "project", "fact",
        "invoice", content, "user_asserted", "high", "normal", "active", 1, now, now,
    ), 1.0, ("exact",))


def choice(value):
    return CandidateChoice(value, value, 1, "Synthetic test candidate, not a learned rule")


class Ports:
    def __init__(self):
        self.allowed = True
        self.calls = []

    def is_current(self, snap, prepared):
        return self.allowed

    def reuse(self, snap, previous):
        self.calls.append(("reuse", snap, previous))
        return ReusePlan()

    def recall(self, snap, retained):
        self.calls.append(("recall", snap, retained))
        return (memory(snap.text),)

    def decisions(self, snap, memories, retained):
        self.calls.append(("decisions", snap, memories, retained))
        return (choice(memories[0].memory.content_text if memories else "missing-context"),)


def stream(ports=None, *, workers=None, debounce=0, max_wait=0.1, meaningful=lambda snap: True):
    ports = ports or Ports()
    workers = workers or WorkerBudget(global_limit=4, user_limits={"user": 4})
    return VoiceMemStream(ParallelPreparation(ports=ports, workers=workers),
                          debounce_s=debounce, max_wait_s=max_wait, meaningful=meaningful)


async def until(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0.001)


async def settle(s):
    if s._spec:
        await asyncio.shield(s._spec)
    return await s.ready()


def test_parallel_memory_and_decisions_then_memory_dependent_reconsideration():
    async def run():
        barrier = threading.Barrier(2, timeout=2)

        class Concurrent(Ports):
            def recall(self, snap, retained):
                barrier.wait()
                return super().recall(snap, retained)

            def decisions(self, snap, memories, retained):
                if not memories:
                    barrier.wait()
                return super().decisions(snap, memories, retained)

        ports = Concurrent()
        s = stream(ports)
        snap = snapshot()
        await s.feed_partial(snap)
        result = await settle(s)
        assert result.snapshot is snap
        assert result.decisions == (choice(snap.text),)
        calls = [call for call in ports.calls if call[0] == "decisions"]
        assert len(calls) == 2 and calls[0][2] == () and calls[1][2] == result.memories
        assert all(call[1] is snap for call in ports.calls)
    asyncio.run(run())


@pytest.mark.parametrize("new_text", ["ABC invoice tomorrow", "not ABC invoice", "Sarah invoice", "", "ABC invoice"])
def test_edits_invalidate_and_drop_or_research_current_revision(new_text):
    async def run():
        ports = Ports()
        s = stream(ports)
        await s.feed_partial(snapshot())
        first = await settle(s)
        assert first is not None
        await s.feed_partial(snapshot(new_text, 2))
        assert s._last_memory is None
        current = await settle(s)
        if not new_text:
            assert current is None and s._previous is None
        else:
            assert current.snapshot.identity.revision == 2
            assert current.memories[0].memory.content_text == new_text
            assert current.decisions[0].value == new_text
    asyncio.run(run())


def test_validated_continuation_reuses_both_branches_without_search():
    async def run():
        class Retain(Ports):
            def reuse(self, snap, previous):
                super().reuse(snap, previous)
                if previous and snap.text == previous.snapshot.text + " please":
                    return ReusePlan(previous.memories, previous.decisions, True, True)
                return ReusePlan()

        ports = Retain()
        s = stream(ports)
        await s.feed_partial(snapshot())
        previous = await settle(s)
        counts = [c[0] for c in ports.calls].count("recall")
        await s.feed_partial(snapshot("ABC invoice please", 2))
        current = await settle(s)
        assert current.snapshot.identity.revision == 2
        assert current.memories == previous.memories and current.decisions == previous.decisions
        assert [c[0] for c in ports.calls].count("recall") == counts
    asyncio.run(run())


def test_late_result_and_aba_do_not_revive_old_revision():
    async def run():
        started, release = threading.Event(), threading.Event()

        class Blocked(Ports):
            def recall(self, snap, retained):
                if snap.identity.revision == 1:
                    started.set()
                    assert release.wait(2)
                return super().recall(snap, retained)

        ports = Blocked()
        s = stream(ports)
        try:
            await s.feed_partial(snapshot())
            await until(started.is_set)
            await s.feed_partial(snapshot("Sarah invoice", 2))
            await s.feed_partial(snapshot("ABC invoice", 3))
            assert await s.ready() is None
            release.set()
            result = await settle(s)
            assert result.snapshot.identity.revision == 3
            assert not any(c[1].identity.revision == 2 for c in ports.calls)
        finally:
            release.set()
            s.invalidate()
            await s.wait_closed()
    asyncio.run(run())


@pytest.mark.parametrize("flag", ["composing", "enabled"])
def test_ime_and_off_clear_work_and_same_identity_resume_cannot_publish_old_job(flag):
    async def run():
        started, release = threading.Event(), threading.Event()

        class Blocked(Ports):
            def recall(self, snap, retained):
                started.set()
                assert release.wait(2)
                return super().recall(snap, retained)

        ports = Blocked()
        s = stream(ports)
        snap = snapshot()
        try:
            await s.feed_partial(snap)
            await until(started.is_set)
            await s.feed_partial(snap, **{flag: flag == "composing"})
            assert s._previous is None and await s.ready() is None
            release.set()
            await settle(s)
            assert await s.ready() is None
            before = len(ports.calls)
            await s.feed_partial(snap)
            assert await settle(s) is not None
            assert len(ports.calls) > before
            with pytest.raises(ValueError, match="Out-of-order"):
                await s.feed_partial(snapshot(revision=0))
        finally:
            release.set()
            s.invalidate()
            await s.wait_closed()
    asyncio.run(run())


def test_meaningful_threshold_is_injected_not_character_count():
    async def run():
        ports = Ports()
        s = stream(ports, meaningful=lambda snap: "invoice" in snap.text)
        await s.feed_partial(snapshot("what"))
        assert not ports.calls and s._spec is None
        await s.feed_partial(snapshot("invoice", 2))
        assert await settle(s) is not None
    asyncio.run(run())


def test_max_wait_offers_preparation_during_continuous_typing():
    async def run():
        ports = Ports()
        attempts = []

        class ObservedStream(VoiceMemStream):
            async def _speculate(self, snap, event):
                attempts.append(snap.identity.revision)
                return await super()._speculate(snap, event)

        base = stream(ports, debounce=0.03, max_wait=0.05)
        s = ObservedStream(base.preparation, debounce_s=0.03, max_wait_s=0.05,
                          meaningful=lambda snap: True)
        try:
            for rev in range(1, 18):
                await s.feed_partial(snapshot(f"invoice {rev}", rev))
                await asyncio.sleep(0.01)
            # Maximum wait promises a scheduling opportunity, not thread startup
            # latency or a result despite continual invalidation/contention.
            assert any(revision < 17 for revision in attempts)
            assert (await settle(s)).snapshot.identity.revision == 17
        finally:
            s.invalidate()
            await s.wait_closed()
    asyncio.run(run())


def test_ready_rechecks_authority_and_versions():
    async def run():
        ports = Ports()
        s = stream(ports)
        await s.feed_partial(snapshot())
        assert await settle(s)
        ports.allowed = False
        assert await s.ready() is None
        assert s._last_memory is None
    asyncio.run(run())


@pytest.mark.parametrize("kind", ["scope", "session", "utterance", "conflict", "out_of_order", "partial_turn"])
def test_rejects_conflicting_or_cross_scope_identity(kind):
    async def run():
        s = stream()
        snap = snapshot()
        await s.feed_partial(snap)
        await settle(s)
        new = {
            "scope": snapshot(revision=2, scope=ScopedPrincipalRef("other", "workspace", "login")),
            "session": snapshot(revision=2, scope=ScopedPrincipalRef("user", "workspace", "other-login")),
            "utterance": replace(snapshot(revision=2), identity=replace(snapshot(revision=2).identity, utterance_id="other")),
            "conflict": snapshot("not invoice", 1),
            "out_of_order": snapshot(revision=0),
            "partial_turn": snapshot(final=True),
        }[kind]
        with pytest.raises(ValueError):
            await s.feed_partial(new)
    asyncio.run(run())


def test_exact_final_revalidates_and_rebinds_without_new_retrieval():
    async def run():
        ports = Ports()
        s = stream(ports)
        await s.feed_partial(snapshot())
        partial = await settle(s)
        count = len(ports.calls)
        final = await s.finalize(snapshot(final=True), timeout_s=1)
        assert final.snapshot.identity.turn_id == "turn" and final.memories == partial.memories
        assert len(ports.calls) == count
        with pytest.raises(ValueError, match="closed"):
            await s.feed_partial(snapshot(revision=2))
    asyncio.run(run())


def test_changed_final_never_relabels_partial_results_and_bypasses_debounce():
    async def run():
        s = stream(debounce=0.1, max_wait=0.2)
        await s.feed_partial(snapshot())
        await settle(s)
        final = await s.finalize(snapshot("not ABC invoice", 2, final=True), timeout_s=0.08)
        assert final and final.memories[0].memory.content_text == "not ABC invoice"
        assert final.decisions == (choice("not ABC invoice"),)
    asyncio.run(run())


def test_final_while_partial_worker_pending():
    async def run():
        started, release = threading.Event(), threading.Event()

        class Blocked(Ports):
            def recall(self, snap, retained):
                if not snap.identity.turn_id:
                    started.set()
                    assert release.wait(2)
                return super().recall(snap, retained)

        s = stream(Blocked())
        try:
            await s.feed_partial(snapshot())
            await until(started.is_set)
            task = asyncio.create_task(s.finalize(snapshot("Sarah invoice", 2, final=True), timeout_s=1))
            await until(lambda: s._sealed)
            release.set()
            final = await task
            assert final.snapshot.identity.turn_id and final.memories[0].memory.content_text == "Sarah invoice"
        finally:
            release.set()
            s.invalidate()
            await s.wait_closed()
    asyncio.run(run())


@pytest.mark.parametrize("cancel", [False, True])
def test_final_timeout_or_cancel_invalidates_late_threads(cancel):
    async def run():
        started, release = threading.Event(), threading.Event()

        class Blocked(Ports):
            def recall(self, snap, retained):
                started.set()
                assert release.wait(2)
                return super().recall(snap, retained)

        s = stream(Blocked())
        try:
            task = asyncio.create_task(s.finalize(snapshot(final=True), timeout_s=1 if cancel else 0.05))
            await until(started.is_set)
            if cancel:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                assert await task is None and s.failure == "final_timeout"
            assert s._closed and s._text == "" and await s.ready() is None
            release.set()
            await s.wait_closed()
            assert await s.ready() is None
        finally:
            release.set()
            await s.preparation.workers.drain()
    asyncio.run(run())


def test_canceled_waiter_does_not_release_global_or_user_thread_permits():
    async def run():
        started, release, second = threading.Event(), threading.Event(), threading.Event()
        workers = WorkerBudget(global_limit=1, user_limits={"user": 1, "other": 1})

        def blocked():
            started.set()
            assert release.wait(2)

        try:
            first = asyncio.create_task(workers.run("user", blocked))
            await until(started.is_set)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            next_job = asyncio.create_task(workers.run("other", second.set))
            await asyncio.sleep(0.03)
            assert not second.is_set() and len(workers._jobs) == 2
            release.set()
            await next_job
            await workers.drain()
            assert second.is_set() and not workers._jobs
        finally:
            release.set()
            await workers.drain()
    asyncio.run(run())


def test_noop_preparation_and_empty_final_have_truthful_no_effects():
    async def run():
        class Noop(Ports):
            def recall(self, snap, retained):
                return ()

            def decisions(self, snap, memories, retained):
                return ()

        s = stream(Noop())
        final = await s.finalize(snapshot(final=True), timeout_s=1)
        assert final.memories == final.decisions == ()
        empty = stream()
        assert await empty.finalize(snapshot("", final=True), timeout_s=1) is None
        assert empty._closed
    asyncio.run(run())


def test_provider_failure_is_not_empty_evidence_or_raw_log(capsys):
    async def run():
        class Failure(Ports):
            def recall(self, snap, retained):
                raise RuntimeError("SECRET draft payload")

        s = stream(Failure())
        await s.feed_partial(snapshot())
        assert await settle(s) is None and s.failure == "preparation_failed"
        await s.preparation.workers.drain()
    asyncio.run(run())
    assert "SECRET" not in capsys.readouterr().out


def test_license_bytes_and_wheel_package_data_preserved():
    root = Path(__file__).resolve().parents[2]
    license_file = root / "app/vault_runtime/live_memory/VOICE_MEM_LICENSE.txt"
    assert sha256(license_file.read_bytes()).hexdigest() == "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
    config = tomllib.loads((root / "pyproject.toml").read_text())
    assert config["tool"]["setuptools"]["package-data"]["app.vault_runtime.live_memory"] == ["VOICE_MEM_LICENSE.txt"]


@pytest.mark.parametrize("limits", [{"global_limit": 0, "user_limits": {"user": 1}},
                                    {"global_limit": 1, "user_limits": {}},
                                    {"global_limit": 1, "user_limits": {"user": False}}])
def test_no_invented_worker_defaults(limits):
    with pytest.raises(ValueError):
        WorkerBudget(**limits)


def test_input_fingerprint_and_deadline_validation():
    with pytest.raises(ValueError, match="fingerprint"):
        replace(snapshot(), text="different")

    async def run():
        with pytest.raises(ValueError):
            await stream().finalize(snapshot(final=True), timeout_s=0)
    asyncio.run(run())


def test_final_revocation_cannot_reuse_prepared_context():
    async def run():
        ports = Ports()
        s = stream(ports)
        await s.feed_partial(snapshot())
        assert await settle(s)
        ports.allowed = False
        assert await s.finalize(snapshot(final=True), timeout_s=1) is None
        assert await s.ready() is None
    asyncio.run(run())


def test_context_or_epoch_change_with_same_text_forces_current_preparation():
    async def run():
        s = stream()
        await s.feed_partial(snapshot())
        first = await settle(s)
        updated = snapshot(revision=2, context_fingerprint="new-conversation-context",
                           validity_fingerprint="new-memory-or-policy-epoch")
        await s.feed_partial(updated)
        assert s._last_memory is None
        second = await settle(s)
        assert second.snapshot is updated and second.snapshot != first.snapshot
    asyncio.run(run())


def test_resuming_identical_snapshot_before_old_thread_finishes_is_new_event():
    async def run():
        started, release = threading.Event(), threading.Event()

        class Blocked(Ports):
            def recall(self, snap, retained):
                started.set()
                assert release.wait(2)
                return super().recall(snap, retained)

        ports = Blocked()
        s = stream(ports)
        snap = snapshot()
        try:
            await s.feed_partial(snap)
            await until(started.is_set)
            await s.feed_partial(snap, enabled=False)
            await s.feed_partial(snap)
            release.set()
            result = await settle(s)
            assert result is not None
            assert [c[0] for c in ports.calls].count("recall") == 2
        finally:
            release.set()
            s.invalidate()
            await s.wait_closed()
    asyncio.run(run())


def test_per_user_budget_does_not_block_another_user_or_release_on_cancel():
    async def run():
        started, release, same, other = [threading.Event() for _ in range(4)]
        workers = WorkerBudget(global_limit=2, user_limits={"user": 1, "other": 1})

        def blocked():
            started.set()
            assert release.wait(2)

        try:
            first = asyncio.create_task(workers.run("user", blocked))
            await until(started.is_set)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            same_job = asyncio.create_task(workers.run("user", same.set))
            await workers.run("other", other.set)
            assert other.is_set() and not same.is_set()
            release.set()
            await same_job
        finally:
            release.set()
            await workers.drain()
    asyncio.run(run())


def test_changed_recalled_memory_invalidates_even_complete_retained_decisions():
    async def run():
        class RetainDecision(Ports):
            def reuse(self, snap, previous):
                return ReusePlan((), (choice("old-route"),), False, True)

        s = stream(RetainDecision())
        await s.feed_partial(snapshot())
        assert (await settle(s)).decisions == (choice("ABC invoice"),)
    asyncio.run(run())


def test_guard_failure_during_publication_drops_all_candidates():
    async def run():
        class Revoked(Ports):
            def is_current(self, snap, prepared):
                return prepared is None

        s = stream(Revoked())
        await s.feed_partial(snapshot())
        assert await settle(s) is None
        assert s._previous is None
    asyncio.run(run())


def test_invalidation_during_final_guard_cannot_publish_rebound_context():
    async def run():
        entered, release = threading.Event(), threading.Event()

        class SlowGuard(Ports):
            def is_current(self, snap, prepared):
                if snap.identity.turn_id and prepared:
                    entered.set()
                    assert release.wait(2)
                return True

        s = stream(SlowGuard())
        try:
            await s.feed_partial(snapshot())
            assert await settle(s)
            task = asyncio.create_task(s.finalize(snapshot(final=True), timeout_s=1))
            await until(entered.is_set)
            s.invalidate()
            release.set()
            assert await task is None
            assert await s.ready() is None
        finally:
            release.set()
            await s.preparation.workers.drain()
    asyncio.run(run())


def test_off_during_slow_initial_guard_does_not_start_retrieval():
    async def run():
        entered, release = threading.Event(), threading.Event()

        class SlowGuard(Ports):
            def is_current(self, snap, prepared):
                entered.set()
                assert release.wait(2)
                return True

        ports = SlowGuard()
        s = stream(ports)
        try:
            await s.feed_partial(snapshot())
            await until(entered.is_set)
            await s.feed_partial(snapshot(), enabled=False)
            release.set()
            assert await settle(s) is None
            assert not ports.calls
        finally:
            release.set()
            s.invalidate()
            await s.wait_closed()
    asyncio.run(run())


def test_failed_branch_does_not_allow_shutdown_before_sibling_thread_finishes():
    async def run():
        entered, release = threading.Event(), threading.Event()

        class FailureAndSlow(Ports):
            def recall(self, snap, retained):
                raise RuntimeError("read failed")

            def decisions(self, snap, memories, retained):
                entered.set()
                assert release.wait(2)
                return ()

        s = stream(FailureAndSlow())
        try:
            await s.feed_partial(snapshot())
            await until(entered.is_set)
            s.invalidate()
            draining = asyncio.create_task(s.wait_closed())
            await asyncio.sleep(0.02)
            assert not draining.done()
            release.set()
            await draining
            await s.preparation.workers.drain()
            assert not s.preparation.workers._jobs
        finally:
            release.set()
            await s.preparation.workers.drain()
    asyncio.run(run())

@pytest.mark.parametrize('blocked_branch', ['memory', 'decisions'])
def test_independent_preparation_publishes_either_branch_without_waiting(blocked_branch):
    async def run():
        release = threading.Event()
        published = []
        class Independent(Ports):
            decisions_depend_on_memory = False
            def recall(self, snap, retained):
                if blocked_branch == 'memory':
                    assert release.wait(2)
                return super().recall(snap, retained)
            def decisions(self, snap, memories, retained):
                assert memories == ()
                self.calls.append(('decisions', snap, memories, retained))
                if blocked_branch == 'decisions':
                    assert release.wait(2)
                return (choice('tool'),)
        ports = Independent()
        workers = WorkerBudget(global_limit=4, user_limits={'user': 4})
        preparation = ParallelPreparation(ports=ports, workers=workers,
            on_memory=lambda p: published.append(('memory', p)),
            on_decisions=lambda p: published.append(('decisions', p)))
        task = asyncio.create_task(preparation.prepare(snapshot(), None, lambda: True))
        try:
            await until(lambda: bool(published))
            assert published[0][0] != blocked_branch
            assert not task.done()
        finally:
            release.set()
        result = await task
        assert result.memories and result.decisions == (choice('tool'),)
        assert len([call for call in ports.calls if call[0] == 'decisions']) == 1
        assert {branch for branch, _ in published} == {'memory', 'decisions'}
    asyncio.run(run())


def test_host_publishable_check_keeps_memory_from_an_earlier_revision_of_the_same_utterance():
    async def run():
        published, checked = [], []
        live = {"current": True}
        def publishable(prepared):
            checked.append(prepared.snapshot.identity.revision)
            return True  # Host: same utterance, authority still current.
        class Ports2(Ports):
            def recall(self, snap, retained):
                live["current"] = False  # The user kept speaking while recall ran.
                return super().recall(snap, retained)
        preparation = ParallelPreparation(ports=Ports2(), workers=WorkerBudget(global_limit=4, user_limits={"user": 4}),
            on_memory=published.append, publishable=publishable)
        with pytest.raises(Exception):
            await preparation.prepare(snapshot(), None, lambda: live["current"])
        assert [p.snapshot.identity.revision for p in published] == [1] and checked == [1]
        # Without a host check, an interim result requires the exact current revision.
        live["current"] = True
        strict = []
        preparation = ParallelPreparation(ports=Ports2(), workers=WorkerBudget(global_limit=4, user_limits={"user": 4}),
            on_memory=strict.append)
        with pytest.raises(Exception):
            await preparation.prepare(snapshot(), None, lambda: live["current"])
        assert strict == []
    asyncio.run(run())


def test_decision_gate_abandons_selection_without_blocking_memory():
    from app.vault_runtime.live_memory.contracts import StalePreparation
    async def run():
        published = []
        ports = Ports()
        ports.decisions_depend_on_memory = False
        async def still_speaking(_snapshot):
            raise StalePreparation()
        preparation = ParallelPreparation(ports=ports, workers=WorkerBudget(global_limit=4, user_limits={"user": 4}),
            on_memory=published.append, decision_gate=still_speaking)
        with pytest.raises(StalePreparation):
            await preparation.prepare(snapshot(), None, lambda: True)
        assert published and published[0].memories
        assert not [call for call in ports.calls if call[0] == "decisions"]  # No selection call was made.
    asyncio.run(run())
