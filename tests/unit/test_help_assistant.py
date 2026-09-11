from pathlib import Path
from types import SimpleNamespace

from app.vault_runtime.help_assistant import HelpAssistant


class _Credentials:
    def selected_provider(self, *, user_id: str, workspace_id: str) -> str:
        assert (user_id, workspace_id) == ("user-1", "workspace-1")
        return "openai"

    def background_access(self, *, user_id: str, workspace_id: str, provider_key: str):
        assert provider_key == "openai"
        return SimpleNamespace(value="secret", auth_method="api_key"), "gpt-help"


class _Response:
    def raise_for_status(self) -> None: pass
    def json(self): return {"output_text": "Follow these clear steps."}


class _Transport:
    def __init__(self): self.payload = None
    def post(self, _url, *, headers, json):
        assert headers["Authorization"] == "Bearer secret"
        self.payload = json
        return _Response()


def _assistant(tmp_path: Path) -> HelpAssistant:
    source = tmp_path / "source"
    (source / "platform-documents").mkdir(parents=True)
    (source / "codebase" / "app").mkdir(parents=True)
    (source / "platform-documents" / "guide.md").write_text(
        "Connect an AI provider from Connections.", encoding="utf-8",
    )
    (source / "codebase" / "app" / "bridge.py").write_text(
        "LOCAL_BRIDGE_PORT = 8766\n", encoding="utf-8",
    )
    return HelpAssistant(
        credentials=_Credentials(), source_root=source,
        data_root=tmp_path / "data", transport=_Transport(),
    )


def test_dashboard_documents_are_indexed_and_prevent_learning(tmp_path: Path) -> None:
    assistant = _assistant(tmp_path)
    principal = SimpleNamespace(user_id="user-1", workspace_id="workspace-1")
    sources = assistant._retrieve("connect provider")
    assert sources and sources[0].kind == "guide"
    assert assistant._learn(principal, "connect provider", "Use Connections.", sources, []) is False
    assert "## connect provider" not in assistant.learned_notes(principal)


def test_code_only_answer_is_learned_once_and_provider_text_model_is_used(tmp_path: Path) -> None:
    assistant = _assistant(tmp_path)
    principal = SimpleNamespace(user_id="user-1", workspace_id="workspace-1")
    result = assistant.ask(principal, message="What is LOCAL_BRIDGE_PORT?")
    assert result["modelKey"] == "gpt-help"
    assert result["learned"] is True
    assert "codebase/app/bridge.py" in assistant.learned_notes(principal)
    assert assistant.ask(principal, message="What is LOCAL_BRIDGE_PORT?")["learned"] is True
    assert assistant.learned_notes(principal).count("## What is LOCAL_BRIDGE_PORT?") == 2


def test_mcp_questions_receive_the_exact_packaged_schema(tmp_path: Path) -> None:
    source = tmp_path / "source"
    schema = source / "codebase" / "app" / "vault_runtime" / "extensions" / "standards" / "mcp.schema.json"
    schema.parent.mkdir(parents=True)
    schema.write_text('{"required":["$schema","mcpServers"]}', encoding="utf-8")
    (source / "platform-documents").mkdir(parents=True)
    assistant = HelpAssistant(
        credentials=_Credentials(), source_root=source,
        data_root=tmp_path / "data", transport=_Transport(),
    )
    sources = assistant._retrieve("Help me draft an MCP connection")
    assert sources[0].path.endswith("mcp.schema.json")
    assert '"mcpServers"' in sources[0].excerpt
