from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult


def _context(agent: AgentKind = AgentKind.VOICE) -> ToolInvocationContext:
    return ToolInvocationContext(
        agent=agent, user_id="user", workspace_id="workspace", tool_call_id="call",
        local_session_id="session", voice_session_id="voice-session",
    )


def _definition(*, audiences=frozenset({AgentKind.VOICE})) -> ToolDefinition:
    return ToolDefinition(
        tool_id="builtin.echo.v1", name="echo", description="Echo bounded text.",
        input_schema={
            "type": "object", "properties": {"text": {"type": "string", "maxLength": 20}},
            "required": ["text"], "additionalProperties": False,
        },
        handler=lambda _context, arguments: ToolInvocationResult(str(arguments["text"])),
        audiences=audiences,
    )


def test_catalog_enforces_audience_authorizer_and_schema() -> None:
    catalog = ToolCatalog(authorizer=lambda _definition, context: context.workspace_id == "workspace")
    catalog.register(_definition())
    assert catalog.invoke("echo", {"text": "hello"}, context=_context()).text == "hello"
    assert catalog.invoke("echo", {"text": "x" * 21}, context=_context()).is_error
    assert catalog.invoke("echo", {"text": "hello"}, context=_context(AgentKind.BACKGROUND)).is_error


def test_capability_source_cannot_collide_and_does_not_change_agents() -> None:
    catalog = ToolCatalog(authorizer=lambda _definition, _context: True)
    catalog.replace_capability_source("plugin:test", (_definition(audiences=frozenset({AgentKind.BACKGROUND})),))
    assert len(catalog.definitions_for(AgentKind.BACKGROUND)) == 1
    try:
        catalog.register(_definition())
    except ValueError:
        pass
    else:
        raise AssertionError("tool collision accepted")
