"""Hosted extension processes are confined by the kernel (Landlock), proved by real access
attempts: a process reads its own install and data, and cannot read Vault's data, another
install of the same name, or another process's environment."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen

import pytest

from app.vault_runtime.extensions import confinement
from app.vault_runtime.extensions.filesystem import ExtensionFilesystem
from app.vault_runtime.extensions.mcp_runtime import McpRuntimeSupervisor
from app.vault_runtime.extensions.models import ExtensionKind, ExtensionState
from app.vault_runtime.extensions.repository import ExtensionRecord
from tests.unit.test_mcp_runtime_supervisor import Repository, _FakeSecrets

pytestmark = pytest.mark.skipif(confinement.landlock_abi() < 1, reason="Linux Landlock is not available here")

PROBE = r'''
import json, os, sys
def attempt(action):
    try:
        action(); return "allowed"
    except PermissionError:
        return "denied"
    except FileNotFoundError:
        return "missing"
targets = json.loads(sys.argv[1])
print(json.dumps({
    "read_own_install": attempt(lambda: open(targets["install_file"]).read()),
    "write_own_data": attempt(lambda: open(os.path.join(targets["data"], "w.txt"), "w").write("x")),
    "write_own_install": attempt(lambda: open(os.path.join(targets["install"], "w.txt"), "w").write("x")),
    "read_vault_secret": attempt(lambda: open(targets["secret"]).read()),
    "list_vault_root": attempt(lambda: os.listdir(targets["vault_root"])),
    "read_other_install_data": attempt(lambda: open(targets["other_data_file"]).read()),
    "read_parent_environ": attempt(lambda: open(f"/proc/{os.getppid()}/environ").read()),
    "read_own_status": attempt(lambda: open("/proc/self/status").read()),
}))
'''


def _layout(tmp_path: Path) -> dict[str, str]:
    vault = tmp_path / "vault"
    install = vault / "extensions" / "mcps" / ".ws" / "w1" / "same.name" / "current"
    data = vault / "extensions" / "data" / ".ws" / "w1" / "same.name"
    other = vault / "extensions" / "data" / ".ws" / "w2" / "same.name"
    for path in (install, data, other, vault / "keys"):
        path.mkdir(parents=True)
    (install / "server.py").write_text("print('hi')\n")
    (other / "resono.db").write_text("other workspace's data")
    (vault / "keys" / "extension-credentials.key").write_text("master key")
    return {"vault_root": str(vault), "install": str(install), "install_file": str(install / "server.py"),
            "data": str(data), "other_data_file": str(other / "resono.db"),
            "secret": str(vault / "keys" / "extension-credentials.key")}


def test_the_kernel_refuses_everything_outside_the_install_and_its_data(tmp_path: Path) -> None:
    targets = _layout(tmp_path)
    command = confinement.launcher_command(
        [sys.executable, "-c", PROBE, json.dumps(targets)],
        rules=confinement.rules_for(install_root=Path(targets["install"]), data_dir=Path(targets["data"])),
    )
    done = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == {
        "read_own_install": "allowed", "write_own_data": "allowed", "write_own_install": "denied",
        "read_vault_secret": "denied", "list_vault_root": "denied", "read_other_install_data": "denied",
        "read_parent_environ": "denied", "read_own_status": "allowed",
    }
    # Unconfined, the same probe could read all of it (the test checks something real).
    loose = subprocess.run([sys.executable, "-c", PROBE, json.dumps(targets)], capture_output=True, text=True)
    assert json.loads(loose.stdout)["read_other_install_data"] == "allowed"


SERVER = r'''
import json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
def attempt(path):
    try:
        open(path).read(); return "allowed"
    except PermissionError:
        return "denied"
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        body = json.dumps({"health": True} if self.path == "/health" else {
            "own": attempt(os.path.join(os.environ["VAULT_PLUGIN_DATA"], "marker.txt")),
            "other": attempt(os.environ["VAULT_MCP_SETTING_OTHER"]),
        }).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)
ThreadingHTTPServer(("127.0.0.1", int(os.environ["VAULT_MCP_PORT"])), H).serve_forever()
'''


def test_two_same_name_hosted_installs_cannot_read_each_others_data(tmp_path: Path) -> None:
    root = tmp_path / "extensions"
    filesystem = ExtensionFilesystem(root)
    source = tmp_path / "source"
    source.mkdir()
    (source / "server.py").write_text(SERVER)
    repository = Repository()
    supervisor = McpRuntimeSupervisor(repository=repository, secrets=_FakeSecrets(), extension_root=root)  # type: ignore[arg-type]
    records = {}
    for workspace in ("w1", "w2"):
        filesystem.replace(category="mcps", identity=f".ws/{workspace}/same.name", candidate_root=source)
        data = root / "data" / ".ws" / workspace / "same.name"
        data.mkdir(parents=True, exist_ok=True)
        (data / "marker.txt").write_text(f"{workspace} private data")
    for workspace, other in (("w1", "w2"), ("w2", "w1")):
        record = ExtensionRecord(
            f"id-{workspace}", ExtensionKind.MCP, "same.name", "same.name", "1", None, "hash",
            ExtensionState.ENABLED, "owner", workspace, None, {
                "packageType": "hosted", "transport": "streamable-http", "executable": True,
                "storageScope": "workspace",
                "runtime": {"type": "process", "command": ["python3", "server.py"], "cwd": ".",
                            "healthPath": "/health", "mcpPath": "/mcp"},
                "settings": {"other": str(root / "data" / ".ws" / other / "same.name" / "marker.txt")},
            })
        repository.records[record.extension_id] = record
        records[workspace] = record
    try:
        for workspace, record in records.items():
            status = supervisor.start(actor_user_id="owner", workspace_id=workspace, record=record)
            assert status.confinement == "landlock"
            assert repository.records[record.extension_id].configuration["runtimeStatus"]["confinement"] == "landlock"
            with urlopen(f"http://127.0.0.1:{status.port}/probe", timeout=5) as response:
                assert json.loads(response.read()) == {"own": "allowed", "other": "denied"}
    finally:
        for record in records.values():
            supervisor.stop(record=repository.records[record.extension_id])


def test_the_emergency_switch_turns_confinement_off(monkeypatch) -> None:
    monkeypatch.setenv("RESONO_VAULT_HOSTED_CONFINEMENT", "off")
    command, mode = McpRuntimeSupervisor._confine(["x"], install_root=Path("/i"), data_dir=Path("/d"), env={})
    assert (command, mode) == (["x"], "none")


def test_a_package_cannot_replace_the_launcher_with_its_own_code(tmp_path: Path) -> None:
    """The launcher ignores the working directory and PYTHONPATH (isolated mode)."""
    fake = tmp_path / "pkg" / "app" / "vault_runtime" / "extensions"
    fake.mkdir(parents=True)
    for folder in (fake.parents[1], fake.parent, fake):
        (folder / "__init__.py").write_text("")
    (fake / "confinement.py").write_text("def main(argv):\n    print('ESCAPED')\n    return 0\n")
    targets = _layout(tmp_path)
    command = confinement.launcher_command(
        [sys.executable, "-c", "print('confined')"],
        rules=confinement.rules_for(install_root=Path(targets["install"]), data_dir=Path(targets["data"])))
    done = subprocess.run(command, capture_output=True, text=True, cwd=tmp_path / "pkg",
                          env={**os.environ, "PYTHONPATH": str(tmp_path / "pkg")}, timeout=60)
    assert done.stdout.strip() == "confined" and "ESCAPED" not in done.stdout


def test_network_allowlist_refuses_ports_not_on_the_list(tmp_path: Path) -> None:
    import socket
    import threading

    if confinement.landlock_abi() < 4:
        pytest.skip("Landlock network rules need ABI 4")
    listeners = []
    for _ in range(2):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(4)
        listeners.append(server)
    threading.Thread(target=lambda: [s.accept() for s in listeners for _ in range(1)], daemon=True).start()
    allowed, blocked = (s.getsockname()[1] for s in listeners)
    probe = ("import socket, sys\n"
             "def go(p):\n"
             "    try:\n"
             "        socket.create_connection(('127.0.0.1', p), timeout=3).close(); return 'allowed'\n"
             "    except PermissionError: return 'denied'\n"
             f"print(go({allowed}), go({blocked}))")
    targets = _layout(tmp_path)
    command = confinement.launcher_command(
        [sys.executable, "-c", probe],
        rules=confinement.rules_for(install_root=Path(targets["install"]), data_dir=Path(targets["data"])),
        network=([], [allowed]))
    done = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert done.stdout.split() == ["allowed", "denied"], done.stderr
    for server in listeners:
        server.close()


def test_cpu_share_priority_and_oom_preference_apply(tmp_path: Path) -> None:
    targets = _layout(tmp_path)
    probe = ("import os; print(sorted(os.sched_getaffinity(0)), os.nice(0), "
             "open('/proc/self/oom_score_adj').read().strip())")
    first = sorted(os.sched_getaffinity(0))[-1]
    command = confinement.launcher_command(
        [sys.executable, "-c", probe], cpus=(first,),
        rules=confinement.rules_for(install_root=Path(targets["install"]), data_dir=Path(targets["data"])))
    done = subprocess.run(command, capture_output=True, text=True, timeout=60)
    assert done.stdout.strip() == f"[{first}] 10 1000", done.stderr


def test_percentages_are_shares_of_what_vault_may_use() -> None:
    from app.vault_runtime.host_resources import HostResources, share_of_cpus, share_of_memory
    docker = HostResources(6 * 1024**3, 3.0, (0, 1, 2, 3), "cgroup", "cgroup")   # cpus: "3.0" on 4 cores
    assert share_of_memory(docker, 25) == 1536 * 1024**2
    assert share_of_cpus(docker, 50) == (3,) and share_of_cpus(docker, 100) == (1, 2, 3)
    small = HostResources(2 * 1024**3, 1.0, (0,), "system", "system")             # small native install
    assert share_of_cpus(small, 10) == (0,) and share_of_memory(small, 5) == 128 * 1024**2


def test_host_resources_read_container_and_service_limits(tmp_path: Path) -> None:
    from app.vault_runtime.host_resources import detect

    root, proc = tmp_path / "cgroup", tmp_path / "proc"
    service = root / "system.slice" / "resono-vault.service"
    service.mkdir(parents=True)
    (proc / "self").mkdir(parents=True)
    (proc / "self" / "cgroup").write_text("0::/system.slice/resono-vault.service\n")
    (proc / "meminfo").write_text("MemTotal:       16384000 kB\n")
    (service / "memory.max").write_text("max\n")
    (service / "cpu.max").write_text("max 100000\n")
    native = detect(cgroup_root=root, proc=proc)            # no service limits: the machine's memory
    assert native.memory_source == "system" and native.memory_bytes == 16384000 * 1024
    (service / "memory.max").write_text(str(4 * 1024**3))
    (service / "cpu.max").write_text("150000 100000\n")
    limited = detect(cgroup_root=root, proc=proc)           # MemoryMax=4G, CPUQuota=150%
    assert (limited.memory_bytes, limited.memory_source) == (4 * 1024**3, "cgroup")
    assert min(limited.cpus, 1.5) == 1.5 and limited.cpu_source in ("cgroup", "affinity", "system")


GREEDY = r'''
import os, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"ok")
server = ThreadingHTTPServer(("127.0.0.1", int(os.environ["VAULT_MCP_PORT"])), H)
threading.Thread(target=server.serve_forever, daemon=True).start()
time.sleep(0.5)
mode = os.environ["VAULT_MCP_SETTING_MODE"]
if mode == "memory":
    hog = bytearray(400 * 1024 * 1024)
    for i in range(0, len(hog), 4096): hog[i] = 1
elif mode == "processes":
    import subprocess
    children = [subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"]) for _ in range(12)]
time.sleep(60)
'''


@pytest.mark.parametrize("mode,limit_field,expect", [("memory", "memory", "MB"), ("processes", "processes", "processes")])
def test_the_watchdog_stops_a_package_over_its_limit(tmp_path: Path, monkeypatch, mode, limit_field, expect) -> None:
    import time as _time
    from app.vault_runtime import host_resources
    from app.vault_runtime.extensions import mcp_runtime

    root = tmp_path / "extensions"
    source = tmp_path / "source"
    source.mkdir()
    (source / "server.py").write_text(GREEDY)
    ExtensionFilesystem(root).replace(category="mcps", identity=".ws/w1/greedy", candidate_root=source)

    class Limited(Repository):
        def device_setting(self, key):
            return {"memoryPercent": 5, "maxProcesses": 6}

    monkeypatch.setattr(mcp_runtime, "_WATCHDOG_SECONDS", 0.5)
    monkeypatch.setattr(host_resources, "detect", lambda: host_resources.HostResources(
        4 * 1024**3, 2.0, tuple(sorted(os.sched_getaffinity(0))), "cgroup", "cgroup"))   # 5% = ~205 MB
    repository = Limited()
    record = ExtensionRecord("greedy", ExtensionKind.MCP, "greedy", "greedy", "1", None, "hash",
                             ExtensionState.ENABLED, "owner", "w1", None, {
                                 "packageType": "hosted", "transport": "streamable-http", "executable": True,
                                 "storageScope": "workspace", "settings": {"mode": mode},
                                 "runtime": {"type": "process", "command": ["python3", "server.py"], "cwd": ".",
                                             "healthPath": "/health", "mcpPath": "/mcp"}})
    repository.records[record.extension_id] = record
    supervisor = McpRuntimeSupervisor(repository=repository, secrets=_FakeSecrets(), extension_root=root)  # type: ignore[arg-type]
    status = supervisor.start(actor_user_id="owner", workspace_id="w1", record=record)
    try:
        assert status.limits["maxProcesses"] == 6
        deadline = _time.monotonic() + 30
        while _time.monotonic() < deadline:
            runtime = repository.records[record.extension_id].configuration["runtimeStatus"]
            if runtime["state"] == "error":
                break
            _time.sleep(0.25)
        assert runtime["state"] == "error" and expect in runtime["lastError"], runtime
        assert status.pid is not None
        with pytest.raises(ProcessLookupError):
            os.killpg(status.pid, 0)                          # the whole group is gone
    finally:
        supervisor.stop(record=repository.records[record.extension_id])
