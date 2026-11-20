"""Background: health, earlier runs (read-only), the deprecated POST /background/runs, and the coordination API."""
from __future__ import annotations

import logging
from typing import Any, Mapping
from uuid import uuid4

from app.vault_runtime.background_agent.contracts import (
    AutonomyProfile,
    BackgroundRunRequest,
    ExecutionRecipe,
    RunLimits,
)
from .common import API_LOGGER, LocalApiResponse, _optional_text, _required_text, _text_tuple


class BackgroundRoutes:
    """VaultLocalApiApp routes: background: health, earlier runs (read-only), the deprecated post /background/runs, and the coordination api."""

    def _handle_background(
        self, principal, *, method: str, path: str, payload: dict[str, Any],
    ) -> LocalApiResponse | None:
        """Background routes of the runtime handler: signed in, CSRF already checked for POST and DELETE."""
        if method == "GET" and path == "/background/health":
            jobs = self._background_jobs()
            return LocalApiResponse(200, {"durable": jobs.health() if jobs is not None else {"state": "disabled"}})
        if method == "GET" and path == "/background/runs":
            # "Earlier runs": the old engine's rows (work_id IS NULL), read-only.
            if self._background_runs is None:
                raise RuntimeError("Background Agent runs are unavailable.")
            items = self._background_runs.list_in_workspace(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                local_session_id=principal.session_id,
            )
            return LocalApiResponse(200, {"items": [
                _background_run_payload(
                    item,
                    events=self._background_runs.list_events(
                        user_id=principal.user_id, workspace_id=principal.workspace_id,
                        local_session_id=principal.session_id, run_id=item.request.run_id,
                        authorize=False,
                    ),
                )
                for item in items
            ]})
        if method == "POST" and path == "/background/runs":
            # Deprecated (owner decision 5-A): kept for one release for an unknown client. The run
            # is a direct one-shot on the durable engine; the response keeps its old shape.
            if self._direct_runs is None or self._background_runs is None:
                raise RuntimeError("Background Agent is unavailable.")
            request = _background_request(payload)
            logging.getLogger(API_LOGGER).warning("background_runs_post_deprecated")
            self._direct_runs.submit(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                local_session_id=principal.session_id, request=request,
            )
            run = self._background_runs.get_in_workspace(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                local_session_id=principal.session_id, run_id=request.run_id,
            )
            return LocalApiResponse(202, _background_run_payload(run))
        if path.startswith("/background/runs/"):
            if self._background_runs is None:
                raise RuntimeError("Background Agent runs are unavailable.")
            suffix = path.removeprefix("/background/runs/")
            cancel = suffix.endswith("/cancel")
            run_id = suffix.removesuffix("/cancel").strip("/")
            if method == "GET" and not cancel:
                run = self._background_runs.get_in_workspace(
                    user_id=principal.user_id, workspace_id=principal.workspace_id,
                    local_session_id=principal.session_id, run_id=run_id,
                )
                events = self._background_runs.list_events(
                    user_id=principal.user_id, workspace_id=principal.workspace_id,
                    local_session_id=principal.session_id, run_id=run_id, authorize=False,
                )
                return LocalApiResponse(200, _background_run_payload(run, events=events))
            # One cancel path (owner decision 5-C): POST /background/work/{id}/cancel. The old
            # POST /background/runs/{id}/cancel is gone and answers 404.
            if method == "DELETE" and not cancel:
                from app.vault_runtime.background_agent.errors import BackgroundRunConflictError
                try:
                    self._background_runs.delete_in_workspace(
                        user_id=principal.user_id, workspace_id=principal.workspace_id,
                        local_session_id=principal.session_id, run_id=run_id,
                    )
                except BackgroundRunConflictError as exc:
                    return LocalApiResponse(409, {"error": {"code": "run_not_terminal", "message": str(exc)}})
                return LocalApiResponse(200, {"runId": run_id, "deleted": True})
        if path.startswith("/background/"):
            from app.vault_runtime.local_api.background import handle_background_coordination_api
            coord_res = handle_background_coordination_api(
                self,
                principal,
                method=method,
                path=path,
                payload=payload,
                respond=lambda status, value: LocalApiResponse(status, value, (("Cache-Control", "no-store"),)),
            )
            if coord_res is not None:
                return coord_res
        return None


def _background_request(payload: Mapping[str, Any]) -> BackgroundRunRequest:
    result_schema = payload.get("resultSchema")
    if not isinstance(result_schema, dict):
        raise ValueError("resultSchema is required.")
    limits_raw = payload.get("limits")
    limits = RunLimits(**limits_raw) if isinstance(limits_raw, dict) else RunLimits()
    return BackgroundRunRequest(
        run_id=str(uuid4()), objective=_required_text(payload, "objective"),
        instruction_profile=_required_text(payload, "instructionProfile"),
        success_criteria=_text_tuple(payload, "successCriteria", required=True),
        result_schema=result_schema,
        recipe=ExecutionRecipe(str(payload.get("recipe", ExecutionRecipe.SELF_REVIEW.value))),
        autonomy=AutonomyProfile(str(payload.get("autonomy", AutonomyProfile.LIMITED.value))),
        limits=limits, goal_type=str(payload.get("goalType", "general")),
        context_summary=str(payload.get("contextSummary", "")),
        expected_result=str(payload.get("expectedResult", "")),
        scope=str(payload.get("scope", "")), exclusions=_text_tuple(payload, "exclusions"),
        source_requirements=str(payload.get("sourceRequirements", "")),
        workspace_destination=_optional_text(payload, "workspaceDestination"),
        original_request=_required_text(payload, "originalRequest"),
        verification_method=_required_text(payload, "verificationMethod"),
        completion_conditions=_text_tuple(payload, "completionConditions", required=True),
        stop_conditions=_text_tuple(payload, "stopConditions"),
        requested_tool_names=_text_tuple(payload, "requestedToolNames"),
    )


def _background_run_payload(run, events=()) -> dict[str, Any]:
    from app.vault_runtime.background_agent.progress import explain_failure, project_progress
    progress = project_progress(run.state, run.request.recipe, events)
    reasoning_entries = [
        {
            "type": item.event_type,
            "createdAt": item.created_at.isoformat(),
            "detail": item.detail,
        }
        for item in events
        if item.event_type in {"reasoning_summary", "agent_evidence"}
    ]
    invocation = "voice_goal" if run.request.instruction_profile == "voice-goal" else run.request.instruction_profile
    return {
        "runId": run.request.run_id, "agentKind": "background",
        "invocationType": invocation,
        "originId": run.local_session_id,
        "objective": run.request.objective,
        "recipe": run.request.recipe.value,
        "state": run.state.value, "cancellationRequested": run.cancellation_requested,
        "output": run.output,
        "failure": ({"code": run.failure_code, "message": run.failure_message}
                    if run.failure_code else None),
        "failureCode": run.failure_code,
        "failureMessage": run.failure_message,
        "failureExplanation": explain_failure(run),
        "modelTurns": run.model_turns,
        "toolCalls": run.tool_calls, "createdAt": run.created_at.isoformat(),
        "updatedAt": run.updated_at.isoformat(),
        "completedAt": run.completed_at.isoformat() if run.completed_at else None,
        "reasoningEntries": reasoning_entries,
        "progress": {
            "label": progress.label,
            "fraction": progress.fraction,
            "active": progress.active,
            "tone": progress.tone,
            "activity": progress.activity,
            "modelTurns": progress.model_turns or run.model_turns,
            "toolCalls": progress.tool_calls or run.tool_calls,
            "timeline": list(progress.timeline),
        },
    }
