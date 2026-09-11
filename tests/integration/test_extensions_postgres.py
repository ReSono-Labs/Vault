from __future__ import annotations

import os
from io import BytesIO
import zipfile

import psycopg
import pytest

from app.core.security.tokens import hash_token
from app.vault_runtime.extensions.models import ExtensionKind, ExtensionState
from app.vault_runtime.extensions.activation import SkillActivation
from app.vault_runtime.extensions.archives import ArchiveInspector
from app.vault_runtime.extensions.filesystem import ExtensionFilesystem
from app.vault_runtime.extensions.models import ExtensionAudience
from app.vault_runtime.extensions.repository import (
    ExtensionAuthorizationError, ExtensionConflictError, ExtensionRepository,
)
from app.vault_runtime.extensions.secrets import ExtensionSecretStore, LocalMasterKey
from app.vault_runtime.extensions.service import ExtensionImportService
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.local_identity.service import LocalIdentityService
from app.vault_runtime.system_agents.inventory import AgentKind


@pytest.fixture()
def extension_state():
    database_url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("VAULT_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
    identities = LocalIdentityService(
        repository=LocalIdentityRepository(database_url=database_url),
        setup_credential_hash=hash_token("setup"),
    )
    identities.ensure_schema()
    owner = identities.bootstrap_owner(
        setup_credential="setup", username="owner", password="owner-password",
        display_name="Owner", experience_style="strict",
    )
    identities.create_user(
        actor=owner.principal, username="member", password="member-password",
        display_name="Member", experience_style="funny",
    )
    member = identities.login(username="member", password="member-password")
    identities.add_member(
        principal=owner.principal, workspace_id=owner.principal.workspace_id, username="member",
    )
    extensions = ExtensionRepository(database_url=database_url)
    extensions.ensure_schema()
    yield extensions, identities, owner, member
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")


def _install(extensions, owner, *, identity="demo", component="demo-skill"):
    return extensions.install(
        actor_user_id=owner.principal.user_id,
        workspace_id=owner.principal.workspace_id,
        kind=ExtensionKind.PLUGIN, identity=identity, display_name=identity,
        version="1.0.0", description="local", content_hash=f"hash-{identity}",
        configuration={}, components=(("skill", component, f"component-{component}"),),
    )


def test_owner_install_replace_and_component_collision_are_transactional(extension_state) -> None:
    extensions, _identities, owner, _member = extension_state
    installed = _install(extensions, owner)
    assert installed.state is ExtensionState.ENABLED
    replaced = extensions.install(
        actor_user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        kind=ExtensionKind.PLUGIN, identity="demo", display_name="demo", version="2.0.0",
        description="new", content_hash="hash-new", configuration={},
        components=(("skill", "demo-skill", "component-new"),),
    )
    assert replaced.content_hash == "hash-new" and replaced.previous_content_hash == "hash-demo"
    with pytest.raises(ExtensionConflictError):
        _install(extensions, owner, identity="other", component="demo-skill")
    assert extensions.get(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        kind=ExtensionKind.PLUGIN, identity="other", owner=True,
    ) is None


def test_plugin_managed_mcp_children_follow_parent_lifecycle(extension_state) -> None:
    extensions, _identities, owner, _member = extension_state
    plugin = _install(extensions, owner, identity="example.plugin")
    children = extensions.reconcile_managed_mcp(
        actor_user_id=owner.principal.user_id,
        workspace_id=owner.principal.workspace_id,
        plugin=plugin,
        servers=(("weather", "server-hash", {
            "transport": "streamable-http", "url": "http://127.0.0.1:8788/mcp",
            "headers": {}, "executable": True,
        }),),
    )
    assert len(children) == 1
    assert children[0].identity == "example.plugin/weather"
    assert children[0].configuration["managedByPluginId"] == plugin.extension_id
    assert all(item.extension_id != children[0].extension_id for item in extensions.list_installed(
        actor_user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
    ))
    extensions.set_managed_state(
        actor_user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        plugin_id=plugin.extension_id, state=ExtensionState.DISABLED,
    )
    assert extensions.by_id(
        actor_user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        extension_id=children[0].extension_id, owner=True,
    ).state is ExtensionState.DISABLED


def test_identity_still_installed_accepts_null_exclusion(extension_state) -> None:
    extensions, _identities, owner, _member = extension_state
    assert extensions.identity_still_installed(
        workspace_id=owner.principal.workspace_id,
        identity="missing.plugin",
        excluding_extension_id=None,
    ) is False


def test_grants_are_exact_and_safe_mode_or_disable_revokes_immediately(extension_state) -> None:
    extensions, identities, owner, member = extension_state
    installed = _install(extensions, owner)
    identities.switch_workspace(
        principal=member.principal, workspace_id=owner.principal.workspace_id,
    )
    member_scoped = identities.authenticate(session_token=member.session_token)
    extensions.set_grant(
        actor_user_id=owner.principal.user_id, target_user_id=member_scoped.user_id,
        workspace_id=owner.principal.workspace_id, extension_id=installed.extension_id,
        agent=AgentKind.VOICE, enabled=True,
    )
    # Third-party capabilities are off after first boot until the device owner exits safe mode.
    assert not extensions.granted(
        user_id=member_scoped.user_id, workspace_id=owner.principal.workspace_id,
        extension_id=installed.extension_id, agent=AgentKind.VOICE,
    )
    extensions.set_safe_mode(
        actor_user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        enabled=False,
    )
    assert extensions.granted(
        user_id=member_scoped.user_id, workspace_id=owner.principal.workspace_id,
        extension_id=installed.extension_id, agent=AgentKind.VOICE,
    )
    assert not extensions.granted(
        user_id=member_scoped.user_id, workspace_id=owner.principal.workspace_id,
        extension_id=installed.extension_id, agent=AgentKind.BACKGROUND,
    )
    extensions.set_safe_mode(
        actor_user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        enabled=True,
    )
    assert not extensions.granted(
        user_id=member_scoped.user_id, workspace_id=owner.principal.workspace_id,
        extension_id=installed.extension_id, agent=AgentKind.VOICE,
    )
    extensions.set_safe_mode(
        actor_user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        enabled=False,
    )
    assert extensions.granted(
        user_id=member_scoped.user_id, workspace_id=owner.principal.workspace_id,
        extension_id=installed.extension_id, agent=AgentKind.VOICE,
    )
    extensions.set_state(
        actor_user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        extension_id=installed.extension_id, state=ExtensionState.DISABLED,
    )
    assert not extensions.granted(
        user_id=member_scoped.user_id, workspace_id=owner.principal.workspace_id,
        extension_id=installed.extension_id, agent=AgentKind.VOICE,
    )


def test_ordinary_user_cannot_mutate_and_private_workspaces_are_isolated(extension_state) -> None:
    extensions, _identities, owner, member = extension_state
    _install(extensions, owner)
    with pytest.raises(ExtensionAuthorizationError):
        extensions.install(
            actor_user_id=member.principal.user_id, workspace_id=member.principal.workspace_id,
            kind=ExtensionKind.SKILL, identity="bad", display_name="bad", version=None,
            description=None, content_hash="hash", configuration={},
        )
    with pytest.raises(ExtensionAuthorizationError):
        extensions.get(
            user_id=owner.principal.user_id, workspace_id=member.principal.workspace_id,
            kind=ExtensionKind.PLUGIN, identity="demo",
        )


def test_schema_records_only_two_agent_kind_values(extension_state) -> None:
    extensions, _identities, owner, _member = extension_state
    installed = _install(extensions, owner)
    with extensions._connect() as connection:
        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute(
                """INSERT INTO vault_private.vault_extension_grants
                   (grant_id,extension_id,user_id,workspace_id,agent_kind,capability_name,enabled,granted_by_user_id)
                   VALUES ('bad',%s,%s,%s,'build','',true,%s)""",
                (installed.extension_id,owner.principal.user_id,owner.principal.workspace_id,owner.principal.user_id),
            )


def test_mcp_credentials_are_encrypted_and_never_returned_as_persistence_text(extension_state, tmp_path) -> None:
    extensions, _identities, owner, _member = extension_state
    connection = extensions.install(
        actor_user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        kind=ExtensionKind.MCP, identity="secure", display_name="secure", version=None,
        description="MCP", content_hash="config-hash",
        configuration={"transport": "streamable-http", "endpoint": "https://example.test/mcp"},
    )
    secrets = ExtensionSecretStore(
        repository=extensions, master_key=LocalMasterKey(tmp_path / "extension.key"),
    )
    secrets.set_headers(
        actor_user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        extension_id=connection.extension_id, headers={"Authorization": "Bearer never-store-plain"},
    )
    assert secrets.resolve_headers(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        extension_id=connection.extension_id,
    ) == (("Authorization", "Bearer never-store-plain"),)
    with extensions._connect() as database:
        nonce, ciphertext = database.execute(
            "SELECT nonce,ciphertext FROM vault_private.vault_extension_secrets WHERE extension_id=%s",
            (connection.extension_id,),
        ).fetchone()
        rendered = database.execute(
            "SELECT configuration_json::text FROM vault_private.vault_extensions WHERE extension_id=%s",
            (connection.extension_id,),
        ).fetchone()[0]
    assert b"never-store-plain" not in bytes(ciphertext)
    assert b"never-store-plain" not in bytes(nonce)
    assert "never-store-plain" not in rendered
    secrets.remove(
        actor_user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        extension_id=connection.extension_id,
    )
    assert secrets.resolve_headers(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        extension_id=connection.extension_id,
    ) == ()


def test_removal_drops_owned_components_grants_tools_and_credentials(extension_state, tmp_path) -> None:
    extensions, _identities, owner, _member = extension_state
    connection = extensions.install(
        actor_user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        kind=ExtensionKind.MCP, identity="remove-me", display_name="remove-me", version=None,
        description="MCP", content_hash="hash", configuration={},
        components=(("mcp", "remove-me", "component-hash"),),
    )
    secrets = ExtensionSecretStore(repository=extensions, master_key=LocalMasterKey(tmp_path / "key"))
    secrets.set_headers(
        actor_user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        extension_id=connection.extension_id, headers={"Authorization": "secret"},
    )
    extensions.set_grant(
        actor_user_id=owner.principal.user_id, target_user_id=owner.principal.user_id,
        workspace_id=owner.principal.workspace_id, extension_id=connection.extension_id,
        agent=AgentKind.VOICE, capability_name="tool", enabled=True, effect_class="read",
    )
    extensions.set_state(
        actor_user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        extension_id=connection.extension_id, state=ExtensionState.REMOVED,
    )
    with extensions._connect() as database:
        counts = tuple(database.execute(f"SELECT count(*) FROM vault_private.{table} WHERE extension_id=%s", (connection.extension_id,)).fetchone()[0] for table in (
            "vault_extension_components", "vault_extension_grants", "vault_mcp_tools", "vault_extension_secrets",
        ))
    assert counts == (0, 0, 0, 0)


def test_skill_progressive_disclosure_rechecks_scope_revocation_and_safe_mode(extension_state, tmp_path) -> None:
    extensions, _identities, owner, _member = extension_state
    filesystem = ExtensionFilesystem(tmp_path / "extensions")
    imports = ExtensionImportService(
        repository=extensions, inspector=ArchiveInspector(tmp_path / "quarantine"),
        filesystem=filesystem,
    )
    payload = BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("local-skill/SKILL.md", "---\nname: local-skill\ndescription: Load only when needed.\n---\nPrivate instructions.\n")
    preview = imports.preflight_skill(
        payload.getvalue(), "skill.zip", actor_user_id=owner.principal.user_id,
        workspace_id=owner.principal.workspace_id,
        audience=ExtensionAudience(frozenset({AgentKind.VOICE})),
    )
    installed = imports.confirm_skill(
        preview.token, actor_user_id=owner.principal.user_id,
        workspace_id=owner.principal.workspace_id, replace=False,
    )
    extensions.set_safe_mode(
        actor_user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        enabled=False,
    )
    extensions.set_grant(
        actor_user_id=owner.principal.user_id, target_user_id=owner.principal.user_id,
        workspace_id=owner.principal.workspace_id, extension_id=installed.extension_id,
        agent=AgentKind.VOICE, enabled=True,
    )
    activation = SkillActivation(repository=extensions, extension_root=tmp_path / "extensions")
    summaries = activation.list_available(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        agent=AgentKind.VOICE,
    )
    assert [(item.name, item.description) for item in summaries] == [("local-skill", "Load only when needed.")]
    assert activation.load(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        agent=AgentKind.VOICE, extension_id=installed.extension_id, name="local-skill",
    ) == "Private instructions.\n"
    extensions.set_safe_mode(
        actor_user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        enabled=True,
    )
    assert activation.list_available(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        agent=AgentKind.VOICE,
    ) == ()
