"""Interop with an independent MCP implementation (the official MCP Python SDK).

Opt-in: set ``VAULT_MCP_PEER_PATH`` to a folder with the ``mcp`` package installed (for
example ``pip install --target <dir> mcp==2.3.0``). Vault never imports the SDK; the peer
runs as a subprocess. Without the variable these tests are skipped.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import importlib.util
from http.server import ThreadingHTTPServer

import pytest

from app.vault_runtime.extensions import mcp_client, mcp_legacy
from app.vault_runtime.extensions.mcp_client import HttpMcpTransport, McpClient
from app.vault_runtime.extensions.mcp_lifecycle import McpLifecycle
from app.vault_runtime.extensions.models import ExtensionKind, ExtensionState
from app.vault_runtime.extensions.repository import ExtensionRecord
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolInvocationContext

PEER_PATH = os.environ.get("VAULT_MCP_PEER_PATH", "")
PEER = Path(__file__).parents[1] / "support" / "mcp_peer.py"
ROOT = Path(__file__).parents[2]
pytestmark = pytest.mark.skipif(not PEER_PATH or not (Path(PEER_PATH) / "mcp").is_dir(),
                                reason="VAULT_MCP_PEER_PATH (official MCP SDK) not set")


def _peer_env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": PEER_PATH, "PYTHONDONTWRITEBYTECODE": "1"}


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(autouse=True)
def fresh_caches():
    mcp_client._ERAS.clear()
    mcp_legacy._SESSIONS.clear()
    yield
    mcp_client._ERAS.clear()
    mcp_legacy._SESSIONS.clear()


@pytest.fixture(scope="module")
def sdk_server():
    port = _free_port()
    process = subprocess.Popen([sys.executable, str(PEER), "server", str(port)], env=_peer_env(),
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("SDK peer did not start")
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


class Repository:
    def __init__(self):
        self.tools = ()
        self.granted = ()

    def replace_mcp_tools(self, *, tools, **_):
        self.tools = tools

    def granted_mcp_tools(self, **_):
        return self.granted


def _agent_path(endpoint: str):
    """Discover, grant every tool, project and return (catalog, names, context): the
    catalog is what Voice, Chat and Background invoke through."""
    connection = ExtensionRecord(
        "peer", ExtensionKind.MCP, "peer", "peer", None, "SDK peer", "h", ExtensionState.ENABLED,
        "owner", "w", None, {"endpoint": endpoint, "transport": "streamable-http"},
    )
    repository = Repository()
    catalog = ToolCatalog(authorizer=lambda _d, _c: True)
    factory = lambda _c, _x: McpClient(HttpMcpTransport(endpoint))  # noqa: E731
    lifecycle = McpLifecycle(repository=repository, catalog=catalog, client_factory=factory)
    lifecycle.discover(actor_user_id="owner", workspace_id="w", connection=connection, client=factory(None, None))
    repository.granted = tuple((name, description, schema, output, "read")
                               for name, _title, description, schema, output, _hash in repository.tools)
    names = lifecycle.project_scope(user_id="u", workspace_id="w", agent=AgentKind.VOICE, connection=connection)
    by_remote = {name.split("_", 2)[2]: name for name in names}
    context = ToolInvocationContext(agent=AgentKind.VOICE, user_id="u", workspace_id="w",
                                    tool_call_id="call-1", local_session_id="session")
    return catalog, by_remote, context


@pytest.mark.parametrize("era", ["modern", "legacy"])
def test_vault_client_against_the_sdk_server(sdk_server, era) -> None:
    if era == "legacy":
        mcp_client._ERAS[sdk_server] = "legacy"
    catalog, tools, context = _agent_path(sdk_server)
    assert set(tools) == {"weather", "picture", "broken"}
    assert mcp_client._ERAS[sdk_server] == era
    # The SDK checks Mcp-Param-Region against the body; a non-ASCII value goes Base64.
    weather = catalog.invoke(tools["weather"], {"city": "Zürich", "region": "Zürich-Ost"}, context=context)
    assert not weather.is_error, weather.text
    assert weather.structured_content == {"city": "Zürich", "region": "Zürich-Ost", "celsius": 21}
    picture = catalog.invoke(tools["picture"], {}, context=context)
    assert not picture.is_error and picture.text == "[image content: image/png]"
    broken = catalog.invoke(tools["broken"], {}, context=context)
    # The tool's own error comes back even though it declares an output schema
    # (the SDK hides the exception text by design).
    assert broken.is_error and broken.text == "Error executing tool broken"


@pytest.mark.parametrize("starter", ["mcp-kit/starters/starter.example/server.py", "plugin-kit/starters/python/server.py"])
def test_sdk_client_against_the_starters(starter) -> None:
    spec = importlib.util.spec_from_file_location("starter_for_peer", ROOT / starter)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    server = ThreadingHTTPServer(("127.0.0.1", 0), module.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/mcp"
        done = subprocess.run([sys.executable, str(PEER), "client", url], env=_peer_env(),
                              capture_output=True, text=True, timeout=60)
        assert done.returncode == 0, done.stderr[-2000:]
        result = json.loads(done.stdout.strip().splitlines()[-1])
        assert result == {"tools": ["starter_greeting"], "structured": {"message": "Hello, Ada!"}, "is_error": False}
    finally:
        server.shutdown()
        server.server_close()
