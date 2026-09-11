from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from app.vault_runtime.extensions.models import ExtensionKind, ExtensionState
from app.vault_runtime.extensions.plugin_services import PluginCapabilityError, PluginVaultServices
from app.vault_runtime.extensions.repository import ExtensionRecord
from app.vault_runtime.extensions.secrets import LocalMasterKey


class Repository:
    def __init__(self, plugin: ExtensionRecord) -> None:
        self.plugin = plugin
        self.activity: list[str] = []

    def by_id(self, **_):
        return self.plugin

    def record_plugin_activity(self, *, message, **_):
        self.activity.append(message)


class Memories:
    def append_transcript(self, **_):
        return None


class MemoryService:
    def search(self, **_):
        return ()


@dataclass
class Finalized:
    memory_count: int = 0
    already_completed: bool = False


def _record(kind: ExtensionKind, identity: str, configuration: dict[str, object]) -> ExtensionRecord:
    return ExtensionRecord(identity, kind, identity, identity, "0.1.0", None, "hash", ExtensionState.ENABLED, "user", "workspace", None, configuration)


def test_capability_is_invocation_and_service_bound(tmp_path: Path) -> None:
    plugin = _record(ExtensionKind.PLUGIN, "plugin", {"vaultManifest": {"services": ["memory.search", "activity.report"]}})
    repository = Repository(plugin)
    services = PluginVaultServices(
        repository=repository, key=LocalMasterKey(tmp_path / "key"), memories=Memories(),
        memory_service=MemoryService(), finalize=lambda *_: Finalized(), service_url="http://127.0.0.1:8766/plugin-services/v1",
    )
    connection = _record(ExtensionKind.MCP, "connection", {"managedByPluginId": "plugin"})
    token = services.issue_for_connection(connection=connection, user_id="user", workspace_id="workspace", invocation_id="call-1")
    assert token
    status, result = services.call(token=token, invocation_id="call-1", service="memory.search", payload={"query": "test"})
    assert status == 200 and result == {"items": []}
    with pytest.raises(PluginCapabilityError):
        services.call(token=token, invocation_id="call-2", service="memory.search", payload={"query": "test"})
    with pytest.raises(PluginCapabilityError):
        services.call(token=token, invocation_id="call-1", service="memory.propose", payload={"text": "test"})
