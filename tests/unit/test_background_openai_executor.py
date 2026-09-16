from __future__ import annotations

from types import SimpleNamespace
import json

from app.vault_runtime.background_agent.contracts import BackgroundRunRequest, RunLimits
from app.vault_runtime.background_agent.openai_executor import OpenAIBackgroundExecutor
from app.vault_runtime.background_agent.sdk_runner import AgentTurnObservation
from app.vault_runtime.background_agent.tool_supply import BackgroundToolGrant, BackgroundToolSupply
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolInvocationContext
from app.vault_runtime.background_agent.contracts import AutonomyProfile


class _Credentials:
    def background_access(self, *, user_id: str, workspace_id: str):
        assert (user_id, workspace_id) == ("user-1", "workspace-1")
        return SimpleNamespace(value="secret-not-logged"), "gpt-5.6-sol"


class _Progress:
    def __init__(self) -> None:
        self.turns = 0
        self.memory_references = ()

    def model_turn(self, count: int = 1) -> None:
        self.turns += count

    def context_frozen(self, memory_references: tuple[str, ...]) -> None:
        self.memory_references = memory_references

    def reasoning(self, summaries: tuple[str, ...]) -> None:
        self.summaries = summaries


class _Memories:
    def search(self, *, user_id: str, workspace_id: str, query: str, limit: int):
        assert (user_id, workspace_id, limit) == ("user-1", "workspace-1", 8)
        assert "bounded result" in query.lower()
        return (SimpleNamespace(memory=SimpleNamespace(
            memory_id="memory-1", domain="project", memory_type="constraint",
            memory_key="vault.clean", content_text="Keep Vault clean",
            confidence="high", sensitivity="normal", visibility="private",
        )),)


def test_production_background_executor_uses_local_credential_and_validated_json() -> None:
    observed = {}

    async def runner(**kwargs):
        observed.update(kwargs)
        kwargs["observation_sink"](AgentTurnObservation(1, ()))
        return {
            "status": "complete", "summary": "Done", "artifact_references": [],
            "requirement_outcomes": [{"requirement": "Result is valid", "status": "completed", "evidence": "Checked"}],
            "unresolved_issues": [], "verification_summary": "Validated",
            "phase_evidence": [{"phase": "execution", "summary": "Completed bounded work"}],
        }

    catalog = ToolCatalog(authorizer=lambda _definition, _context: True)
    supply = BackgroundToolSupply(
        catalog=catalog,
        grant=BackgroundToolGrant(autonomy=AutonomyProfile.LIMITED, explicit_names=frozenset(), max_calls=1),
        user_id="user-1", workspace_id="workspace-1",
    )
    request = BackgroundRunRequest(
        run_id="run-1", objective="Return a bounded result", instruction_profile="strict",
        success_criteria=("Result is valid",), result_schema={
            "type": "object", "properties": {"done": {"type": "boolean"}},
            "required": ["done"], "additionalProperties": False,
        }, limits=RunLimits(max_seconds=30, max_model_turns=3, max_tool_calls=1),
        original_request="Do the bounded work", verification_method="Validate JSON",
        completion_conditions=("done is true",),
    )
    progress = _Progress()
    result = OpenAIBackgroundExecutor(
        credentials=_Credentials(), memories=_Memories(), runner=runner,
    ).execute(  # type: ignore[arg-type]
        request, tools=supply,
        context=ToolInvocationContext(
            agent=AgentKind.BACKGROUND, user_id="user-1", workspace_id="workspace-1",
            tool_call_id="executor", local_session_id="session-1", execution_id="run-1",
        ),
        progress=progress,  # type: ignore[arg-type]
    )
    assert result["status"] == "complete"
    assert observed["api_key"] == "secret-not-logged"
    assert observed["model"] == "gpt-5.6-sol"
    assert observed["reasoning_effort"] == "medium"
    assert observed["agent_name"] == "ReSono Background Agent"
    assert observed["function_tools"] == []
    assert observed["output_type"].__name__ == "BackgroundAgentOutput"
    assert progress.memory_references == ("memory-1",)
    supplied = json.loads(observed["input_text"])["authorizedMemory"]
    assert supplied == [{
        "confidence": "high", "content": "Keep Vault clean", "domain": "project",
        "memoryId": "memory-1", "memoryKey": "vault.clean",
        "memoryType": "constraint", "sensitivity": "normal", "visibility": "private",
    }]
    assert progress.turns == 1
