"""Shared test helpers moved out of test modules (TST-01)."""

from __future__ import annotations

import json

from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText


TASK_TOOLS = ["tasks_list", "tasks_read", "tasks_add", "tasks_edit", "tasks_mark_completed", "tasks_remove", "tasks_confirm_action"]


def _output_json(summary: str, status: str = "complete") -> str:
    return json.dumps({
        "status": status,
        "summary": summary,
        "artifact_references": [],
        "requirement_outcomes": [{
            "requirement": "Task change",
            "status": "completed" if status == "complete" else "unresolved",
            "evidence": summary,
        }],
        "unresolved_issues": [] if status == "complete" else [summary],
        "verification_summary": "Checked Tasks repository",
        "phase_evidence": [{"phase": "act", "summary": summary}],
    })


class OfflineTaskModel(Model):
    def __init__(self, task_text: str = "Ship Phase B", *, force_complete_on_deny: bool = False) -> None:
        self.task_text = task_text
        self.force_complete_on_deny = force_complete_on_deny

    async def get_response(self, system_instructions, input, *args, **kwargs):
        if isinstance(input, list) and any(
            isinstance(item, dict) and item.get("type") == "function_call_output" for item in input
        ):
            outputs = [str(item.get("output", "")) for item in input if isinstance(item, dict) and item.get("type") == "function_call_output"]
            denied = any("not approved" in out.lower() or "denied" in out.lower() or "expired" in out.lower() for out in outputs)
            status = "complete" if (not denied or self.force_complete_on_deny) else "blocked"
            output = [ResponseOutputMessage(
                id="msg-task-done", role="assistant", status="completed", type="message",
                content=[ResponseOutputText(type="output_text", text=_output_json(f"Task {self.task_text}", status=status), annotations=[])],
            )]
        else:
            output = [ResponseFunctionToolCall(
                id="call-task-add", call_id="call-task-add", name="tasks_add", type="function_call",
                arguments=json.dumps({"text": self.task_text}),
            )]
        return ModelResponse(output=output, usage=Usage(requests=1), response_id="resp-task")

    async def stream_response(self, *args, **kwargs):
        raise AssertionError("OfflineTaskModel does not stream")
        yield
