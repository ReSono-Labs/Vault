from io import BytesIO
import json
from pathlib import Path
import zipfile

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

    def get(self, *, workspace_id, kind, identity, **_):
        return self.records.get((workspace_id, kind, identity))

    def by_id(self, *, actor_user_id, workspace_id, extension_id, owner=False):
        for record in self.records.values():
            if record.extension_id == extension_id and record.workspace_id == workspace_id:
                return record
        raise KeyError(extension_id)

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

    def set_state(self, *, actor_user_id, workspace_id, extension_id, state):
        record = self.by_id(actor_user_id=actor_user_id, workspace_id=workspace_id, extension_id=extension_id)
        updated = ExtensionRecord(
            record.extension_id, record.kind, record.identity, record.display_name,
            record.version, record.description, record.content_hash, state,
            record.installed_by_user_id, record.workspace_id, record.previous_content_hash,
            record.configuration,
        )
        self.records[(workspace_id, record.kind, record.identity)] = updated
        return updated


def _plugin_files() -> dict[str, str]:
    return {
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
            "migration": {
                "workspace": {"source": "migration/workspace", "target": "workspace"},
            },
        }),
        "demo.plugin/migration/workspace/SKILLS.md": "# Skills\n",
    }


def test_plugin_import_hydrates_migration_and_removes_data(tmp_path: Path) -> None:
    root = tmp_path / "extensions"
    service = ExtensionImportService(
        repository=Repository(),
        inspector=ArchiveInspector(tmp_path / "quarantine"),
        filesystem=ExtensionFilesystem(root),
    )
    preview = service.preflight_plugin(
        _zip(_plugin_files()), "demo.plugin.zip",
        actor_user_id="owner", workspace_id="workspace",
        audience=ExtensionAudience(frozenset({AgentKind.VOICE})),
    )
    installed = service.confirm_plugin(
        preview.token, actor_user_id="owner", workspace_id="workspace", replace=False,
    )
    assert installed.kind is ExtensionKind.PLUGIN
    assert installed.configuration.get("packageData") is True
    assert installed.configuration.get("migrationStatus") == {"workspace": "imported"}
    assert (root / "plugins/demo.plugin/current/plugin.json").is_file()
    assert not (root / "plugins/demo.plugin/current/migration").exists()
    assert (root / "data/demo.plugin/workspace/SKILLS.md").is_file()

    removed = service.set_state(
        actor_user_id="owner", workspace_id="workspace",
        extension_id=installed.extension_id, state=ExtensionState.REMOVED,
    )
    assert removed.state is ExtensionState.REMOVED
    assert not (root / "plugins/demo.plugin").exists()
    assert not (root / "data/demo.plugin").exists()
