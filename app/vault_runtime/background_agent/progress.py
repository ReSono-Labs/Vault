"""Safe, recipe-aware progress projection for delegated work (R1 donor)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from app.vault_runtime.background_agent.contracts import BackgroundRunState, ExecutionRecipe


@dataclass(frozen=True, slots=True)
class RunProgress:
    phase: str
    label: str
    fraction: float
    active: bool
    tone: str
    activity: str
    model_turns: int
    tool_calls: int
    timeline: tuple[dict[str, object], ...]


def project_progress(
    state: BackgroundRunState, recipe: ExecutionRecipe, events: Iterable[Any] = (),
) -> RunProgress:
    items = tuple(events)
    model_turns = sum(
        int(item.detail.get("count", 0)) for item in items if item.event_type == "model_turns"
    )
    tool_calls = max(
        (int(item.detail.get("call", 0)) for item in items if item.event_type.startswith("tool_")),
        default=0,
    )
    timeline = tuple(_timeline(item) for item in items if _visible(item.event_type))[-8:]
    latest = timeline[-1]["label"] if timeline else "Run accepted"

    def value(phase: str, label: str, fraction: float, active: bool, tone: str) -> RunProgress:
        return RunProgress(phase, label, fraction, active, tone, str(latest), model_turns, tool_calls, timeline)

    if state is BackgroundRunState.ACCEPTED:
        return value("preparing", "Preparing goal context", 0.12, True, "active")
    if state is BackgroundRunState.QUEUED:
        return value("queued", "Waiting for the Background Agent", 0.24, True, "active")
    if state is BackgroundRunState.RUNNING:
        label = "Working and checking the result" if recipe is ExecutionRecipe.SELF_REVIEW else "Background Agent is working"
        return value("working", label, 0.52, True, "active")
    if state is BackgroundRunState.REVIEWING:
        return value("reviewing", "Independent reviewer is checking the result", 0.72, True, "active")
    if state is BackgroundRunState.REPAIRING:
        return value("repairing", "Applying reviewer feedback", 0.84, True, "active")
    if state is BackgroundRunState.COMPLETED:
        return value("completed", "Completed", 1.0, False, "complete")
    if state is BackgroundRunState.CANCELLED:
        return value("cancelled", "Cancelled", 1.0, False, "stopped")
    return value("failed", "Stopped before completion", 1.0, False, "failed")


def explain_failure(run: Any) -> str | None:
    if not run.failure_code:
        return None
    labels = {
        "max_model_turns_exceeded": "The Agents SDK reached the configured model-turn limit before returning a result.",
        "max_turns_exceeded": "The Agents SDK reached the configured model-turn limit before returning a result.",
        "run_timeout": "The run reached its configured time limit before returning a result.",
        "agent_incomplete": "The agent returned a typed result but reported that work was blocked or still needed attention.",
        "execution_failed": "The Agents SDK execution stopped before it could return a typed result.",
    }
    return labels.get(run.failure_code, str(run.failure_message or run.failure_code))


def _visible(event_type: str) -> bool:
    return event_type in {
        "accepted", "context_frozen", "queued", "sdk_agent_started",
        "model_request_started", "model_request_completed", "model_request_failed",
        "model_turns", "tool_started", "tool_completed", "tool_failed",
        "agent_evidence", "completed", "agent_incomplete", "execution_failed",
        "max_turns_exceeded", "max_model_turns_exceeded", "run_timeout", "cancelled",
        "started", "reasoning_summary",
    }


def _timeline(item: Any) -> dict[str, object]:
    event_type = item.event_type
    detail = item.detail
    tool = _tool_label(str(detail.get("name", "tool")))
    created = item.created_at
    created_at = created.isoformat() if isinstance(created, datetime) else str(created)
    labels = {
        "accepted": "Goal accepted",
        "context_frozen": "Goal context prepared",
        "queued": "Queued for the Background Agent",
        "started": "Background Agent started",
        "sdk_agent_started": "Agents SDK run started",
        "model_request_started": "Agent is reasoning and selecting tools",
        "model_request_completed": "Agent returned a typed result",
        "model_request_failed": "Model request failed",
        "model_turns": f"Completed {detail.get('count', 0)} model turns",
        "tool_started": f"{tool} started",
        "tool_completed": f"{tool} completed",
        "tool_failed": f"{tool} failed",
        "reasoning_summary": str(detail.get("summary", "Reasoning summary")),
        "agent_evidence": str(detail.get("summary", "Agent evidence recorded")),
        "completed": "Result committed",
        "agent_incomplete": "Agent reported unresolved work",
        "execution_failed": "SDK execution failed",
        "max_turns_exceeded": "Maximum model turns reached",
        "max_model_turns_exceeded": "Maximum model turns reached",
        "run_timeout": "Maximum run time reached",
        "cancelled": "Run cancelled",
    }
    return {"type": event_type, "label": labels.get(event_type, event_type.replace("_", " ")),
            "createdAt": created_at}


def _tool_label(name: str) -> str:
    return name.replace("_", " ").strip().capitalize()
