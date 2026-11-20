"""Sequential independent review calls; durable scheduling belongs to the caller."""
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")
U = TypeVar("U")


@dataclass(frozen=True, slots=True)
class ReviewOutcome(Generic[T]):
    state: str
    result: T | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class SessionReviewResult(Generic[T, U]):
    memory: ReviewOutcome[T]
    decisions: ReviewOutcome[U]


def _attempt(callback: Callable[[], T]) -> ReviewOutcome[T]:
    try:
        return ReviewOutcome("completed", callback())
    except Exception:
        # Never expose provider exception strings or credentials as review status.
        return ReviewOutcome("failed", error_code="review_failed")


def review_session(*, memory_review: Callable[[], T],
                  decision_review: Callable[[], U] | None) -> SessionReviewResult[T, U]:
    memory = _attempt(memory_review)
    decisions = (_attempt(decision_review) if decision_review is not None
                 else ReviewOutcome("disabled"))
    return SessionReviewResult(memory, decisions)
