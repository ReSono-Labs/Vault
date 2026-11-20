"""Four-person isolation matrix for plugins, skills and MCP (STD-FOURUSER, STD-RELEASE).

Uses the one shared setup in ``tests/support/four_people.py``: the owner and three users,
four private workspaces and one shared workspace (owner, Ada, Ben; Cy is not a member).
"""
from __future__ import annotations

import os

import pytest

from app.vault_runtime.extensions.activation import SkillActivation
from app.vault_runtime.extensions.mcp_accounts import McpAccounts
from app.vault_runtime.extensions.models import ExtensionKind
from app.vault_runtime.extensions.repository import ExtensionNotFoundError, ExtensionRepository
from app.vault_runtime.extensions.secrets import LocalMasterKey
from app.vault_runtime.system_agents.inventory import AgentKind
from tests.integration.test_extensions_postgres import _confirm_skill, _imports, _remove, _skill_zip, _ws
from tests.support.four_people import build_four_people


@pytest.fixture()
def world(tmp_path):
    database_url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("VAULT_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    people = build_four_people(database_url)
    extensions = ExtensionRepository(database_url=database_url)
    extensions.ensure_schema()
    extensions.set_safe_mode(actor_user_id=people.owner.user_id, workspace_id=people.owner.private_workspace,
                             enabled=False)
    imports, root = _imports(extensions, tmp_path)
    accounts = McpAccounts(repository=extensions, master_key=LocalMasterKey(tmp_path / "keys" / "c.key"))
    activation = SkillActivation(repository=extensions, extension_root=root)
    yield people, extensions, imports, root, accounts, activation
    import psycopg
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")


def _mcp(extensions, people, workspace, identity="crm"):
    return extensions.install(
        actor_user_id=people.owner.user_id, workspace_id=workspace, kind=ExtensionKind.MCP, identity=identity,
        display_name=identity, version=None, description=None, content_hash=f"hash-{identity}-{workspace}",
        configuration={"endpoint": "https://crm.example/mcp", "transport": "streamable-http"}, components=())


def test_twelve_cross_private_attempts_are_refused_for_plugins_skills_and_mcp(world) -> None:
    people, extensions, imports, _root, accounts, activation = world
    owner_ws = people.owner.private_workspace
    skill = _confirm_skill(imports, people.owner, _skill_zip("notes", "Owner private notes."), workspace_id=owner_ws)
    plugin = extensions.install(
        actor_user_id=people.owner.user_id, workspace_id=owner_ws, kind=ExtensionKind.PLUGIN, identity="notes.plugin",
        display_name="Notes", version="1", description=None, content_hash="hash-plugin", configuration={},
        components=(("skill", "plugin-skill", "c1"),))
    connection = _mcp(extensions, people, owner_ws)
    for record in (skill, plugin, connection):
        extensions.set_grant(actor_user_id=people.owner.user_id, target_user_id=people.owner.user_id,
                             workspace_id=owner_ws, extension_id=record.extension_id, agent=AgentKind.VOICE,
                             enabled=True, effect_class="read" if record is connection else None,
                             capability_name="lookup" if record is connection else "")
    accounts.set_personal_headers(user_id=people.owner.user_id, workspace_id=owner_ws,
                                  extension_id=connection.extension_id, headers={"Authorization": "Bearer owner"})

    attempts = {
        "list installs": lambda actor, victim: extensions.list_installed(
            actor_user_id=actor.user_id, workspace_id=victim.private_workspace),
        "read a skill": lambda actor, victim: activation.load(
            user_id=actor.user_id, workspace_id=victim.private_workspace, agent=AgentKind.VOICE,
            extension_id=skill.extension_id, name="notes"),
        "open a plugin": lambda actor, victim: extensions.by_id(
            actor_user_id=actor.user_id, workspace_id=victim.private_workspace, extension_id=plugin.extension_id),
        "list MCP tool grants": lambda actor, victim: extensions.granted_mcp_tools(
            user_id=actor.user_id, workspace_id=victim.private_workspace, agent=AgentKind.VOICE,
            extension_id=connection.extension_id),
        "use an MCP credential": lambda actor, victim: accounts.headers_for(
            user_id=actor.user_id, workspace_id=victim.private_workspace, extension_id=connection.extension_id,
            endpoint="https://crm.example/mcp"),
        "grant oneself": lambda actor, victim: extensions.set_grant(
            actor_user_id=actor.user_id, target_user_id=actor.user_id, workspace_id=victim.private_workspace,
            extension_id=skill.extension_id, agent=AgentKind.VOICE, enabled=True),
    }
    assert len(people.pairs()) == 12
    leaks = {name: people.cross_private(attempt) for name, attempt in attempts.items()}
    assert leaks == {name: [] for name in attempts}
    # The owner still reaches their own installs (the attempts above were refusals, not breakage).
    assert activation.load(user_id=people.owner.user_id, workspace_id=owner_ws, agent=AgentKind.VOICE,
                           extension_id=skill.extension_id, name="notes") == "Owner private notes.\n"


def test_shared_workspace_grant_wrong_agent_and_revocations(world) -> None:
    people, extensions, imports, _root, accounts, activation = world
    shared = people.shared_workspace
    skill = _confirm_skill(imports, people.owner, _skill_zip("notes", "Family notes."), workspace_id=shared)
    extensions.set_grant(actor_user_id=people.owner.user_id, target_user_id=people["ada"].user_id,
                         workspace_id=shared, extension_id=skill.extension_id, agent=AgentKind.VOICE, enabled=True)

    def read(name, agent=AgentKind.VOICE):
        try:
            return activation.load(user_id=people[name].user_id, workspace_id=shared, agent=agent,
                                   extension_id=skill.extension_id, name="notes")
        except Exception:
            return None

    assert read("ada") == "Family notes.\n"                       # explicit grant
    assert read("ada", AgentKind.BACKGROUND) is None              # wrong agent
    assert read("ben") is None                                    # member without a grant
    assert read("cy") is None                                     # not a member
    # Only the device owner grants; a member cannot grant themselves.
    with pytest.raises(Exception):
        extensions.set_grant(actor_user_id=people["ben"].user_id, target_user_id=people["ben"].user_id,
                             workspace_id=shared, extension_id=skill.extension_id, agent=AgentKind.VOICE, enabled=True)
    # Revoking the grant takes effect at the next read.
    extensions.set_grant(actor_user_id=people.owner.user_id, target_user_id=people["ada"].user_id,
                         workspace_id=shared, extension_id=skill.extension_id, agent=AgentKind.VOICE, enabled=False)
    assert read("ada") is None
    # So does leaving the workspace, even with the grant restored first.
    extensions.set_grant(actor_user_id=people.owner.user_id, target_user_id=people["ada"].user_id,
                         workspace_id=shared, extension_id=skill.extension_id, agent=AgentKind.VOICE, enabled=True)
    assert read("ada") == "Family notes.\n"
    people.leave_shared("ada")
    assert read("ada") is None

    # MCP in the shared workspace: Ben's own credential is never Ada's or Cy's.
    connection = _mcp(extensions, people, shared)
    accounts.set_personal_headers(user_id=people["ben"].user_id, workspace_id=shared,
                                  extension_id=connection.extension_id, headers={"Authorization": "Bearer ben"})
    ben = accounts.headers_for(user_id=people["ben"].user_id, workspace_id=shared,
                               extension_id=connection.extension_id, endpoint="https://crm.example/mcp")
    assert ben == (("Authorization", "Bearer ben"),)
    assert accounts.headers_for(user_id=people.owner.user_id, workspace_id=shared,
                                extension_id=connection.extension_id, endpoint="https://crm.example/mcp") == ()
    for outsider in ("ada", "cy"):                                # Ada left; Cy was never in
        with pytest.raises(Exception):
            accounts.headers_for(user_id=people[outsider].user_id, workspace_id=shared,
                                 extension_id=connection.extension_id, endpoint="https://crm.example/mcp")


def test_same_name_installs_in_private_and_shared_workspaces_stay_independent(world) -> None:
    people, extensions, imports, root, _accounts, activation = world
    private, shared = people.owner.private_workspace, people.shared_workspace
    installs = {ws: _confirm_skill(imports, people.owner, _skill_zip("notes", f"Notes for {label}."), workspace_id=ws)
                for ws, label in ((private, "private"), (shared, "family"))}
    for ws, record in installs.items():
        extensions.set_grant(actor_user_id=people.owner.user_id, target_user_id=people.owner.user_id,
                             workspace_id=ws, extension_id=record.extension_id, agent=AgentKind.VOICE, enabled=True)

    def read(ws):
        try:
            return activation.load(user_id=people.owner.user_id, workspace_id=ws, agent=AgentKind.VOICE,
                                   extension_id=installs[ws].extension_id, name="notes")
        except ExtensionNotFoundError:
            return None

    assert (read(private), read(shared)) == ("Notes for private.\n", "Notes for family.\n")
    # Upgrade one: the other keeps its version and bytes.
    upgraded = _confirm_skill(imports, people.owner, _skill_zip("notes", "Family notes v2."),
                              workspace_id=shared, replace=True)
    assert upgraded.extension_id == installs[shared].extension_id
    assert (read(private), read(shared)) == ("Notes for private.\n", "Family notes v2.\n")
    # Remove one: the other is untouched.
    _remove(imports, people.owner, installs[shared])
    assert read(private) == "Notes for private.\n" and read(shared) is None
    assert _ws(root, "skills", private, "notes").exists() and not _ws(root, "skills", shared, "notes").exists()
