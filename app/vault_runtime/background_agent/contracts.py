from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum


class AutonomyProfile(StrEnum):
    LIMITED = "limited"
    EXPANDED = "expanded"
    CUSTOM = "custom"


class ExecutionRecipe(StrEnum):
    DIRECT = "direct_v1"
    SELF_REVIEW = "self_review_v1"
    INDEPENDENT_REVIEW = "independent_review_v1"


class BackgroundRunState(StrEnum):
    ACCEPTED = "accepted"
    QUEUED = "queued"
    RUNNING = "running"
    REVIEWING = "reviewing"
    REPAIRING = "repairing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class RunLimits:
    max_seconds: int = 300
    max_model_turns: int = 24
    max_tool_calls: int = 40
    max_review_rounds: int = 2
    max_workspace_bytes: int = 8 * 1024 * 1024

    def __post_init__(self) -> None:
        values = (
            self.max_seconds, self.max_model_turns, self.max_tool_calls,
            self.max_review_rounds, self.max_workspace_bytes,
        )
        if any(value <= 0 for value in values):
            raise ValueError("run limits must be positive")
        if self.max_seconds > 3600 or self.max_model_turns > 100 or self.max_tool_calls > 500:
            raise ValueError("run limits exceed the supported maximum")
        if self.max_review_rounds > 10 or self.max_workspace_bytes > 256 * 1024 * 1024:
            raise ValueError("run limits exceed the supported maximum")


@dataclass(frozen=True, slots=True)
class BackgroundRunRequest:
    run_id: str
    objective: str
    instruction_profile: str
    success_criteria: tuple[str, ...]
    result_schema: dict[str, object]
    recipe: ExecutionRecipe = ExecutionRecipe.SELF_REVIEW
    autonomy: AutonomyProfile = AutonomyProfile.LIMITED
    limits: RunLimits = RunLimits()
    goal_type: str = "general"
    context_summary: str = ""
    expected_result: str = ""
    scope: str = ""
    exclusions: tuple[str, ...] = ()
    source_requirements: str = ""
    workspace_destination: str | None = None
    original_request: str = ""
    verification_method: str = ""
    completion_conditions: tuple[str, ...] = ()
    stop_conditions: tuple[str, ...] = ()
    requested_tool_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name, value in (
            ("run_id", self.run_id), ("objective", self.objective),
            ("instruction_profile", self.instruction_profile),
            ("original_request", self.original_request),
            ("verification_method", self.verification_method),
        ):
            if not value or value.strip() != value:
                raise ValueError(f"{name} must be a non-empty trimmed string")
        for name, values in (
            ("success_criteria", self.success_criteria),
            ("completion_conditions", self.completion_conditions),
        ):
            if not values or len(values) > 20 or len(values) != len(set(values)):
                raise ValueError(f"{name} must contain 1-20 unique values")
            if any(not item or item.strip() != item or len(item) > 2048 for item in values):
                raise ValueError(f"{name} contains an invalid value")
        for values in (self.exclusions, self.stop_conditions, self.requested_tool_names):
            if len(values) > 50 or len(values) != len(set(values)):
                raise ValueError("run tuple values must be unique and bounded")
            if any(not item or item.strip() != item or len(item) > 2048 for item in values):
                raise ValueError("run tuple contains an invalid value")
        if not isinstance(self.result_schema, dict) or not self.result_schema:
            raise ValueError("result_schema must be a non-empty object")
        if len(self.objective) > 16384 or len(self.original_request) > 16384:
            raise ValueError("run request text is too long")

    def payload(self) -> dict[str, object]:
        result = asdict(self)
        result["recipe"] = self.recipe.value
        result["autonomy"] = self.autonomy.value
        return result


TERMINAL_RUN_STATES = frozenset(
    {BackgroundRunState.COMPLETED, BackgroundRunState.FAILED, BackgroundRunState.CANCELLED}
)

LEGAL_TRANSITIONS = {
    BackgroundRunState.ACCEPTED: frozenset({BackgroundRunState.QUEUED, BackgroundRunState.CANCELLED}),
    BackgroundRunState.QUEUED: frozenset(
        {BackgroundRunState.RUNNING, BackgroundRunState.CANCELLED, BackgroundRunState.FAILED}
    ),
    BackgroundRunState.RUNNING: frozenset(
        {
            BackgroundRunState.REVIEWING, BackgroundRunState.COMPLETED,
            BackgroundRunState.CANCELLED, BackgroundRunState.FAILED,
        }
    ),
    BackgroundRunState.REVIEWING: frozenset(
        {
            BackgroundRunState.REPAIRING, BackgroundRunState.COMPLETED,
            BackgroundRunState.CANCELLED, BackgroundRunState.FAILED,
        }
    ),
    BackgroundRunState.REPAIRING: frozenset(
        {BackgroundRunState.REVIEWING, BackgroundRunState.CANCELLED, BackgroundRunState.FAILED}
    ),
}
