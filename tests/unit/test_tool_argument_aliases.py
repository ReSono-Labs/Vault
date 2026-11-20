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


class _Mutation:
    def __init__(self, file_key: str) -> None:
        self.file_key = file_key

    def to_dict(self) -> dict[str, object]:
        return {"fileKey": self.file_key}


class _FakeWorkspaceService:
    """Records what the real workspace tool handlers pass to the service."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self._local = None

    def workspace_root_info(self, **_kwargs) -> dict[str, object]:
        return {}

    def write_text_file(self, **kwargs):
        self.calls.append(("write", kwargs))
        return _Mutation(kwargs["file_key"])

    def patch_file(self, **kwargs):
        self.calls.append(("patch", kwargs))
        return _Mutation(kwargs["file_key"])

    def list_directory(self, **kwargs):
        self.calls.append(("list", kwargs))

        class _Listing:
            currentDirectory = kwargs["directory"] or ""

            def to_dict(self) -> dict[str, object]:
                return {"currentDirectory": self.currentDirectory, "entries": []}

        return _Listing()


def _workspace_catalog() -> tuple[ToolCatalog, _FakeWorkspaceService]:
    from app.vault_runtime.workspace_files.tools import register_workspace_file_tools

    service = _FakeWorkspaceService()
    catalog = ToolCatalog(authorizer=lambda _definition, _context: True)
    register_workspace_file_tools(catalog=catalog, service=service)  # type: ignore[arg-type]
    return catalog, service


def test_save_file_accepts_its_schema_field_and_the_content_spelling() -> None:
    catalog, service = _workspace_catalog()
    first = catalog.invoke("workspace_save_file", {"fileKey": "Idea Lab/README.md", "contentMarkdown": "# One"},
                           context=_context())
    second = catalog.invoke("workspace_save_file", {"fileKey": "Idea Lab/README.md", "content": "# Two"},
                            context=_context())
    assert not first.is_error, first.text
    assert not second.is_error, second.text
    assert [call[1]["content_markdown"] for call in service.calls] == ["# One", "# Two"]
    assert all(call[1]["overwrite_existing"] is True for call in service.calls)


def test_patch_file_accepts_camel_and_snake_case_strings() -> None:
    catalog, service = _workspace_catalog()
    first = catalog.invoke("workspace_patch_file",
                           {"fileKey": "Idea Lab/README.md", "oldString": "a", "newString": "b", "replaceAll": True},
                           context=_context())
    second = catalog.invoke("workspace_patch_file",
                            {"fileKey": "Idea Lab/README.md", "old_string": "c", "new_string": ""},
                            context=_context())
    assert not first.is_error, first.text
    assert not second.is_error, second.text
    assert [(c[1]["old_string"], c[1]["new_string"], c[1]["replace_all"]) for c in service.calls] == [
        ("a", "b", True), ("c", "", False),
    ]


def test_patch_file_without_old_string_names_only_the_missing_field() -> None:
    catalog, _service = _workspace_catalog()
    result = catalog.invoke("workspace_patch_file", {"fileKey": "Idea Lab/README.md", "newString": "b"},
                            context=_context())
    assert result.is_error
    assert "oldString" in result.text and "newString" not in result.text


def test_schema_fields_survive_normalization() -> None:
    read = normalize_tool_arguments("workspace_read_file", {"fileKey": "a.md", "startLine": 3, "endLine": 9})
    search = normalize_tool_arguments("workspace_search_files", {"query": "x", "regex": True, "include": ["*.md"]})
    assert read == {"fileKey": "a.md", "startLine": 3, "endLine": 9}
    assert search == {"query": "x", "regex": True, "include": ["*.md"]}


def test_vault_area_prefix_means_the_vault_root() -> None:
    catalog, service = _workspace_catalog()
    for key in ("vault/Idea Lab/README.md", "vault://Idea Lab/README.md", "Vault:/Idea Lab/README.md"):
        assert not catalog.invoke("workspace_save_file", {"fileKey": key, "contentMarkdown": "x"},
                                  context=_context()).is_error
    assert not catalog.invoke("workspace_list_directory", {"directory": "vault"}, context=_context()).is_error
    assert [call[1].get("file_key", call[1].get("directory")) for call in service.calls] == [
        "Idea Lab/README.md", "Idea Lab/README.md", "Idea Lab/README.md", None,
    ]
    assert normalize_tool_arguments("workspace_read_files", {"fileKeys": ["vault/a.md", "local/b.md"]}) == {
        "fileKeys": ["a.md", "local/b.md"],
    }
    assert normalize_tool_arguments("workspace_read_file", {"fileKey": "vault/a.md", "shareId": "s1"}) == {
        "fileKey": "vault/a.md", "shareId": "s1",
    }
    assert normalize_tool_arguments("workspace_read_file", {"fileKey": "vaulted/a.md"}) == {"fileKey": "vaulted/a.md"}
