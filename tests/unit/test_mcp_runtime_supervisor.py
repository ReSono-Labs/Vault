from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
import socket
import time
from urllib.request import Request, urlopen

import pytest

from app.vault_runtime.extensions.filesystem import ExtensionFilesystem
from app.vault_runtime.extensions.mcp_runtime import McpRuntimeSafeModeError, McpRuntimeSupervisor
from app.vault_runtime.extensions.service import ExtensionImportService
from app.vault_runtime.extensions.models import ExtensionKind, ExtensionState
from app.vault_runtime.extensions.repository import ExtensionRecord


@dataclass
class _FakeSecrets:
    def resolve_headers(self, **kwargs) -> tuple[tuple[str, str], ...]:
        return ()


class Repository:
    def __init__(self) -> None:
        self.records: dict[str, ExtensionRecord] = {}
        # Stands in for the durable device-wide row; shared by every supervisor built on it.
        self.safe_mode = False

    def device_safe_mode(self) -> bool:
        return self.safe_mode

    def by_id(self, *, extension_id, **_):
        return self.records[extension_id]

    def list_installed(self, **_):
        return tuple(self.records.values())

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
        category="mcps", identity=".ws/workspace/starter.example", candidate_root=starter_root,
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
    meta = {"io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientCapabilities": {}}
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": meta},
    }).encode()
    with urlopen(Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "tools/list"},
        method="POST",
    ), timeout=3) as response:
        body = json.loads(response.read().decode())
    names = tuple(tool["name"] for tool in body["result"]["tools"])
    assert names == ("starter_greeting",)
    # Older clients still get the 2025-11-25 handshake.
    legacy = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "initialize", "params": {
        "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}}).encode()
    with urlopen(Request(endpoint, data=legacy, headers={"Content-Type": "application/json"}, method="POST"),
                 timeout=3) as response:
        assert json.loads(response.read().decode())["result"]["protocolVersion"] == "2025-11-25"
    supervisor.stop(record=updated)


def test_supervisor_installs_requirements_into_data_dir(tmp_path: Path) -> None:
    install_root = tmp_path / "extensions" / "mcps" / ".ws" / "workspace" / "deps.example" / "current"
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
    data_dir = tmp_path / "extensions" / "data" / ".ws" / "workspace" / "deps.example"
    venv_python = supervisor._ensure_python_environment(install_root=install_root, data_dir=data_dir)
    assert venv_python is not None
    assert (data_dir / ".venv" / "bin" / "python3").is_file()
    assert (data_dir / ".requirements.sha256").is_file()


def test_plugin_environment_excludes_vault_secrets(tmp_path: Path, monkeypatch) -> None:
    """SEC-04: a plugin process never inherits Vault's secrets from the environment."""
    monkeypatch.setenv("RESONO_VAULT_GOOGLE_OAUTH_CLIENT_SECRET", "secret-value")
    monkeypatch.setenv("RESONO_VAULT_LOCAL_API_TLS_PRIVATE_KEY_FILE", "/keys/tls.key")
    monkeypatch.setenv("RESONO_VAULT_DATABASE_URL", "postgresql://u:p@h/db")
    monkeypatch.setenv("SSL_CERT_FILE", "/etc/ssl/certs/ca.pem")
    record = _install_starter(tmp_path)
    supervisor = McpRuntimeSupervisor(
        repository=Repository(),  # type: ignore[arg-type]
        secrets=_FakeSecrets(),  # type: ignore[arg-type]
        extension_root=tmp_path / "extensions",
    )
    env = supervisor._build_env(actor_user_id="owner", workspace_id="workspace", record=record,
                                install_root=tmp_path, port=8790)
    assert "RESONO_VAULT_GOOGLE_OAUTH_CLIENT_SECRET" not in env
    assert "RESONO_VAULT_LOCAL_API_TLS_PRIVATE_KEY_FILE" not in env
    assert "RESONO_VAULT_DATABASE_URL" not in env
    assert env["SSL_CERT_FILE"] == "/etc/ssl/certs/ca.pem"
    assert env["PATH"] and env["VAULT_MCP_PORT"] == "8790"


def _gone(pid: int) -> bool:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        except FileNotFoundError:
            return True
        if stat.rsplit(")", 1)[1].split()[0] == "Z":
            return True
        time.sleep(0.05)
    return False


def _accepts(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def test_safe_mode_stops_supervised_processes_and_keeps_them_stopped(tmp_path: Path) -> None:
    starter = _install_starter(tmp_path)
    runtime = dict(starter.configuration["runtime"])
    # The server forks a helper child into its process group that ignores SIGTERM.
    runtime["command"] = [
        "sh", "-c",
        '(trap "" TERM; exec sleep 600) & echo $! > "$VAULT_PLUGIN_DATA/child.pid"; exec python3 server.py',
    ]
    record = replace(starter, state=ExtensionState.ENABLED, configuration={**starter.configuration, "runtime": runtime})
    repository = Repository()
    repository.records[record.extension_id] = record
    extension_root = tmp_path / "extensions"

    def supervisor() -> McpRuntimeSupervisor:
        return McpRuntimeSupervisor(
            repository=repository,  # type: ignore[arg-type]
            secrets=_FakeSecrets(),  # type: ignore[arg-type]
            extension_root=extension_root,
        )

    running = supervisor()
    status = running.start(actor_user_id="owner", workspace_id="workspace", record=record)
    assert status.state == "running" and status.pid is not None and status.port is not None
    child = int((extension_root / "data/.ws/workspace/starter.example/child.pid").read_text(encoding="utf-8"))
    assert _accepts(status.port)

    repository.safe_mode = True
    assert running.stop_all() == 1
    assert _gone(status.pid) and _gone(child)
    assert not _accepts(status.port)
    assert repository.records[record.extension_id].configuration["runtimeStatus"]["state"] == "stopped"
    with pytest.raises(McpRuntimeSafeModeError, match="Safe mode is on"):
        running.start(actor_user_id="owner", workspace_id="workspace", record=record)

    # A Vault restart: boot restore and automatic restart start nothing.
    restarted = supervisor()
    restarted.restore_on_boot()
    restarted.restart_enabled(actor_user_id="owner", workspace_id="workspace")
    # Confirm and enable go through the import service, which starts nothing either.
    imports = ExtensionImportService(
        repository=repository,  # type: ignore[arg-type]
        inspector=object(),  # type: ignore[arg-type]
        filesystem=ExtensionFilesystem(extension_root),
        mcp_runtime=restarted,
    )
    imports._start_supervised_if_enabled(actor_user_id="owner", workspace_id="workspace", record=record)
    imports._sync_supervised_runtime(
        actor_user_id="owner", workspace_id="workspace", record=record, state=ExtensionState.ENABLED,
    )
    assert restarted.status(repository.records[record.extension_id]).state == "stopped"
    assert not _accepts(status.port)

    repository.safe_mode = False
    resumed = restarted.start(actor_user_id="owner", workspace_id="workspace", record=record)
    assert resumed.state == "running" and _accepts(resumed.port)
    restarted.stop_all()
    assert _gone(resumed.pid)
