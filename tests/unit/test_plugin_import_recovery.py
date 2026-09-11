from io import BytesIO
import json
from pathlib import Path
import zipfile

import pytest

from app.vault_runtime.extensions.archives import ArchiveInspector
from app.vault_runtime.extensions.filesystem import ExtensionFilesystem
from app.vault_runtime.extensions.models import ExtensionAudience, ExtensionKind, ExtensionState
from app.vault_runtime.extensions.repository import ExtensionRecord
from app.vault_runtime.extensions.service import ExtensionImportService
from app.vault_runtime.extensions.specification import PLUGIN_SCHEMA_ID
from app.vault_runtime.system_agents.inventory import AgentKind


def _zip(files: dict[str, str]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


class Repository:
    def __init__(self) -> None:
        self.records: dict[tuple[str, ExtensionKind, str], ExtensionRecord] = {}

    def get(self, *, user_id, workspace_id, kind, identity, owner=False, **_kwargs):
        return self.records.get((workspace_id, kind, identity))

    def get_active(self, *, user_id, workspace_id, kind, identity, owner=False, **_kwargs):
        record = self.get(
            user_id=user_id, workspace_id=workspace_id, kind=kind, identity=identity, owner=owner,
        )
        if record is None or record.state is ExtensionState.REMOVED:
            return None
        return record

    def identity_still_installed(self, *, workspace_id, identity, excluding_extension_id=None):
        for (scope, kind, name), record in self.records.items():
            if scope != workspace_id or name != identity or record.state is ExtensionState.REMOVED:
                continue
            if excluding_extension_id and record.extension_id == excluding_extension_id:
                continue
            return True
        return False

    def install(self, *, actor_user_id, workspace_id, kind, identity, display_name, version, description, content_hash, configuration, components=()):
        key = (workspace_id, kind, identity)
        prior = self.records.get(key)
        record = ExtensionRecord(
            prior.extension_id if prior else f"{kind.value}-{identity}",
            kind, identity, display_name, version, description, content_hash,
            ExtensionState.ENABLED, actor_user_id, workspace_id,
            prior.content_hash if prior else None, configuration,
        )
        self.records[key] = record
        return record


def test_preflight_after_remove_does_not_require_replacement(tmp_path: Path) -> None:
    repository = Repository()
    repository.records[("workspace-a", ExtensionKind.PLUGIN, "demo.plugin")] = ExtensionRecord(
        "plugin-demo", ExtensionKind.PLUGIN, "demo.plugin", "demo.plugin", "0.1.0",
        "Demo", "old-hash", ExtensionState.REMOVED, "owner", "workspace-a", None, {},
    )
    service = ExtensionImportService(
        repository=repository,
        inspector=ArchiveInspector(tmp_path / "quarantine"),
        filesystem=ExtensionFilesystem(tmp_path / "extensions"),
    )
    payload = _zip({
        "demo.plugin/plugin.json": json.dumps({
            "$schema": PLUGIN_SCHEMA_ID,
            "name": "demo.plugin",
            "version": "0.2.0",
            "description": "Demo plugin",
        }),
    })
    preview = service.preflight_plugin(
        payload, "demo.plugin.zip",
        actor_user_id="owner", workspace_id="workspace-a",
        audience=ExtensionAudience(agents=frozenset({AgentKind.VOICE})),
    )
    assert preview.current_hash is None


def test_failed_confirm_removes_orphan_plugin_tree_without_previous(tmp_path: Path) -> None:
    repository = Repository()
    service = ExtensionImportService(
        repository=repository,
        inspector=ArchiveInspector(tmp_path / "quarantine"),
        filesystem=ExtensionFilesystem(tmp_path / "extensions"),
    )
    payload = _zip({
        "demo.plugin/plugin.json": json.dumps({
            "$schema": PLUGIN_SCHEMA_ID,
            "name": "demo.plugin",
            "version": "0.1.0",
            "description": "Demo plugin",
        }),
        "demo.plugin/vault.json": json.dumps({
            "$schema": "https://schemas.resonolabs.com/vault/plugin/v1.json",
            "minimumVaultVersion": "0.1.0",
            "agents": ["voice"],
            "localShare": {
                "mountName": "docs",
                "permission": "read",
                "label": "Docs",
                "required": True,
            },
        }),
    })
    preview = service.preflight_plugin(
        payload, "demo.plugin.zip",
        actor_user_id="owner", workspace_id="workspace-a",
        audience=ExtensionAudience(agents=frozenset({AgentKind.VOICE})),
    )
    with pytest.raises(Exception, match="requires linking"):
        service.confirm_plugin(
            preview.token, actor_user_id="owner", workspace_id="workspace-a", replace=False,
        )
    assert not (tmp_path / "extensions" / "plugins" / "demo.plugin").exists()
