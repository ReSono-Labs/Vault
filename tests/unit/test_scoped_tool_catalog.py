from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult


def test_scoped_dynamic_tool_is_not_visible_or_invokable_across_scope() -> None:
    catalog = ToolCatalog(authorizer=lambda _definition, _context: True)
    catalog.replace_capability_source("scope", (ToolDefinition(
        tool_id="scoped", name="scoped", description="Scoped",
        input_schema={"type": "object", "additionalProperties": False},
        handler=lambda _context, _arguments: ToolInvocationResult("ok"),
        audiences=frozenset({AgentKind.VOICE}), scope_user_id="user-a", scope_workspace_id="ws-a",
    ),))
    assert [item.name for item in catalog.definitions_for(AgentKind.VOICE, user_id="user-a", workspace_id="ws-a")] == ["scoped"]
    assert catalog.definitions_for(AgentKind.VOICE, user_id="user-b", workspace_id="ws-a") == ()
    denied = catalog.invoke("scoped", {}, context=ToolInvocationContext(
        agent=AgentKind.VOICE, user_id="user-b", workspace_id="ws-a",
        tool_call_id="call", local_session_id="session",
    ))
    assert denied.is_error and denied.text == "Tool is not granted."
