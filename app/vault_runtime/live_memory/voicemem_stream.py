"""External-text subset extracted from xzf-thu/VoiceMem, Apache-2.0.

Source: voicemem/stream.py at 6cacb3c1e7fca2679f3bf95451f6b480efd9a783.
Modified by ReSono Labs: canonical typed snapshots; empty/stale/final rejection;
coalescing instead of task cancellation; shared bounded preparation ports. Only
VoiceStream's external-text seam is retained, not ASR/stores/perception/persona.
See VOICE_MEM_LICENSE.txt and C05A source review for attribution and exact diff.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import replace
from hashlib import sha256
from math import isfinite

from .contracts import InputSnapshot, PreparedContext, StalePreparation
from .preparation import ParallelPreparation


class VoiceMemStream:
    def __init__(self, preparation: ParallelPreparation, *, debounce_s: float,
                 max_wait_s: float, meaningful: Callable[[InputSnapshot], bool]):
        if not all(isfinite(value) and value >= 0 for value in (debounce_s, max_wait_s)):
            raise ValueError("Finite nonnegative scheduling parameters required")
        if max_wait_s < debounce_s or max_wait_s == 0:
            raise ValueError("Maximum wait must be positive and at least debounce")
        self.preparation = preparation
        self.meaningful = meaningful
        self.debounce_s = debounce_s
        self.max_wait_s = max_wait_s
        self._text = ""
        self._current: InputSnapshot | None = None
        self._owner = None
        self._last_revision = -1
        self._last_payload = None
        self._event = 0
        self._spec: asyncio.Task | None = None
        self._pending: tuple[InputSnapshot, int] | None = None
        self._last_memory: PreparedContext | None = None
        self._previous: PreparedContext | None = None
        self._changed = asyncio.Event()
        self._burst_start: float | None = None
        self._due = 0.0
        self._sealed = False
        self._closed = False
        self.failure: str | None = None

    def _matches(self, snapshot, event=None):
        return (not self._closed and self._current == snapshot
                and (event is None or event == self._event))

    def _accept(self, snapshot, *, final=False):
        if self._closed or self._sealed:
            raise ValueError("Utterance closed; create another stream")
        owner = (snapshot.scope, snapshot.identity.conversation_id,
                 snapshot.identity.segment_id, snapshot.identity.utterance_id)
        if self._owner is not None and owner != self._owner:
            raise ValueError("Cannot switch stream scope/utterance")
        if bool(snapshot.identity.turn_id) != final:
            raise ValueError("Immutable final identity required only for final")
        comparable = replace(snapshot, identity=replace(snapshot.identity, turn_id=None))
        payload = sha256(repr(comparable).encode()).hexdigest()
        if snapshot.identity.revision < self._last_revision:
            raise ValueError("Out-of-order revision")
        if snapshot.identity.revision == self._last_revision and payload != self._last_payload:
            raise ValueError("Conflicting revision")
        self._last_revision, self._last_payload = snapshot.identity.revision, payload
        self._event += 1
        self._owner = owner
        self._current = snapshot
        self._text = snapshot.text  # Unlike donor, empty input replaces previous text.
        self._last_memory = None  # Every event invalidates the ready envelope.
        self.failure = None
        self.preparation.emit("revision_accepted",snapshot,event_sequence=self._event)

    async def _speculate(self, snapshot, event) -> PreparedContext:
        # Extracted work seam: classification/search become one canonical scoped
        # preparation port; it overlaps listening without producing a response.
        return await self.preparation.prepare(snapshot, self._previous,
                                              lambda: self._matches(snapshot, event))

    def _kick(self, snapshot, *, immediate=False):
        # Donor canceled/replaced each task. Keep actual work counted, coalescing
        # only the latest pending revision instead of pretending threads stopped.
        now = asyncio.get_running_loop().time()
        if self._burst_start is None:
            self._burst_start = now
        self._pending = (snapshot, self._event)
        self._due = now if immediate else min(now + self.debounce_s,
                                              self._burst_start + self.max_wait_s)
        self._changed.set()
        if self._spec is None or self._spec.done():
            self._spec = asyncio.create_task(self._pump())

    async def _pump(self):
        while self._pending is not None and not self._closed:
            self._changed.clear()
            delay = max(0.0, self._due - asyncio.get_running_loop().time())
            if delay:
                try:
                    await asyncio.wait_for(self._changed.wait(), delay)
                    continue
                except TimeoutError:
                    pass
            (snapshot, event), self._pending = self._pending, None
            self._burst_start = None
            try:
                prepared = await self._speculate(snapshot, event)
                if self._matches(snapshot, event):
                    self._last_memory = self._previous = prepared
            except StalePreparation:
                self.preparation.emit("preparation_stale",snapshot,event_sequence=event,reason="stale")
            except Exception:
                self.preparation.emit("preparation_failed",snapshot,event_sequence=event,reason="failed")
                if self._matches(snapshot, event):
                    self.failure = "preparation_failed"  # No raw draft/exception logging.

    async def _ready_memory(self):
        prepared = self._last_memory
        if prepared is not None:
            try:
                valid = await self.preparation.current(prepared.snapshot, prepared,
                                                      lambda: self._matches(prepared.snapshot))
            except Exception:
                valid = False
            if self._last_memory is not prepared:
                return None
            if not valid:
                self._last_memory = None
                return None
        return prepared

    async def feed_partial(self, snapshot: InputSnapshot, *, composing=False, enabled=True):
        self._accept(snapshot)
        if not enabled or composing or not self._text.strip():
            self.preparation.emit("draft_skipped",snapshot,event_sequence=self._event,
                reason="off" if not enabled else "composing" if composing else "empty")
            self._pending = None
            self._burst_start = None
            self._previous = None
            self._changed.set()
            # Also invalidate a running job whose snapshot is otherwise identical.
            self._current = None
            return None
        if self.meaningful(snapshot):
            self._kick(snapshot)
        else:
            self.preparation.emit("draft_skipped",snapshot,event_sequence=self._event,reason="not_meaningful")
            self._pending = None
            self._burst_start = None
            self._changed.set()
        return None  # New result is retrieved explicitly, never stale donor _last_memory.

    async def ready(self):
        return await self._ready_memory()

    async def _confirm(self, snapshot: InputSnapshot, *, timeout_s: float):
        if not isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("Explicit positive final deadline required")
        previous = self._last_memory
        self._accept(snapshot, final=True)
        self._sealed = True
        try:
            async with asyncio.timeout(timeout_s):
                if previous is not None:
                    comparable = replace(snapshot, identity=replace(snapshot.identity, turn_id=None))
                    if comparable == previous.snapshot:
                        rebound = replace(previous, snapshot=snapshot)
                        if (await self.preparation.current(snapshot, rebound,
                                                           lambda: self._matches(snapshot))
                                and self._matches(snapshot)):
                            self._last_memory = self._previous = rebound
                            self._pending = None
                            self._changed.set()
                            self.preparation.emit("final_reused",snapshot,event_sequence=self._event,
                                memory_count=len(rebound.memories),decision_count=len(rebound.decisions))
                            return rebound
                        self.preparation.emit("final_preparation_rejected",snapshot,event_sequence=self._event,reason="stale")
                    else:
                        self.preparation.emit("final_preparation_rejected",snapshot,event_sequence=self._event,reason="not_exact")
                if not self._text.strip():
                    self.invalidate()
                    return None
                self.preparation.emit("final_researched",snapshot,event_sequence=self._event)
                self._kick(snapshot, immediate=True)
                await asyncio.shield(self._spec)
                result = await self._ready_memory()
                self.preparation.emit("final_completed",snapshot,event_sequence=self._event,
                    reason="current" if result is not None else "stale")
                return result
        except TimeoutError:
            self.preparation.emit("final_timeout",snapshot,reason="timeout")
            self.invalidate()
            self.failure = "final_timeout"
            return None
        except asyncio.CancelledError:
            self.preparation.emit("final_canceled",snapshot,reason="canceled")
            self.invalidate()
            raise
        except Exception:
            self.invalidate()
            self.failure = "preparation_failed"
            return None

    async def finalize(self, snapshot: InputSnapshot, *, timeout_s: float):
        return await self._confirm(snapshot, timeout_s=timeout_s)

    def invalidate(self):
        if self._current is not None:
            self.preparation.emit("stream_invalidated",self._current,event_sequence=self._event)
        self._closed = True
        self._reset_turn()
        self._changed.set()

    def _reset_turn(self):
        # Extracted reset clears transient text and candidates, never canonical data.
        self._text = ""
        self._current = self._pending = self._last_memory = self._previous = None
        self._burst_start = None

    async def wait_closed(self):
        if not self._closed:
            raise ValueError("Invalidate before draining stream")
        if self._spec is not None:
            await asyncio.shield(self._spec)
