from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from app.vault_runtime.decision_routing.contracts import (
    CandidateChoice, EvidenceRef, InputIdentity, ScopedPrincipalRef,
)
from app.vault_runtime.memory.retrieval import RetrievalMatch


@dataclass(frozen=True, slots=True)
class InputSnapshot:
    scope: ScopedPrincipalRef
    identity: InputIdentity
    text: str
    context_sources: tuple[EvidenceRef, ...]
    context_fingerprint: str
    validity_fingerprint: str

    def __post_init__(self):
        if self.identity.revision < 0 or not self.context_fingerprint or not self.validity_fingerprint:
            raise ValueError("Incomplete snapshot identity")
        if self.identity.input_fingerprint != sha256(self.text.encode()).hexdigest():
            raise ValueError("Input fingerprint mismatch")
        if not all((self.scope.user_id, self.scope.workspace_id, self.scope.local_session_id,
                    self.identity.conversation_id, self.identity.segment_id, self.identity.utterance_id)):
            raise ValueError("Incomplete scope identity")


@dataclass(frozen=True, slots=True)
class PreparedContext:
    snapshot: InputSnapshot
    memories: tuple[RetrievalMatch, ...]
    decisions: tuple[CandidateChoice, ...]


@dataclass(frozen=True, slots=True)
class ReusePlan:
    """Only an actual relevance/version/authority validator may mark complete."""

    memories: tuple[RetrievalMatch, ...] = ()
    decisions: tuple[CandidateChoice, ...] = ()
    memory_complete: bool = False
    decisions_complete: bool = False


class PreparationPorts(Protocol):
    def is_current(self, snapshot: InputSnapshot, prepared: PreparedContext | None) -> bool: ...

    def reuse(self, snapshot: InputSnapshot, previous: PreparedContext | None) -> ReusePlan: ...

    def recall(self, snapshot: InputSnapshot,
               retained: tuple[RetrievalMatch, ...]) -> tuple[RetrievalMatch, ...]: ...

    def decisions(self, snapshot: InputSnapshot, memories: tuple[RetrievalMatch, ...],
                  retained: tuple[CandidateChoice, ...]) -> tuple[CandidateChoice, ...]: ...


class StalePreparation(RuntimeError):
    """No current evidence; consumer uses normal final retrieval/reasoning."""
