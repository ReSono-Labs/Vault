"""Hosted MCP process lifecycle for packages imported through mcp.package.json."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.vault_runtime.extensions.filesystem import extension_category_path, extension_data_path
from app.vault_runtime.extensions.models import ExtensionKind, ExtensionState
from app.vault_runtime.extensions.repository import ExtensionRecord, ExtensionRepository
from app.vault_runtime.extensions.runtime_port_forwarder import (
    RuntimePortForwarder,
    RuntimePortForwarderError,
    runtime_port_publish_enabled,
)
from app.vault_runtime.extensions.secrets import ExtensionSecretStore


logger = logging.getLogger(__name__)

_PORT_BASE = 8788
_PORT_LIMIT = 8899
_PORT_CAPACITY = _PORT_LIMIT - _PORT_BASE + 1
_HEALTH_TIMEOUT_SECONDS = 20.0
_HEALTH_POLL_SECONDS = 0.25
_PYTHON_NAMES = frozenset({"python", "python3"})


class McpRuntimeError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class McpRuntimeStatus:
    state: str
    port: int | None
    endpoint: str | None
    pid: int | None
    last_error: str | None


@dataclass(slots=True)
class _ManagedProcess:
    record: ExtensionRecord
    process: subprocess.Popen[str]
    port: int
    endpoint: str


class McpRuntimeSupervisor:
    def __init__(
        self, *, repository: ExtensionRepository, secrets: ExtensionSecretStore,
        extension_root: Path,
    ) -> None:
        self._repository = repository
        self._secrets = secrets
        self._root = extension_root.resolve()
        self._runtime_root = self._root / "runtime"
        self._data_root = self._root / "data"
        self._port_file = self._runtime_root / "ports.json"
        self._lock = threading.RLock()
        self._processes: dict[str, _ManagedProcess] = {}
        self._port_forwarder = RuntimePortForwarder()

    def status(self, record: ExtensionRecord) -> McpRuntimeStatus:
        runtime = _runtime_configuration(record)
        if runtime is None:
            return McpRuntimeStatus("external", None, _external_endpoint(record), None, None)
        managed = self._processes.get(record.extension_id)
        if managed is not None and managed.process.poll() is None:
            return McpRuntimeStatus("running", managed.port, managed.endpoint, managed.process.pid, None)
        stored = record.configuration.get("runtimeStatus", {})
        if isinstance(stored, dict):
            return McpRuntimeStatus(
                str(stored.get("state", "stopped")),
                int(stored["port"]) if isinstance(stored.get("port"), int) else None,
                str(stored["endpoint"]) if isinstance(stored.get("endpoint"), str) else None,
                int(stored["pid"]) if isinstance(stored.get("pid"), int) else None,
                str(stored["lastError"]) if isinstance(stored.get("lastError"), str) else None,
            )
        return McpRuntimeStatus("stopped", None, None, None, None)

    def start(
        self, *, actor_user_id: str, workspace_id: str, record: ExtensionRecord,
    ) -> McpRuntimeStatus:
        runtime = _runtime_configuration(record)
        if runtime is None:
            raise McpRuntimeError("This extension does not have a supervised runtime")
        with self._lock:
            self.stop(record=record, actor_user_id=actor_user_id, workspace_id=workspace_id)
            install_root = self._install_root(record)
            if not install_root.is_dir():
                raise McpRuntimeError("Supervised extension files are unavailable")
            port = self._allocate_port(record.extension_id)
            env = self._build_env(
                actor_user_id=actor_user_id, workspace_id=workspace_id,
                record=record, install_root=install_root, port=port,
            )
            data_dir = self._data_dir(record.identity)
            cwd = install_root / str(runtime.get("cwd", "."))
            if not cwd.is_dir():
                raise McpRuntimeError("Hosted MCP working directory is unavailable")
            bind_host = "0.0.0.0" if runtime_port_publish_enabled() else "127.0.0.1"
            env["VAULT_MCP_BIND"] = bind_host
            env["PORT"] = str(port)
            command = self._prepare_command(
                list(runtime["command"]), install_root=install_root, data_dir=data_dir, env=env,
                runtime_cwd=Path(str(runtime.get("cwd", "."))),
            )
            try:
                process = subprocess.Popen(
                    command, cwd=cwd, env=env,
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                    text=True, start_new_session=True,
                )
            except OSError as exc:
                self._persist_status(
                    actor_user_id=actor_user_id, workspace_id=workspace_id,
                    record=record, status=McpRuntimeStatus("error", port, None, None, str(exc)),
                )
                raise McpRuntimeError("Supervised extension process could not start") from exc
            mcp_path = runtime.get("mcpPath")
            endpoint = (
                f"http://127.0.0.1:{port}{mcp_path}"
                if isinstance(mcp_path, str) and mcp_path
                else f"http://127.0.0.1:{port}"
            )
            health_path = str(runtime.get("healthPath", "/health"))
            try:
                self._wait_for_health(port=port, health_path=health_path)
            except McpRuntimeError as exc:
                self._terminate(process)
                stderr = process.stderr.read() if process.stderr is not None else ""
                detail = str(exc) if not stderr else f"{exc} ({stderr.strip()[:240]})"
                self._persist_status(
                    actor_user_id=actor_user_id, workspace_id=workspace_id,
                    record=record,
                    status=McpRuntimeStatus("error", port, endpoint, process.pid, detail),
                    endpoint=endpoint,
                )
                raise
            self._processes[record.extension_id] = _ManagedProcess(record, process, port, endpoint)
            status = McpRuntimeStatus("running", port, endpoint, process.pid, None)
            self._persist_status(
                actor_user_id=actor_user_id, workspace_id=workspace_id,
                record=record, status=status, endpoint=endpoint, runtime=runtime,
            )
            self._publish_host_port(record=record, runtime=runtime, target_port=port)
            logger.info("supervised extension %s listening on %s", record.identity, endpoint)
            return status

    def stop(
        self, *, record: ExtensionRecord, actor_user_id: str | None = None,
        workspace_id: str | None = None, release_port: bool = False,
    ) -> None:
        with self._lock:
            managed = self._processes.pop(record.extension_id, None)
            runtime = _runtime_configuration(record)
            if runtime is not None:
                self._unpublish_host_port(runtime=runtime)
            if managed is not None:
                self._terminate(managed.process)
            if release_port:
                self._release_port(record.extension_id)
            if actor_user_id is not None and workspace_id is not None:
                self._persist_status(
                    actor_user_id=actor_user_id, workspace_id=workspace_id,
                    record=record, status=McpRuntimeStatus("stopped", None, None, None, None),
                )

    def restore_on_boot(self) -> None:
        list_enabled = getattr(self._repository, "list_enabled_supervised_runtimes", None)
        if list_enabled is None:
            list_enabled = getattr(self._repository, "list_enabled_hosted_mcps", None)
        if list_enabled is None:
            return
        for record in list_enabled():
            try:
                self.start(
                    actor_user_id=record.installed_by_user_id,
                    workspace_id=record.workspace_id,
                    record=record,
                )
            except McpRuntimeError as exc:
                logger.warning("supervised extension %s did not restore on boot: %s", record.identity, exc)

    def restart_enabled(self, *, actor_user_id: str, workspace_id: str) -> None:
        for record in self._repository.list_installed(
            actor_user_id=actor_user_id, workspace_id=workspace_id,
        ):
            if record.state is not ExtensionState.ENABLED:
                continue
            if record.kind not in {ExtensionKind.MCP, ExtensionKind.PLUGIN}:
                continue
            if _runtime_configuration(record) is None:
                continue
            try:
                self.start(actor_user_id=actor_user_id, workspace_id=workspace_id, record=record)
            except McpRuntimeError as exc:
                logger.warning("supervised extension %s did not restart: %s", record.identity, exc)

    def _install_root(self, record: ExtensionRecord) -> Path:
        category = "plugins" if record.kind is ExtensionKind.PLUGIN else "mcps"
        return (extension_category_path(
            root=self._root, category=category, identity=record.identity,
        ) / "current").resolve()

    def _data_dir(self, identity: str) -> Path:
        path = extension_data_path(root=self._root, identity=identity)
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        return path

    def _build_env(
        self, *, actor_user_id: str, workspace_id: str, record: ExtensionRecord,
        install_root: Path, port: int,
    ) -> dict[str, str]:
        env = os.environ.copy()
        env["VAULT_MCP_PORT"] = str(port)
        env["PORT"] = str(port)
        bind_host = "0.0.0.0" if runtime_port_publish_enabled() else "127.0.0.1"
        env["VAULT_MCP_BIND"] = bind_host
        env["VAULT_PLUGIN_ROOT"] = str(install_root)
        env["VAULT_PLUGIN_DATA"] = str(self._data_dir(record.identity))
        workspace_root = self._data_dir(record.identity) / "workspace"
        env["RESONO_WORKSPACE"] = str(workspace_root)
        database_path = self._data_dir(record.identity) / "resono.db"
        if database_path.is_file():
            env["RESONO_DB"] = str(database_path)
        settings = record.configuration.get("settings", {})
        if isinstance(settings, dict):
            for key, value in settings.items():
                env[f"VAULT_MCP_SETTING_{str(key).upper()}"] = str(value)
        for header, value in self._secrets.resolve_headers(
            user_id=actor_user_id, workspace_id=workspace_id, extension_id=record.extension_id,
        ):
            if header.lower() == "authorization":
                token = value.removeprefix("Bearer ").strip()
                env["MCP_AUTH_TOKEN"] = token
            env[f"VAULT_MCP_HEADER_{header.upper().replace('-', '_')}"] = value
        return env

    def _allocate_port(self, extension_id: str) -> int:
        self._runtime_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        allocations: dict[str, int] = {}
        if self._port_file.is_file():
            allocations = json.loads(self._port_file.read_text(encoding="utf-8"))
        if extension_id in allocations:
            return int(allocations[extension_id])
        used = set(allocations.values()) | {
            managed.port for managed in self._processes.values()
        }
        for port in range(_PORT_BASE, _PORT_LIMIT + 1):
            if port not in used:
                allocations[extension_id] = port
                self._port_file.write_text(json.dumps(allocations, sort_keys=True), encoding="utf-8")
                os.chmod(self._port_file, 0o600)
                return port
        raise McpRuntimeError("No internal MCP ports are available")

    def _release_port(self, extension_id: str) -> None:
        if not self._port_file.is_file():
            return
        allocations = json.loads(self._port_file.read_text(encoding="utf-8"))
        if extension_id not in allocations:
            return
        allocations.pop(extension_id, None)
        self._port_file.write_text(json.dumps(allocations, sort_keys=True), encoding="utf-8")
        os.chmod(self._port_file, 0o600)

    def _prepare_command(
        self, command: list[str], *, install_root: Path, data_dir: Path, env: dict[str, str],
        runtime_cwd: Path = Path("."),
    ) -> list[str]:
        venv_python = self._ensure_python_environment(
            install_root=install_root, data_dir=data_dir, runtime_cwd=runtime_cwd,
        )
        if venv_python is None:
            return command
        env["VAULT_MCP_VENV"] = str(venv_python.parent.parent)
        env["VAULT_MCP_PYTHON"] = str(venv_python)
        if command and Path(command[0]).name in _PYTHON_NAMES:
            return [str(venv_python), *command[1:]]
        return command

    def _ensure_python_environment(
        self, *, install_root: Path, data_dir: Path, runtime_cwd: Path = Path("."),
    ) -> Path | None:
        cwd = (install_root / runtime_cwd).resolve()
        requirements = cwd / "requirements.txt"
        if not requirements.is_file():
            requirements = install_root / "requirements.txt"
        if not requirements.is_file():
            return None
        venv_dir = data_dir / ".venv"
        venv_python = venv_dir / "bin" / "python3"
        digest = sha256(requirements.read_bytes()).hexdigest()
        stamp = data_dir / ".requirements.sha256"
        if stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == digest and venv_python.is_file():
            return venv_python
        try:
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_dir)],
                check=True, capture_output=True, text=True,
            )
            subprocess.run(
                [str(venv_dir / "bin" / "pip"), "install", "--disable-pip-version-check", "-r", str(requirements)],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or str(exc)).strip()[:240]
            raise McpRuntimeError(f"Hosted MCP dependency install failed: {detail}") from exc
        stamp.write_text(digest + "\n", encoding="utf-8")
        os.chmod(stamp, 0o600)
        if not venv_python.is_file():
            raise McpRuntimeError("Hosted MCP virtual environment is unavailable")
        return venv_python

    def _wait_for_health(self, *, port: int, health_path: str) -> None:
        deadline = time.monotonic() + _HEALTH_TIMEOUT_SECONDS
        url = f"http://127.0.0.1:{port}{health_path}"
        while time.monotonic() < deadline:
            try:
                with urlopen(Request(url, method="GET"), timeout=1.0) as response:
                    if 200 <= response.status < 300:
                        return
            except URLError:
                time.sleep(_HEALTH_POLL_SECONDS)
            time.sleep(_HEALTH_POLL_SECONDS)
        raise McpRuntimeError("Hosted MCP health check timed out")

    def _persist_status(
        self, *, actor_user_id: str, workspace_id: str, record: ExtensionRecord,
        status: McpRuntimeStatus, endpoint: str | None = None,
        runtime: dict[str, Any] | None = None,
    ) -> None:
        configuration = dict(record.configuration)
        runtime_status: dict[str, object] = {
            "state": status.state,
            "port": status.port,
            "endpoint": status.endpoint,
            "pid": status.pid,
            "lastError": status.last_error,
        }
        if runtime is not None and isinstance(runtime.get("port"), int):
            published_port = int(runtime["port"])
            runtime_status["publishedPort"] = published_port
            if status.state == "running" and published_port != status.port:
                runtime_status["publishedEndpoint"] = f"http://127.0.0.1:{published_port}"
        configuration["runtimeStatus"] = runtime_status
        if endpoint is not None and record.kind is ExtensionKind.MCP:
            configuration["endpoint"] = endpoint
            configuration["url"] = endpoint
        self._repository.update_configuration(
            actor_user_id=actor_user_id, workspace_id=workspace_id,
            extension_id=record.extension_id, configuration=configuration,
        )

    def _publish_host_port(
        self, *, record: ExtensionRecord, runtime: dict[str, Any], target_port: int,
    ) -> None:
        host_port = runtime.get("port")
        if not isinstance(host_port, int) or host_port == target_port:
            return
        try:
            self._port_forwarder.publish(
                host_port=host_port, target_port=target_port, identity=record.identity,
            )
        except RuntimePortForwarderError as exc:
            logger.warning(
                "supervised extension %s could not publish host port %s: %s",
                record.identity, host_port, exc,
            )

    def _unpublish_host_port(self, *, runtime: dict[str, Any]) -> None:
        host_port = runtime.get("port")
        if isinstance(host_port, int):
            self._port_forwarder.unpublish(host_port=host_port)

    @staticmethod
    def _terminate(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def supervised_runtime_configuration(record: ExtensionRecord) -> dict[str, Any] | None:
    return _runtime_configuration(record)


def _runtime_configuration(record: ExtensionRecord) -> dict[str, Any] | None:
    runtime = record.configuration.get("runtime")
    if not isinstance(runtime, dict):
        return None
    if record.configuration.get("packageType") == "hosted":
        return runtime
    if record.kind is ExtensionKind.PLUGIN and record.configuration.get("supervised"):
        return runtime
    return None


def _external_endpoint(record: ExtensionRecord) -> str | None:
    endpoint = record.configuration.get("endpoint") or record.configuration.get("url")
    return str(endpoint) if isinstance(endpoint, str) else None
