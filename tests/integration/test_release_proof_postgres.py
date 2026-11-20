"""Three-standard release proof (issue #4, STD-RELEASE), through the normal agent path.

One Agent Plugin (#2) holds a Skill (#3) and a Streamable HTTP MCP server (#4). It is
imported in the shared workspace of the four-person setup. The Skill is listed, loaded and
its bundled reference read through the agent's skill tools. The MCP tool is granted to Ada
only and invoked through the tool catalog against the official MCP Python SDK (an
independent 2026-07-28 server with its own OAuth server); the answer names Ada's own
signed-in account. Ben, a member without a grant, and Cy, not a member, cannot see or use it.

Opt-in: needs ``VAULT_MCP_PEER_PATH`` (folder with ``mcp`` installed) and the test database.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlsplit

import pytest

from app.vault_runtime.extensions import mcp_client
from app.vault_runtime.extensions.mcp_client import HttpMcpTransport, McpClient
from app.vault_runtime.extensions.mcp_lifecycle import McpLifecycle
from app.vault_runtime.extensions.specification import MCP_SCHEMA_ID, PLUGIN_SCHEMA_ID
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolInvocationContext
from tests.integration.test_extensions_postgres import _confirm_plugin
from tests.integration.test_four_person_isolation_postgres import world  # noqa: F401  (fixture)
from tests.unit.test_extension_import_service import _zip

PEER_PATH = os.environ.get("VAULT_MCP_PEER_PATH", "")
REDIRECT = "https://127.0.0.1:8765/extensions/oauth/callback"
pytestmark = pytest.mark.skipif(not PEER_PATH, reason="VAULT_MCP_PEER_PATH (official MCP SDK) not set")


@pytest.fixture()
def sdk_peer():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    peer = Path(__file__).parents[1] / "support" / "mcp_peer.py"
    process = subprocess.Popen([sys.executable, str(peer), "protected-server", str(port)],
                               env={**os.environ, "PYTHONPATH": PEER_PATH, "PYTHONDONTWRITEBYTECODE": "1"},
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(150):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.2)
        mcp_client._ERAS.clear()
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def test_release_proof_plugin_skill_and_mcp_through_the_agent_path(world, sdk_peer) -> None:  # noqa: F811
    people, extensions, imports, _root, accounts, activation = world
    shared = people.shared_workspace
    plugin_zip = _zip({
        "release.demo/plugin.json": json.dumps({"$schema": PLUGIN_SCHEMA_ID, "name": "release.demo"}),
        "release.demo/skills/crm-notes/SKILL.md":
            "---\nname: crm-notes\ndescription: How to look up a CRM contact.\n---\n"
            "Call the CRM whoami tool, then read references/fields.md.\n",
        "release.demo/skills/crm-notes/references/fields.md": "Fields: name, email, owner.\n",
        "release.demo/mcp.json": json.dumps({"$schema": MCP_SCHEMA_ID, "mcpServers": {
            "crm": {"type": "streamable-http", "url": sdk_peer}}}),
    })
    plugin = _confirm_plugin(imports, people.owner, plugin_zip, workspace_id=shared)
    connection = extensions.managed_children(actor_user_id=people.owner.user_id, workspace_id=shared,
                                             plugin_id=plugin.extension_id)[0]
    assert (connection.configuration.get("endpoint") or connection.configuration.get("url")) == sdk_peer

    def context(name, agent=AgentKind.VOICE):
        return ToolInvocationContext(agent=agent, user_id=people[name].user_id, workspace_id=shared,
                                     tool_call_id=f"call-{name}", local_session_id="session")

    def sign_in(name):
        started = accounts.start_sign_in(user_id=people[name].user_id, workspace_id=shared,
                                         extension_id=connection.extension_id, redirect_uri=REDIRECT)

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None
        try:
            urllib.request.build_opener(NoRedirect).open(started["authorizationUrl"], timeout=10)
            raise AssertionError("sign-in did not redirect")
        except urllib.error.HTTPError as redirect:
            values = {k: v[0] for k, v in parse_qs(urlsplit(redirect.headers["Location"]).query).items()}
        accounts.complete_sign_in(user_id=people[name].user_id, state=values["state"], code=values.get("code"),
                                  iss=values.get("iss"), error=values.get("error"))

    def factory(record, ctx):
        endpoint = record.configuration.get("endpoint") or record.configuration["url"]
        return McpClient(HttpMcpTransport(endpoint, credential_headers=accounts.headers_for(
            user_id=ctx.user_id, workspace_id=ctx.workspace_id, extension_id=record.extension_id, endpoint=endpoint)))

    def refused(record, ctx, error):
        return accounts.explain_rejection(user_id=ctx.user_id, workspace_id=ctx.workspace_id,
                                          extension_id=record.extension_id,
                                          endpoint=record.configuration.get("endpoint") or record.configuration["url"],
                                          error=error)

    catalog = ToolCatalog(authorizer=lambda _d, _c: True)
    for definition in activation.tool_definitions():
        catalog.register(definition)
    lifecycle = McpLifecycle(repository=extensions, catalog=catalog, client_factory=factory, auth_refused=refused)

    # #4: the owner signs in to discover; nothing is granted by discovery.
    sign_in("owner")
    assert lifecycle.discover(actor_user_id=people.owner.user_id, workspace_id=shared, connection=connection,
                              client=factory(connection, context("owner"))) == ("whoami",)
    for agent in (AgentKind.VOICE,):
        extensions.set_grant(actor_user_id=people.owner.user_id, target_user_id=people["ada"].user_id,
                             workspace_id=shared, extension_id=plugin.extension_id, agent=agent,
                             capability_name="skill:crm-notes", enabled=True)
        extensions.set_grant(actor_user_id=people.owner.user_id, target_user_id=people["ada"].user_id,
                             workspace_id=shared, extension_id=connection.extension_id, agent=agent,
                             capability_name="whoami", enabled=True, effect_class="read")
    projected = {name: lifecycle.project_scope(user_id=people[name].user_id, workspace_id=shared,
                                               agent=AgentKind.VOICE, connection=connection)
                 for name in ("ada", "ben")}
    assert len(projected["ada"]) == 1 and projected["ben"] == ()

    # #3: Ada's agent sees the skill, loads it, and reads its bundled reference.
    summaries = activation.list_available(user_id=people["ada"].user_id, workspace_id=shared, agent=AgentKind.VOICE)
    assert [item.name for item in summaries] == ["crm-notes"]
    loaded = catalog.invoke("load_agent_skill", {"name": "crm-notes"}, context=context("ada"))
    assert not loaded.is_error and "whoami tool" in loaded.text
    reference = catalog.invoke("read_agent_skill_resource", {"name": "crm-notes", "path": "references/fields.md"},
                               context=context("ada"))
    assert not reference.is_error and "Fields: name, email, owner." in reference.text

    # #4: Ada signs in with her own account; the tool answers as Ada, not as the owner.
    sign_in("ada")
    ada = catalog.invoke(projected["ada"][0], {}, context=context("ada"))
    assert not ada.is_error, ada.text
    owner_client = factory(connection, context("owner"))
    owner_client.initialize()
    owner_says = owner_client.call_tool("whoami", {})["content"][0]["text"]
    assert ada.text.startswith("signed in as user-") and ada.text != owner_says

    # Ungranted and outside people: no skill, no tool.
    for name in ("ben", "cy"):
        try:
            seen = [item.name for item in activation.list_available(
                user_id=people[name].user_id, workspace_id=shared, agent=AgentKind.VOICE)]
        except Exception:
            seen = []
        assert seen == []
        assert catalog.invoke(projected["ada"][0], {}, context=context(name)).is_error
        assert catalog.invoke("load_agent_skill", {"name": "crm-notes"}, context=context(name)).is_error
    # Wrong agent for Ada: refused too.
    assert catalog.invoke("load_agent_skill", {"name": "crm-notes"},
                          context=context("ada", AgentKind.BACKGROUND)).is_error
