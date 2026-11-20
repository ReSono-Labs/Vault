from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class TurnStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True)
class PeerEndpoint:
    name: str
    url: str
    token: str


@dataclass
class TurnRecord:
    turn_id: str
    peer: str
    context_id: str | None
    task_id: str | None
    status: TurnStatus
    request_text: str
    response_text: str | None
    error: str | None
    created_at: float
    updated_at: float
    raw_task: dict[str, Any] | None = None
