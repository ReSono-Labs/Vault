"""Scoped data contracts below the two fixed public system-agent identities."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
import json

from .contracts import BackgroundRunRequest, RunLimits


def _text(value: str, maximum: int = 128) -> None:
    if not isinstance(value, str) or not value or value.strip() != value or len(value) > maximum:
        raise ValueError("Identifier/text must be nonempty, trimmed and bounded")


def _object(value: dict[str, object]) -> None:
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    json.dumps(value, allow_nan=False)


class WorkState(StrEnum):
    PROPOSED = "proposed"
    READY = "ready"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_INPUT = "waiting_input"
    WAITING_EVENT = "waiting_event"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


WORK_TRANSITIONS = {
    WorkState.PROPOSED: frozenset({WorkState.READY, WorkState.WAITING_APPROVAL, WorkState.CANCELLED}),
    WorkState.READY: frozenset({WorkState.QUEUED, WorkState.CANCELLED}),
    WorkState.QUEUED: frozenset({WorkState.RUNNING, WorkState.WAITING_APPROVAL, WorkState.FAILED, WorkState.CANCELLED}),
    WorkState.RUNNING: frozenset({WorkState.WAITING_APPROVAL, WorkState.WAITING_INPUT, WorkState.WAITING_EVENT,
                                WorkState.COMPLETED, WorkState.FAILED, WorkState.CANCELLED, WorkState.UNKNOWN}),
    WorkState.WAITING_APPROVAL: frozenset({WorkState.READY, WorkState.WAITING_INPUT, WorkState.FAILED, WorkState.CANCELLED}),
    WorkState.WAITING_INPUT: frozenset({WorkState.READY, WorkState.FAILED, WorkState.CANCELLED}),
    WorkState.WAITING_EVENT: frozenset({WorkState.READY, WorkState.FAILED, WorkState.CANCELLED}),
    WorkState.UNKNOWN: frozenset({WorkState.WAITING_INPUT, WorkState.CANCELLED}),
    WorkState.COMPLETED: frozenset(), WorkState.FAILED: frozenset(), WorkState.CANCELLED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class OwnerScope:
    user_id: str
    workspace_id: str

    def __post_init__(self) -> None:
        _text(self.user_id)
        _text(self.workspace_id)


@dataclass(frozen=True, slots=True)
class WorkScope(OwnerScope):
    work_id: str
    intent_version: int
    worker_id: str | None
    worker_generation: int | None
    grant_id: str | None

    def __post_init__(self) -> None:
        OwnerScope.__post_init__(self)
        _text(self.work_id)
        if type(self.intent_version) is not int or self.intent_version < 1:
            raise ValueError("Invalid work intent version")
        if (self.worker_id is None) != (self.worker_generation is None):
            raise ValueError("Worker identity requires its generation")
        if self.worker_id is not None:
            _text(self.worker_id)
            if type(self.worker_generation) is not int or self.worker_generation < 1:
                raise ValueError("Invalid worker generation")
        if self.grant_id is not None:
            _text(self.grant_id)


@dataclass(frozen=True, slots=True)
class WorkRequest:
    request: BackgroundRunRequest
    grant_id: str | None
    local_session_id: str | None
    destination: dict[str, object]

    def __post_init__(self) -> None:
        if (self.grant_id is None) == (self.local_session_id is None):
            raise ValueError("Work requires exactly one authority path")
        for value in (self.grant_id, self.local_session_id):
            if value is not None:
                _text(value)
        if not isinstance(self.request, BackgroundRunRequest):
            raise ValueError("Work requires a validated background request")
        _object(self.destination)

    def payload(self) -> dict[str, object]:
        return {"request": self.request.payload(), "grant_id": self.grant_id,
                "local_session_id": self.local_session_id, "destination": self.destination}


@dataclass(frozen=True, slots=True)
class WorkerSpec:
    role_key: str
    purpose: str
    instructions: str
    tool_names: tuple[str, ...]
    resource_policy: dict[str, object]
    limits: RunLimits = field(default_factory=RunLimits)

    def __post_init__(self) -> None:
        _text(self.role_key, 64)
        _text(self.purpose, 4096)
        _text(self.instructions, 16384)
        if not isinstance(self.tool_names, tuple) or len(self.tool_names) > 50 or len(set(self.tool_names)) != len(self.tool_names):
            raise ValueError("Worker tools must be unique and bounded")
        for name in self.tool_names:
            _text(name, 255)
        _object(self.resource_policy)
        if not isinstance(self.limits, RunLimits):
            raise ValueError("Worker limits require RunLimits")


@dataclass(frozen=True, slots=True)
class PreparedAction:
    action_id: str
    action_hash: str
    work_id: str | None
    kind: str
    title: str
    detail: str
    expires_at: datetime

    def __post_init__(self) -> None:
        for value in (self.action_id, self.kind, self.title):
            _text(value, 255)
        if len(self.action_hash) != 64 or any(c not in "0123456789abcdef" for c in self.action_hash):
            raise ValueError("Invalid action fingerprint")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ValueError("Action expiry must be timezone aware")
        # owner_approval: asked during an interactive Chat turn or Voice call (owner_approvals.py).
        if self.work_id is None and self.kind not in {"worker_create", "execution_grant", "routine_create", "owner_approval"}:
            raise ValueError("Tool actions require work scope")


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    action_id: str
    action_hash: str
    choice: str
    actor_user_id: str
    workspace_id: str
    channel: str
    channel_generation: str
    decision_id: str

    def __post_init__(self) -> None:
        for value in (self.action_id, self.actor_user_id, self.workspace_id, self.channel, self.channel_generation, self.decision_id):
            _text(value)
        if self.choice not in {"allow_once", "deny"} or len(self.action_hash) != 64:
            raise ValueError("Invalid approval decision")


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    state: WorkState
    checkpoint: dict[str, object] | None = None
    output: dict[str, object] | None = None
    pending_action_id: str | None = None
    failure_code: str | None = None
    # The run's failure message (vault_background_runs.failure_message), as the old engine wrote it.
    failure_message: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", WorkState(self.state))
        if self.state is WorkState.WAITING_APPROVAL and not self.pending_action_id:
            raise ValueError("Waiting for approval requires an action")
        for value in (self.checkpoint, self.output):
            if value is not None:
                _object(value)
