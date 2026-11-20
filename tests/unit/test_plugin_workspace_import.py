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
from app.vault_runtime.workspace_files.store import WorkspaceFilesystemStore
from app.vault_runtime.workspace_storage import WorkspaceStorage


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

    def install(self, *, actor_user_id, workspace_id, kind, identity, display_name, version, description, content_hash, configuration, components=()):
        key = (workspace_id, kind, identity)
        prior = self.records.get(key)
        record = ExtensionRecord(
            prior.extension_id if prior else f"{kind.value}-{identity}",
            kind, identity, display_name, version, description, content_hash,
            prior.state if prior else ExtensionState.ENABLED,
            actor_user_id, workspace_id,
            prior.content_hash if prior else None, configuration,
        )
        self.records[key] = record
        return record


def test_plugin_workspace_import_copies_into_vault_workspace(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "workspaces")
    storage.ensure_root()
    workspace_id = "workspace-a"
    storage.reconcile_identity(user_id="owner", workspace_id=workspace_id)
    store = WorkspaceFilesystemStore(storage)
    repository = Repository()
    service = ExtensionImportService(
        repository=repository,
        inspector=ArchiveInspector(tmp_path / "quarantine"),
        filesystem=ExtensionFilesystem(tmp_path / "extensions"),
        workspace_store=store,
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
            "workspaceImport": {
                "onConflict": "replace",
                "items": [{
                    "source": "workspace-import/note.md",
                    "target": "notes/demo.md",
                    "kind": "file",
                }],
            },
        }),
        "demo.plugin/workspace-import/note.md": "# Note\n",
    })
    preview = service.preflight_plugin(
        payload, "demo.plugin.zip",
        actor_user_id="owner", workspace_id=workspace_id,
        audience=ExtensionAudience(agents=frozenset({AgentKind.VOICE})),
    )
    assert preview.payload.workspace_import_assessment is not None
    assert preview.payload.workspace_import_assessment.declared
    record = service.confirm_plugin(
        preview.token, actor_user_id="owner", workspace_id=workspace_id, replace=False,
    )
    files_root = store.files_root(workspace_id=workspace_id)
    imported = files_root / "notes/demo.md"
    assert imported.is_file()
    assert imported.read_text(encoding="utf-8") == "# Note\n"
    status = record.configuration.get("workspaceImportStatus")
    assert isinstance(status, dict)
    assert status.get("notes/demo.md") == "imported"
