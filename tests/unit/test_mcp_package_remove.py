from io import BytesIO
import json
from pathlib import Path
import zipfile

from app.vault_runtime.extensions.archives import ArchiveInspector
from app.vault_runtime.extensions.filesystem import ExtensionFilesystem
from app.vault_runtime.extensions.models import ExtensionAudience, ExtensionKind, ExtensionState
from app.vault_runtime.extensions.repository import ExtensionRecord
from app.vault_runtime.extensions.service import ExtensionImportService
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

    def update_configuration(self, *, actor_user_id, workspace_id, extension_id, configuration):
        record = self.by_id(actor_user_id=actor_user_id, workspace_id=workspace_id, extension_id=extension_id)
        updated = ExtensionRecord(
            record.extension_id, record.kind, record.identity, record.display_name,
            record.version, record.description, record.content_hash, record.state,
            record.installed_by_user_id, record.workspace_id, record.previous_content_hash,
            configuration,
        )
        self.records[(workspace_id, record.kind, record.identity)] = updated
        return updated


def _starter_files() -> dict[str, str]:
    manifest = json.dumps({
        "$schema": "https://schemas.resonolabs.com/vault/mcp-package/v1.json",
        "name": "starter.example",
        "version": "0.1.0",
        "configuration": "config.schema.json",
        "runtime": {
            "type": "process",
            "command": ["python3", "server.py"],
            "cwd": ".",
            "port": 8788,
            "healthPath": "/health",
            "mcpPath": "/mcp",
        },
        "companionPlugin": {"directory": "plugin", "removeWithPackage": True},
    })
    config = json.dumps({
        "$schema": "https://schemas.resonolabs.com/vault/plugin-config/v1.json",
        "fields": [{"key": "greeting", "type": "text", "label": "Greeting", "default": "Hello"}],
    })
    plugin = json.dumps({
        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        "name": "starter.example.ui",
        "version": "0.1.0",
        "description": "Companion plugin",
        "license": "Apache-2.0",
    })
    return {
        "starter.example/mcp.package.json": manifest,
        "starter.example/config.schema.json": config,
        "starter.example/server.py": "print('mcp')\n",
        "starter.example/plugin/plugin.json": plugin,
        "starter.example/plugin/vault.json": json.dumps({
            "$schema": "https://schemas.resonolabs.com/vault/plugin/v1.json",
            "minimumVaultVersion": "0.1.0",
            "agents": ["voice", "background"],
        }),
    }


def test_mcp_package_remove_cleans_hosted_files_and_companion(tmp_path: Path) -> None:
    root = tmp_path / "extensions"
    service = ExtensionImportService(
        repository=Repository(),
        inspector=ArchiveInspector(tmp_path / "quarantine"),
        filesystem=ExtensionFilesystem(root),
    )
    preview = service.preflight_mcp_package(
        _zip(_starter_files()), "starter.zip",
        actor_user_id="owner", workspace_id="workspace",
        audience=ExtensionAudience(frozenset({AgentKind.VOICE})),
    )
    installed = service.confirm_mcp_package(
        preview.token, actor_user_id="owner", workspace_id="workspace", replace=False,
    )
    companion_id = installed.configuration["companionPluginId"]
    assert isinstance(companion_id, str)
    data_dir = root / "data" / installed.identity
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "demo.sqlite").write_text("demo", encoding="utf-8")

    removed = service.set_state(
        actor_user_id="owner", workspace_id="workspace",
        extension_id=installed.extension_id, state=ExtensionState.REMOVED,
    )
    assert removed.state is ExtensionState.REMOVED
    assert not (root / "mcps" / installed.identity).exists()
    assert not (root / "data" / installed.identity).exists()

    companion = service._repository.by_id(
        actor_user_id="owner", workspace_id="workspace", extension_id=companion_id,
    )
    assert companion.state is ExtensionState.REMOVED
    assert not (root / "plugins" / companion.identity).exists()
