import pytest

from app.vault_runtime.background_agent.contracts import AutonomyProfile
from app.vault_runtime.background_agent.tool_supply import (
    BackgroundToolGrant,
    BackgroundToolSupply,
    ToolBudgetExceeded,
)
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult


def _context():
    return ToolInvocationContext(
        agent=AgentKind.BACKGROUND, user_id="user", workspace_id="workspace",
        tool_call_id="call", local_session_id="session", execution_id="run",
    )


def test_background_supply_intersects_names_effect_and_budget() -> None:
    catalog = ToolCatalog(authorizer=lambda _definition, _context: True)
    for name, effect in (("read_memory", "read"), ("write_memory", "write")):
        catalog.register(ToolDefinition(
            tool_id=f"builtin.{name}.v1", name=name, description=name,
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=lambda _context, _arguments: ToolInvocationResult("ok"),
            effect_class=effect, audiences=frozenset({AgentKind.BACKGROUND}),
        ))
    supply = BackgroundToolSupply(
        catalog=catalog,
        grant=BackgroundToolGrant(
            autonomy=AutonomyProfile.LIMITED,
            explicit_names=frozenset({"read_memory", "write_memory"}), max_calls=1,
        ),
    )
    assert [item["name"] for item in supply.definitions()] == ["read_memory"]
    empty = BackgroundToolSupply(
        catalog=catalog,
        grant=BackgroundToolGrant(autonomy=AutonomyProfile.LIMITED, explicit_names=frozenset(), max_calls=2),
    )
    assert [item["name"] for item in empty.definitions()] == ["read_memory"]
    assert supply.invoke("write_memory", {}, context=_context()).is_error
    assert supply.invoke("read_memory", {}, context=_context()).text == "ok"
    with pytest.raises(ToolBudgetExceeded):
        supply.invoke("read_memory", {}, context=_context())
