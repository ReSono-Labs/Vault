from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.vault_runtime.extensions.filesystem import ExtensionFilesystem
from app.vault_runtime.extensions.models import ExtensionKind, ExtensionState
from app.vault_runtime.extensions.repository import ExtensionRecord
from app.vault_runtime.extensions.service import ExtensionImportService


@dataclass
class _Started:
    record: ExtensionRecord | None = None


class _Supervisor:
    def __init__(self) -> None:
        self.started: list[ExtensionRecord] = []

    def start(self, *, actor_user_id: str, workspace_id: str, record: ExtensionRecord):
        self.started.append(record)
        return object()


class _Repository:
    def __init__(self, record: ExtensionRecord) -> None:
        self._record = record

    def by_id(self, **kwargs) -> ExtensionRecord:
        return self._record


def test_start_supervised_if_enabled_starts_enabled_plugin(tmp_path: Path) -> None:
    record = ExtensionRecord(
        "plugin-1", ExtensionKind.PLUGIN, "demo.plugin", "demo.plugin", "1.0.0",
        "demo", "hash", ExtensionState.ENABLED, "owner", "workspace", None,
        {
            "supervised": True,
            "runtime": {
                "command": ["bash", "run.sh"],
                "cwd": "crm",
                "port": 8790,
                "healthPath": "/health",
            },
        },
    )
    supervisor = _Supervisor()
    service = ExtensionImportService(
        repository=_Repository(record),  # type: ignore[arg-type]
        filesystem=ExtensionFilesystem(tmp_path),
        inspector=object(),  # type: ignore[arg-type]
        mcp_runtime=supervisor,  # type: ignore[arg-type]
    )
    result = service._start_supervised_if_enabled(
        actor_user_id="owner", workspace_id="workspace", record=record,
    )
    assert result is record
    assert supervisor.started == [record]
