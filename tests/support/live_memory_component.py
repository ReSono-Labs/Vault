"""Shared test helpers moved out of test modules (TST-01)."""

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256

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
