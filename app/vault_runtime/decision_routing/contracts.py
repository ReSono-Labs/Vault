from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

SELECTOR_CONTRACT_VERSION = 1
FALLBACK_VALUE = "__fallback__"


class InputError(ValueError):
    """Invalid local selector request; never hide this as provider unavailability."""


class TransportTimeout(RuntimeError):
    pass


class TransportUnavailable(RuntimeError):
    pass


class Clock(Protocol):
    def now(self) -> float: ...


class CancellationToken(Protocol):
    @property
    def is_cancelled(self) -> bool: ...


class DecisionTransport(Protocol):
    def evaluate(self, payload: dict, *, timeout_seconds: float) -> dict: ...


@dataclass(frozen=True, slots=True)
class ScopedPrincipalRef:
    user_id: str
    workspace_id: str
    local_session_id: str


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    source_id: str
    source_kind: str
    source_authority: str
    text: str


@dataclass(frozen=True, slots=True)
class InputIdentity:
    conversation_id: str
    segment_id: str
    utterance_id: str
    revision: int
    turn_id: str | None
    input_fingerprint: str


@dataclass(frozen=True, slots=True)
class CandidateChoice:
    value: str
    definition_id: str
    definition_version: int
    applicability_description: str


@dataclass(frozen=True, slots=True)
class SelectionRequest:
    request_id: str
    scope: ScopedPrincipalRef
    input_identity: InputIdentity
    phase: Literal["provisional", "final"]
    input_text: str
    context_sources: tuple[EvidenceRef, ...]
    context_fingerprint: str
    candidate_set: tuple[CandidateChoice, ...]
    candidate_set_fingerprint: str
    capability_snapshot_fingerprint: str
    generation_id: str | None
    selector_contract_version: int
    complete_context: bool


@dataclass(frozen=True, slots=True)
class ValidationToken:
    revision: int
    input_fingerprint: str
    context_fingerprint: str
    candidate_set_fingerprint: str
    capability_snapshot_fingerprint: str
    generation_id: str | None


@dataclass(frozen=True, slots=True)
class RequestIdentity:
    request_id: str
    scope: ScopedPrincipalRef
    input_identity: InputIdentity
    phase: Literal["provisional", "final"]
    validation_token: ValidationToken


@dataclass(frozen=True, slots=True)
class ChoiceProbability:
    value: str
    probability: float


@dataclass(frozen=True, slots=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_tokens: int | None = None
    cache_write_tokens: int | None = None
    reasoning_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    model: str | None = None
    usage: TokenUsage | None = None


@dataclass(frozen=True, slots=True)
class Selected:
    """Observation only. A consumer must independently validate execution authority."""

    definition_id: str
    version: int
    confidence: float
    probabilities: tuple[ChoiceProbability, ...]
    request_identity: RequestIdentity
    usage: TokenUsage | None
    model: str | None


FallbackReason = Literal[
    "no_candidates", "missing_context", "refusal", "timeout", "canceled",
    "unavailable", "invalid_response", "low_confidence", "stale", "no_supported_choice",
]


@dataclass(frozen=True, slots=True)
class Fallback:
    reason: FallbackReason
    request_identity: RequestIdentity
    provider_metadata: ProviderMetadata | None = None


SelectionResult = Selected | Fallback
