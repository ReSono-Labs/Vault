from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.argument_aliases import normalize_tool_arguments
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult


def _context() -> ToolInvocationContext:
    return ToolInvocationContext(
        agent=AgentKind.VOICE, user_id="user", workspace_id="workspace", tool_call_id="call",
        local_session_id="session", voice_session_id="voice-session",
    )


def test_workspace_path_alias_maps_to_directory() -> None:
    captured: dict[str, object] = {}

    def handler(_context, arguments):
        captured.update(arguments)
        return ToolInvocationResult("ok")

    catalog = ToolCatalog(authorizer=lambda _definition, _context: True)
    catalog.register(ToolDefinition(
        tool_id="builtin.workspace-list-directory.v1",
        name="workspace_list_directory",
        description="List",
        input_schema={
            "type": "object",
            "properties": {"directory": {"type": "string"}, "shareId": {"type": "string"}},
            "additionalProperties": False,
        },
        handler=handler,
    ))
    result = catalog.invoke("workspace_list_directory", {"path": "local/Tax-2024/invoices"}, context=_context())
    assert not result.is_error
    assert captured["directory"] == "local/Tax-2024/invoices"


def test_normalize_tool_arguments_accepts_file_path_alias() -> None:
    normalized = normalize_tool_arguments("workspace_read_file", {"path": "shared/alice/Reports/q1.md"})
    assert normalized == {"fileKey": "shared/alice/Reports/q1.md"}
