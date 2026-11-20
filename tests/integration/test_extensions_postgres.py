from __future__ import annotations

from hashlib import sha256
import json
import os
from io import BytesIO
from pathlib import Path
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
    extensions, identities, owner, _member = extension_state
    assert extensions.identity_still_installed(
        identity="missing.plugin",
        excluding_extension_id=None,
    ) is False
    # Data folders are keyed by identity alone: any kind, any workspace counts.
    second = identities.create_workspace(principal=owner.principal, display_name="Second")
    hosted = extensions.install(
        actor_user_id=owner.principal.user_id, workspace_id=second,
        kind=ExtensionKind.MCP, identity="shared.name", display_name="shared.name", version=None,
        description="MCP", content_hash="hash", configuration={"packageType": "hosted"},
    )
    assert extensions.identity_still_installed(identity="shared.name") is True
    assert extensions.identity_still_installed(
        identity="shared.name", excluding_extension_id=hosted.extension_id,
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
    # The supervisor reads the same device-wide row without a user scope.
    assert extensions.device_safe_mode() is True
    assert not extensions.granted(
        user_id=member_scoped.user_id, workspace_id=owner.principal.workspace_id,
        extension_id=installed.extension_id, agent=AgentKind.VOICE,
    )
    extensions.set_safe_mode(
        actor_user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        enabled=False,
    )
    assert extensions.device_safe_mode() is False
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
    assert extensions.device_safe_mode() is True
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


def _zip(files: dict[str, str]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


def _tree_hash(root: Path) -> str:
    """sha256 over every file's relative path and bytes; a missing tree hashes as 'absent'."""
    if not root.exists():
        return "absent"
    digest = sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode()); digest.update(b"\0")
        digest.update(path.read_bytes()); digest.update(b"\0")
    return digest.hexdigest()


def _migration(on_conflict: str) -> dict[str, object]:
    return {"workspace": {"source": "migration/workspace", "target": "workspace"}, "onConflict": on_conflict}


def _hosted_package(name: str, *, version: str, marker: str, on_conflict: str | None = "replace") -> bytes:
    manifest: dict[str, object] = {
        "$schema": "https://schemas.resonolabs.com/vault/mcp-package/v1.json",
        "name": name, "version": version, "configuration": "config.schema.json",
        "runtime": {
            "type": "process", "command": ["python3", "server.py"], "cwd": ".",
            "port": 8791, "healthPath": "/health", "mcpPath": "/mcp",
        },
    }
    files = {
        f"{name}/config.schema.json": json.dumps({
            "$schema": "https://schemas.resonolabs.com/vault/plugin-config/v1.json", "fields": [],
        }),
        f"{name}/server.py": f"print('{marker}')\n",
    }
    if on_conflict is not None:
        manifest["migration"] = _migration(on_conflict)
        files[f"{name}/migration/workspace/NOTES.md"] = f"package {marker}\n"
    files[f"{name}/mcp.package.json"] = json.dumps(manifest)
    return _zip(files)


def _data_plugin(name: str, *, version: str, marker: str, on_conflict: str = "replace") -> bytes:
    return _zip({
        f"{name}/plugin.json": json.dumps({
            "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
            "name": name, "version": version, "description": f"Plugin {marker}",
        }),
        f"{name}/vault.json": json.dumps({
            "$schema": "https://schemas.resonolabs.com/vault/plugin/v1.json",
            "minimumVaultVersion": "0.1.0", "agents": ["voice"], "migration": _migration(on_conflict),
        }),
        f"{name}/migration/workspace/NOTES.md": f"plugin {marker}\n",
    })


def _imports(extensions, tmp_path):
    root = tmp_path / "extensions"
    return ExtensionImportService(
        repository=extensions, inspector=ArchiveInspector(tmp_path / "quarantine"),
        filesystem=ExtensionFilesystem(root),
    ), root


def _confirm_hosted(imports, owner, payload, *, workspace_id=None, replace=False, replace_migration=False):
    workspace_id = workspace_id or owner.principal.workspace_id
    preview = imports.preflight_mcp_package(
        payload, "package.zip", actor_user_id=owner.principal.user_id, workspace_id=workspace_id,
        audience=ExtensionAudience(frozenset({AgentKind.VOICE})),
    )
    return imports.confirm_mcp_package(
        preview.token, actor_user_id=owner.principal.user_id, workspace_id=workspace_id,
        replace=replace, replace_migration=replace_migration,
    )


def _confirm_plugin(imports, owner, payload, *, workspace_id=None, replace=False, replace_migration=False):
    workspace_id = workspace_id or owner.principal.workspace_id
    preview = imports.preflight_plugin(
        payload, "plugin.zip", actor_user_id=owner.principal.user_id, workspace_id=workspace_id,
        audience=ExtensionAudience(frozenset({AgentKind.VOICE})),
    )
    return imports.confirm_plugin(
        preview.token, actor_user_id=owner.principal.user_id, workspace_id=workspace_id,
        replace=replace, replace_migration=replace_migration,
    )


def _remove(imports, owner, record):
    return imports.set_state(
        actor_user_id=owner.principal.user_id, workspace_id=record.workspace_id,
        extension_id=record.extension_id, state=ExtensionState.REMOVED,
    )


def _fail_install_after_replacement(monkeypatch, extensions) -> None:
    def failing_install(**_kwargs):
        raise RuntimeError("injected failure after replacement started")
    monkeypatch.setattr(extensions, "install", failing_install)


def test_failed_hosted_package_upgrade_keeps_previous_data_byte_for_byte(extension_state, tmp_path, monkeypatch) -> None:
    extensions, _identities, owner, _member = extension_state
    imports, root = _imports(extensions, tmp_path)
    _confirm_hosted(imports, owner, _hosted_package("resono.business", version="0.1.0", marker="v1"))
    data, tree = root / "data/resono.business", root / "mcps/resono.business/current"
    (data / "runtime-state.json").write_text('{"written":"by the running package"}', encoding="utf-8")
    before = (_tree_hash(data), _tree_hash(tree))
    assert (data / "workspace/NOTES.md").read_text(encoding="utf-8") == "package v1\n"

    # The owner has to approve replacing existing data; refusing touches nothing.
    with pytest.raises(Exception, match="Confirm migration replacement"):
        _confirm_hosted(imports, owner, _hosted_package(
            "resono.business", version="0.2.0", marker="v2", on_conflict="ask",
        ), replace=True)
    assert (_tree_hash(data), _tree_hash(tree)) == before

    # The tree is replaced and the migration has overwritten data when the fault hits.
    _fail_install_after_replacement(monkeypatch, extensions)
    with pytest.raises(RuntimeError, match="injected"):
        _confirm_hosted(imports, owner, _hosted_package("resono.business", version="0.2.0", marker="v2"), replace=True)
    assert (_tree_hash(data), _tree_hash(tree)) == before
    assert not any((root / "recovery").glob("data-*"))


def test_failed_plugin_upgrade_keeps_previous_data_byte_for_byte(extension_state, tmp_path, monkeypatch) -> None:
    extensions, _identities, owner, _member = extension_state
    imports, root = _imports(extensions, tmp_path)
    _confirm_plugin(imports, owner, _data_plugin("demo.data", version="0.1.0", marker="v1"))
    data, tree = root / "data/demo.data", root / "plugins/demo.data/current"
    (data / "user-notes.txt").write_text("kept", encoding="utf-8")
    before = (_tree_hash(data), _tree_hash(tree))

    with pytest.raises(Exception, match="Confirm migration replacement"):
        _confirm_plugin(imports, owner, _data_plugin("demo.data", version="0.2.0", marker="v2", on_conflict="ask"), replace=True)
    assert (_tree_hash(data), _tree_hash(tree)) == before

    _fail_install_after_replacement(monkeypatch, extensions)
    with pytest.raises(RuntimeError, match="injected"):
        _confirm_plugin(imports, owner, _data_plugin("demo.data", version="0.2.0", marker="v2"), replace=True)
    assert (_tree_hash(data), _tree_hash(tree)) == before
    assert (data / "workspace/NOTES.md").read_text(encoding="utf-8") == "plugin v1\n"


def test_hosted_package_removal_keeps_data_a_same_identity_plugin_uses(extension_state, tmp_path) -> None:
    extensions, _identities, owner, _member = extension_state
    imports, root = _imports(extensions, tmp_path)
    # The live resono.business case: a packageData plugin and a hosted package share data/resono.business.
    plugin = _confirm_plugin(imports, owner, _data_plugin("resono.business", version="0.1.0", marker="plugin"))
    hosted = _confirm_hosted(imports, owner, _hosted_package(
        "resono.business", version="0.1.0", marker="hosted", on_conflict=None,
    ))
    data = root / "data/resono.business"
    (data / "business.db").write_bytes(b"customer records")
    before = _tree_hash(data)

    _remove(imports, owner, hosted)
    assert _tree_hash(data) == before
    assert not (root / "mcps/resono.business").exists()
    assert (root / "plugins/resono.business/current/plugin.json").is_file()

    _remove(imports, owner, plugin)
    assert not data.exists()


def test_hosted_package_removal_deletes_its_current_and_previous_trees(extension_state, tmp_path) -> None:
    extensions, _identities, owner, _member = extension_state
    imports, root = _imports(extensions, tmp_path)
    _confirm_hosted(imports, owner, _hosted_package("demo.hosted", version="0.1.0", marker="v1"))
    upgraded = _confirm_hosted(
        imports, owner, _hosted_package("demo.hosted", version="0.2.0", marker="v2"), replace=True,
    )
    base = root / "mcps/demo.hosted"
    assert (base / "current/server.py").read_text(encoding="utf-8") == "print('v2')\n"
    assert (base / "previous/server.py").read_text(encoding="utf-8") == "print('v1')\n"

    _remove(imports, owner, upgraded)
    assert not (base / "current").exists() and not (base / "previous").exists()
    assert not base.exists()
    assert not (root / "data/demo.hosted").exists()
