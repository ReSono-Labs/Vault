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


def test_delegated_supply_omits_write_tools_the_action_bridge_cannot_route() -> None:
    """HANDOFF item 10: unsupported Mail writes are not offered to delegated work at all; the
    legacy explicit-submission path keeps its current tools."""
    from app.vault_runtime.background_agent.coordination_contracts import WorkScope
    catalog = ToolCatalog(authorizer=lambda _definition, _context: True,
                          background_authorizer=lambda *_args: True)
    names = ("email_check", "email_compose", "email_send_pending", "email_mark_read", "email_move_message",
             "agent_mail_compose", "agent_mail_archive", "tasks_add", "workspace_write_file")
    for name in names:
        catalog.register(ToolDefinition(
            tool_id=f"builtin.{name}.v1", name=name, description=name,
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            handler=lambda _context, _arguments: ToolInvocationResult("ok"),
            effect_class="read" if name == "email_check" else "write", audiences=frozenset({AgentKind.BACKGROUND}),
        ))
    grant = BackgroundToolGrant(autonomy=AutonomyProfile.EXPANDED, explicit_names=frozenset(), max_calls=5)

    class Authority:
        def allowed_tool_names(self, _scope):
            return None

    scope = WorkScope("user", "workspace", "work", 1, None, None, "grant")
    delegated = {item["name"] for item in BackgroundToolSupply(catalog=catalog, grant=grant,
                                                               background_scope=scope, authority=Authority()).definitions()}
    assert delegated == {"email_check", "email_compose", "email_send_pending", "agent_mail_compose", "tasks_add",
                         "workspace_write_file"}
    legacy = {item["name"] for item in BackgroundToolSupply(catalog=catalog, grant=grant).definitions()}
    assert legacy == set(names)
