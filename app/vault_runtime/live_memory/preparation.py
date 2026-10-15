from __future__ import annotations

import asyncio
from time import monotonic
from uuid import uuid4
from collections.abc import Callable, Mapping
from app.vault_runtime.decision_routing.diagnostics import LiveDiagnostics

from .contracts import InputSnapshot, PreparationPorts, PreparedContext, StalePreparation


class WorkerBudget:
    """Loop-owned permits account for actual threads, including canceled waiters."""

    def __init__(self, *, global_limit: int, user_limits: Mapping[str, int]):
        if type(global_limit) is not int or global_limit < 1 or not user_limits:
            raise ValueError("Explicit positive worker limits required")
        if any(not user or type(limit) is not int or limit < 1 for user, limit in user_limits.items()):
            raise ValueError("Explicit positive user limits required")
        self._global = asyncio.Semaphore(global_limit)
        self._users = {user: asyncio.Semaphore(limit) for user, limit in user_limits.items()}
        self._jobs: set[asyncio.Task] = set()

    def register_user(self, user_id: str, *, limit: int):
        """Owning-loop admission for accounts created after runtime startup."""
        if not user_id or type(limit) is not int or limit < 1:
            raise ValueError("Explicit positive user allocation required")
        if user_id not in self._users:
            if len(self._users) >= 32:
                raise ValueError("Worker user allocation capacity reached")
            self._users[user_id] = asyncio.Semaphore(limit)

    async def run(self, user_id: str, function: Callable, *args):
        if user_id not in self._users:
            raise ValueError("User has no worker allocation")

        async def work():
            async with self._users[user_id], self._global:
                return await asyncio.to_thread(function, *args)

        task = asyncio.create_task(work())
        self._jobs.add(task)

        def finished(job):
            self._jobs.discard(job)
            if not job.cancelled():
                job.exception()  # Retrieve failures even if the waiter was canceled.

        task.add_done_callback(finished)
        return await asyncio.shield(task)

    async def drain(self):
        while self._jobs:
            await asyncio.gather(*(asyncio.shield(job) for job in tuple(self._jobs)),
                                 return_exceptions=True)


class ParallelPreparation:
    """One evolving snapshot, parallel recall/decisions, one dependent reconsideration."""

    def __init__(self, *, ports: PreparationPorts, workers: WorkerBudget, diagnostics=None, on_memory=None,
                 on_decisions=None, publishable=None, decision_gate=None):
        self.ports = ports
        self.workers = workers
        self.on_memory = on_memory
        self.on_decisions = on_decisions
        # Optional host check for interim branch results. A host may publish a result for an
        # earlier revision of the same utterance while it is still authorized (live speech moves
        # faster than lookups). Without it, interim results require the exact current revision.
        self.publishable = publishable
        # Optional async host cadence for the decision branch (for example, wait for a pause in
        # speech). It may raise StalePreparation to abandon this attempt; memory still publishes.
        self.decision_gate = decision_gate
        self.diagnostics = diagnostics if diagnostics is not None else LiveDiagnostics()

    def emit(self, event, snapshot, **fields):
        try:
            self.diagnostics.emit(event, snapshot, **fields)
        except Exception:
            pass

    async def current(self, snapshot, prepared, live: Callable[[], bool]):
        def validate():
            return live() and self.ports.is_current(snapshot, prepared) and live()

        return await self.workers.run(snapshot.scope.user_id, validate)

    async def _publishable(self, snapshot, interim, live):
        if self.publishable is None:
            return await self.current(snapshot, interim, live)
        return await self.workers.run(snapshot.scope.user_id, self.publishable, interim)

    async def prepare(self, snapshot: InputSnapshot, previous: PreparedContext | None,
                      live: Callable[[], bool]) -> PreparedContext:
        attempt_id, started = str(uuid4()), monotonic()
        self.emit("preparation_started",snapshot,attempt_id=attempt_id)
        async def call(function, *args):
            def guarded():
                if not live() or not self.ports.is_current(snapshot, None) or not live():
                    self.emit("preparation_stale",snapshot,attempt_id=attempt_id,reason="stale")
                    raise StalePreparation()
                return function(snapshot, *args)

            return await self.workers.run(snapshot.scope.user_id, guarded)

        reuse = await call(self.ports.reuse, previous)
        self.emit("reuse_checked",snapshot,attempt_id=attempt_id,memory_count=len(reuse.memories),decision_count=len(reuse.decisions),
            memory_reused=reuse.memory_complete,decisions_reused=reuse.decisions_complete)

        async def recall():
            if reuse.memory_complete:
                return reuse.memories
            recalled = await call(self.ports.recall, reuse.memories)
            self.emit("memory_lookup_complete",snapshot,attempt_id=attempt_id,memory_count=len(recalled))
            if self.on_memory is not None:
                interim = PreparedContext(snapshot, tuple(recalled), ())
                if await self._publishable(snapshot, interim, live):
                    self.on_memory(interim)
            return recalled

        async def decide():
            if reuse.decisions_complete:
                return reuse.decisions
            if self.decision_gate is not None:
                await self.decision_gate(snapshot)
            choices = await call(self.ports.decisions, reuse.memories, reuse.decisions)
            self.emit("decision_lookup_complete",snapshot,attempt_id=attempt_id,decision_count=len(choices))
            if self.on_decisions is not None:
                interim = PreparedContext(snapshot, (), tuple(choices))
                if await self._publishable(snapshot, interim, live):
                    self.on_decisions(interim)
            return choices

        # Drain both branches even on failure, so a stream's wait_closed does not
        # finish while a sibling retrieval is still executing in a thread.
        results = await asyncio.gather(recall(), decide(), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                self.emit("preparation_stale" if isinstance(result,StalePreparation) else "preparation_failed",
                    snapshot,attempt_id=attempt_id,reason="stale" if isinstance(result,StalePreparation) else "failed")
                raise result
        memories, decisions = results
        # A decision computed from the initial cache is invalid if new memory arrived.
        # Never publish it as current while reconsideration is outstanding.
        if getattr(self.ports, "decisions_depend_on_memory", True) and memories != reuse.memories:
            self.emit("decision_reconsidered",snapshot,attempt_id=attempt_id,reason="fresh_memory",memory_count=len(memories))
            decisions = await call(self.ports.decisions, memories, ())
        prepared = PreparedContext(snapshot, tuple(memories), tuple(decisions))
        if not await self.current(snapshot, prepared, live):
            self.emit("preparation_stale",snapshot,attempt_id=attempt_id,reason="stale")
            raise StalePreparation()
        self.emit("preparation_ready",snapshot,attempt_id=attempt_id,memory_count=len(memories),
            decision_count=len(decisions),elapsed_ms=(monotonic()-started)*1000)
        return prepared
