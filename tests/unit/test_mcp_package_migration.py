from io import BytesIO
import json
import sqlite3
from pathlib import Path
import zipfile

import pytest

from app.vault_runtime.extensions.archives import ArchiveInspector
from app.vault_runtime.extensions.filesystem import ExtensionFilesystem
from app.vault_runtime.extensions.models import ExtensionAudience, ExtensionKind, ExtensionState
from app.vault_runtime.extensions.repository import ExtensionRecord
from app.vault_runtime.extensions.service import ExtensionImportService
from app.vault_runtime.system_agents.inventory import AgentKind


def _zip(files: dict[str, bytes | str]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in files.items():
            payload = value if isinstance(value, bytes) else value.encode("utf-8")
            archive.writestr(name, payload)
    return output.getvalue()


def _sqlite_bytes() -> bytes:
    path = Path("/tmp/resono-migration-test.db")
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE demo (id INTEGER PRIMARY KEY, label TEXT)")
    connection.commit()
    connection.close()
    data = path.read_bytes()
    path.unlink()
    return data


class Repository:
    def __init__(self) -> None:
        self.records: dict[tuple[str, ExtensionKind, str], ExtensionRecord] = {}
        self.events: list[tuple[str, str, dict[str, object]]] = []

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

    def record_event(self, *, actor_user_id, workspace_id, extension_id, event_type, detail):
        self.events.append((extension_id, event_type, detail))


def _manifest(**overrides: object) -> str:
    payload = {
        "$schema": "https://schemas.resonolabs.com/vault/mcp-package/v1.json",
        "name": "resono.business",
        "version": "0.1.0",
        "configuration": "config.schema.json",
        "runtime": {
            "type": "process",
            "command": ["python3", "server.py"],
            "cwd": ".",
            "port": 8791,
            "healthPath": "/health",
            "mcpPath": "/mcp",
        },
        "migration": {
            "database": {"source": "migration/resono.db", "target": "resono.db"},
            "workspace": {"source": "migration/workspace", "target": "workspace"},
            "onConflict": "ask",
        },
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_mcp_package_migration_hydrates_data_and_excludes_from_code(tmp_path: Path) -> None:
    service = ExtensionImportService(
        repository=Repository(),
        inspector=ArchiveInspector(tmp_path / "quarantine"),
        filesystem=ExtensionFilesystem(tmp_path / "extensions"),
    )
    files = {
        "resono.business/mcp.package.json": _manifest(),
        "resono.business/config.schema.json": json.dumps({
            "$schema": "https://schemas.resonolabs.com/vault/plugin-config/v1.json",
            "fields": [],
        }),
        "resono.business/server.py": "print('mcp')\n",
        "resono.business/migration/resono.db": _sqlite_bytes(),
        "resono.business/migration/workspace/SKILLS.md": "# Skills\n",
    }
    preview = service.preflight_mcp_package(
        _zip(files), "resono.business.zip",
        actor_user_id="owner", workspace_id="workspace",
        audience=ExtensionAudience(frozenset({AgentKind.VOICE})),
    )
    assert preview.payload.migration_assessment is not None
    assert preview.payload.migration_assessment.requires_decision is False
    installed = service.confirm_mcp_package(
        preview.token, actor_user_id="owner", workspace_id="workspace",
        replace=False, replace_migration=False,
    )
    data_dir = tmp_path / "extensions/data/resono.business"
    assert (data_dir / "resono.db").is_file()
    assert (data_dir / "workspace/SKILLS.md").is_file()
    assert not (tmp_path / "extensions/mcps/resono.business/current/migration").exists()
    assert installed.configuration["migrationStatus"] == {
        "database": "imported",
        "workspace": "imported",
    }


def test_mcp_package_migration_conflict_requires_confirmation(tmp_path: Path) -> None:
    service = ExtensionImportService(
        repository=Repository(),
        inspector=ArchiveInspector(tmp_path / "quarantine"),
        filesystem=ExtensionFilesystem(tmp_path / "extensions"),
    )
    data_dir = tmp_path / "extensions/data/resono.business"
    data_dir.mkdir(parents=True)
    (data_dir / "resono.db").write_bytes(_sqlite_bytes())
    files = {
        "resono.business/mcp.package.json": _manifest(migration={
            "database": {"source": "migration/resono.db", "target": "resono.db"},
            "onConflict": "ask",
        }),
        "resono.business/config.schema.json": json.dumps({
            "$schema": "https://schemas.resonolabs.com/vault/plugin-config/v1.json",
            "fields": [],
        }),
        "resono.business/server.py": "print('mcp')\n",
        "resono.business/migration/resono.db": _sqlite_bytes(),
    }
    preview = service.preflight_mcp_package(
        _zip(files), "resono.business.zip",
        actor_user_id="owner", workspace_id="workspace",
        audience=ExtensionAudience(frozenset({AgentKind.VOICE})),
    )
    assert preview.payload.migration_assessment is not None
    assert preview.payload.migration_assessment.requires_decision is True
