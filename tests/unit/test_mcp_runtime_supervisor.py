from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from urllib.request import Request, urlopen

from app.vault_runtime.extensions.filesystem import ExtensionFilesystem
from app.vault_runtime.extensions.mcp_runtime import McpRuntimeSupervisor
from app.vault_runtime.extensions.models import ExtensionKind, ExtensionState
from app.vault_runtime.extensions.repository import ExtensionRecord


@dataclass
class _FakeSecrets:
    def resolve_headers(self, **kwargs) -> tuple[tuple[str, str], ...]:
        return ()


class Repository:
    def __init__(self) -> None:
        self.records: dict[str, ExtensionRecord] = {}

    def list_enabled_hosted_mcps(self) -> tuple[ExtensionRecord, ...]:
        return tuple(
            record for record in self.records.values()
            if record.kind is ExtensionKind.MCP
            and record.state is ExtensionState.ENABLED
            and record.configuration.get("packageType") == "hosted"
        )

    def update_configuration(self, *, actor_user_id, workspace_id, extension_id, configuration):
        record = self.records[extension_id]
        updated = ExtensionRecord(
            record.extension_id, record.kind, record.identity, record.display_name,
            record.version, record.description, record.content_hash, record.state,
            record.installed_by_user_id, record.workspace_id, record.previous_content_hash,
            configuration,
        )
        self.records[extension_id] = updated
        return updated


def _install_starter(tmp_path: Path) -> ExtensionRecord:
    repo_root = Path(__file__).resolve().parents[2]
    starter_root = repo_root / "mcp-kit" / "starters" / "starter.example"
    extension_root = tmp_path / "extensions"
    filesystem = ExtensionFilesystem(extension_root)
    filesystem.replace(
        category="mcps", identity="starter.example", candidate_root=starter_root,
    )
    record = ExtensionRecord(
        "mcp-starter", ExtensionKind.MCP, "starter.example", "starter.example", "0.1.0",
        "Hosted MCP package", "hash", ExtensionState.DISABLED, "owner", "workspace", None,
        {
            "packageType": "hosted",
            "transport": "streamable-http",
            "executable": True,
            "headers": {},
            "runtime": {
                "type": "process",
                "command": ["python3", "server.py"],
                "cwd": ".",
                "port": 8788,
                "healthPath": "/health",
                "mcpPath": "/mcp",
            },
            "settings": {"greeting": "Hi"},
            "runtimeStatus": {"state": "stopped"},
        },
    )
    return record


def test_supervisor_starts_starter_and_discovers_tools(tmp_path: Path) -> None:
    record = _install_starter(tmp_path)
    repository = Repository()
    repository.records[record.extension_id] = record
    supervisor = McpRuntimeSupervisor(
        repository=repository,  # type: ignore[arg-type]
        secrets=_FakeSecrets(),  # type: ignore[arg-type]
        extension_root=tmp_path / "extensions",
    )
    status = supervisor.start(actor_user_id="owner", workspace_id="workspace", record=record)
    assert status.state == "running"
    assert status.endpoint is not None
    updated = repository.records[record.extension_id]
    endpoint = str(updated.configuration["endpoint"])
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {},
    }).encode()
    with urlopen(Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    ), timeout=3) as response:
        body = json.loads(response.read().decode())
    names = tuple(tool["name"] for tool in body["result"]["tools"])
    assert names == ("starter_greeting",)
    supervisor.stop(record=updated)


def test_supervisor_installs_requirements_into_data_dir(tmp_path: Path) -> None:
    install_root = tmp_path / "extensions" / "mcps" / "deps.example" / "current"
    install_root.mkdir(parents=True)
    (install_root / "requirements.txt").write_text("# no third-party deps\n", encoding="utf-8")
    (install_root / "server.py").write_text("print('ok')\n", encoding="utf-8")
    record = ExtensionRecord(
        "mcp-deps", ExtensionKind.MCP, "deps.example", "deps.example", "0.1.0",
        "deps", "hash", ExtensionState.DISABLED, "owner", "workspace", None,
        {
            "packageType": "hosted",
            "runtime": {
                "type": "process",
                "command": ["python3", "-c", "print('alive')"],
                "cwd": ".",
                "port": 8788,
                "healthPath": "/health",
                "mcpPath": "/mcp",
            },
        },
    )
    repository = Repository()
    repository.records[record.extension_id] = record
    supervisor = McpRuntimeSupervisor(
        repository=repository,  # type: ignore[arg-type]
        secrets=_FakeSecrets(),  # type: ignore[arg-type]
        extension_root=tmp_path / "extensions",
    )
    data_dir = tmp_path / "extensions" / "data" / "deps.example"
    venv_python = supervisor._ensure_python_environment(install_root=install_root, data_dir=data_dir)
    assert venv_python is not None
    assert (data_dir / ".venv" / "bin" / "python3").is_file()
    assert (data_dir / ".requirements.sha256").is_file()
