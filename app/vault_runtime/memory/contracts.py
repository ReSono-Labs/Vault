from __future__ import annotations

from dataclasses import dataclass

# Donor: ReSono-Labs-R1-Voice/runtime/resono_runtime/memory/contracts.py
# R1 contract names remain exact. Visibility is the required local multi-user
# scope adaptation frozen in the Phase 3 contract.
REVIEWER_CONTRACT_VERSION = 2
MEMORY_DOMAINS = frozenset(
    {"identity", "personal", "relationship", "environment", "project", "device", "platform"}
)
MEMORY_TYPES = frozenset(
    {"fact", "preference", "decision", "episode", "constraint", "correction"}
)
MEMORY_AUTHORITIES = frozenset({"user_asserted", "tool_verified", "model_derived"})
MEMORY_INTENTS = frozenset({"create", "confirm", "correct", "conflict"})
MEMORY_CONFIDENCE_LEVELS = frozenset({"low", "medium", "high"})
MEMORY_SENSITIVITIES = frozenset({"normal", "sensitive"})
MEMORY_VISIBILITIES = frozenset({"private", "workspace"})


class MemoryContractError(ValueError):
    pass


def _require(value: str, allowed: frozenset[str], field: str) -> str:
    normalized = value.strip()
    if normalized not in allowed:
        raise MemoryContractError(f"Invalid {field}: {value!r}")
    return normalized


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    subject_id: str
    domain: str
    memory_type: str
    memory_key: str
    content_text: str
    source_authority: str
    confidence: str
    sensitivity: str
    intent: str
    visibility: str = "private"

    def validated(self) -> "MemoryCandidate":
        subject_id = self.subject_id.strip()
        memory_key = self.memory_key.strip()
        content_text = self.content_text.strip()
        if not subject_id or not memory_key or not content_text:
            raise MemoryContractError("subject_id, memory_key and content_text are required")
        if len(memory_key) > 256 or len(content_text) > 4096:
            raise MemoryContractError("memory candidate exceeds its bounded size")
        return MemoryCandidate(
            subject_id=subject_id,
            domain=_require(self.domain, MEMORY_DOMAINS, "domain"),
            memory_type=_require(self.memory_type, MEMORY_TYPES, "memory_type"),
            memory_key=memory_key,
            content_text=content_text,
            source_authority=_require(self.source_authority, MEMORY_AUTHORITIES, "source_authority"),
            confidence=_require(self.confidence, MEMORY_CONFIDENCE_LEVELS, "confidence"),
            sensitivity=_require(self.sensitivity, MEMORY_SENSITIVITIES, "sensitivity"),
            intent=_require(self.intent, MEMORY_INTENTS, "intent"),
            visibility=_require(self.visibility, MEMORY_VISIBILITIES, "visibility"),
        )


@dataclass(frozen=True, slots=True)
class ReviewedMemoryCandidate:
    memory: MemoryCandidate
    source_entry_indexes: tuple[int, ...]

    def validated(self) -> "ReviewedMemoryCandidate":
        memory = self.memory.validated()
        indexes = tuple(dict.fromkeys(int(value) for value in self.source_entry_indexes))
        if not indexes or any(value < 0 for value in indexes):
            raise MemoryContractError("contract v2 memory requires transcript citations")
        return ReviewedMemoryCandidate(memory=memory, source_entry_indexes=indexes)


@dataclass(frozen=True, slots=True)
class MemoryReview:
    summary: str
    memories: tuple[ReviewedMemoryCandidate, ...]
    model: str
    contract_version: int = REVIEWER_CONTRACT_VERSION

    def validated(self) -> "MemoryReview":
        if self.contract_version != REVIEWER_CONTRACT_VERSION:
            raise MemoryContractError("unsupported memory reviewer contract version")
        summary = self.summary.strip()
        if not summary:
            raise MemoryContractError("memory review summary is required")
        return MemoryReview(
            summary=summary,
            memories=tuple(item.validated() for item in self.memories),
            model=self.model.strip(),
            contract_version=self.contract_version,
        )
