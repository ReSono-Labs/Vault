"""Shared test helpers moved out of test modules (TST-01)."""

from __future__ import annotations

from app.vault_runtime.background_agent.contracts import BackgroundRunRequest
from app.vault_runtime.background_agent.coordination_contracts import ExecutionOutcome, WorkScope, WorkState


class _RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def execute(self, scope: WorkScope, request: BackgroundRunRequest, checkpoint, tools, cancel_requested):
        self.calls.append(
            {
                "scope": scope,
                "request": request,
                "checkpoint": checkpoint,
                "tool_names": tuple(defn["name"] for defn in tools.definitions()),
                "tools": tools,
            }
        )
        return ExecutionOutcome(
            state=WorkState.COMPLETED,
            output={
                "status": "complete",
                "summary": f"Completed {request.objective}",
                "artifact_references": [f"artifact://{scope.work_id}"],
                "requirement_outcomes": [
                    {
                        "requirement": "Status compiled accurately",
                        "status": "completed",
                        "evidence": f"Handled by {scope.worker_id or 'direct'}",
                    }
                ],
                "unresolved_issues": [],
                "verification_summary": "Verified",
                "phase_evidence": [{"phase": "act", "summary": request.objective}],
            },
        )
