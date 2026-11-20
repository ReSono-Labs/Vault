from io import BytesIO
import json
from pathlib import Path
import zipfile

import pytest

from app.vault_runtime.extensions.archives import ArchiveInspector
from app.vault_runtime.extensions.filesystem import ExtensionFilesystem
from app.vault_runtime.extensions.models import ExtensionAudience, ExtensionKind, ExtensionState
from app.vault_runtime.extensions.preflight import PreflightError
from app.vault_runtime.extensions.repository import ExtensionRecord
from app.vault_runtime.extensions.service import ExtensionImportService
from app.vault_runtime.extensions.specification import MCP_SCHEMA_ID, PLUGIN_SCHEMA_ID
from app.vault_runtime.system_agents.inventory import AgentKind


def _zip(files: dict[str, str]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


class Repository:
    def __init__(self):
        self.records = {}

    def get(self, *, workspace_id, kind, identity, **_):
        return self.records.get((workspace_id, kind, identity))

    def install(self, *, actor_user_id, workspace_id, kind, identity, display_name, version, description, content_hash, configuration, components=()):
        key = (workspace_id, kind, identity)
        prior = self.records.get(key)
        record = ExtensionRecord(
            prior.extension_id if prior else identity, kind, identity, display_name, version,
            description, content_hash, ExtensionState.ENABLED, actor_user_id, workspace_id,
            prior.content_hash if prior else None, configuration,
        )
        self.records[key] = record
        return record


def _service(tmp_path: Path):
    repository = Repository()
    return ExtensionImportService(
        repository=repository, inspector=ArchiveInspector(tmp_path / "quarantine"),
        filesystem=ExtensionFilesystem(tmp_path / "extensions"),
    ), repository


def test_skill_preflight_confirm_and_explicit_replacement(tmp_path: Path) -> None:
    service, repository = _service(tmp_path)
    audience = ExtensionAudience(frozenset({AgentKind.VOICE}))
    payload = _zip({"demo/SKILL.md": "---\nname: demo\ndescription: Demo when requested.\n---\nFirst.\n"})
    preview = service.preflight_skill(payload, "demo.zip", actor_user_id="owner", workspace_id="workspace", audience=audience)
    installed = service.confirm_skill(preview.token, actor_user_id="owner", workspace_id="workspace", replace=False)
    assert installed.identity == "demo"
    updated = _zip({"demo/SKILL.md": "---\nname: demo\ndescription: Demo when requested.\n---\nSecond.\n"})
    preview = service.preflight_skill(updated, "demo.zip", actor_user_id="owner", workspace_id="workspace", audience=audience)
    with pytest.raises(PreflightError, match="replacement"):
        service.confirm_skill(preview.token, actor_user_id="owner", workspace_id="workspace", replace=False)
    preview = service.preflight_skill(updated, "demo.zip", actor_user_id="owner", workspace_id="workspace", audience=audience)
    replaced = service.confirm_skill(preview.token, actor_user_id="owner", workspace_id="workspace", replace=True)
    assert replaced.previous_content_hash == installed.content_hash
    assert (tmp_path / "extensions/skills/demo/current/SKILL.md").read_text() .endswith("Second.\n")


def test_plugin_preserves_valid_components_and_reports_invalid_components(tmp_path: Path) -> None:
    service, _repository = _service(tmp_path)
    manifest = json.dumps({"$schema": PLUGIN_SCHEMA_ID, "name": "local.demo", "version": "1.0"})
    valid = _zip({
        "local.demo/plugin.json": manifest,
        "local.demo/skills/helper/SKILL.md": "---\nname: helper\ndescription: Help when asked.\n---\nHelp.\n",
    })
    preview = service.preflight_plugin(valid, "plugin.zip", actor_user_id="owner", workspace_id="workspace", audience=ExtensionAudience(frozenset(AgentKind)))
    installed = service.confirm_plugin(preview.token, actor_user_id="owner", workspace_id="workspace", replace=False)
    assert installed.kind is ExtensionKind.PLUGIN
    partial = _zip({
        "local.partial/plugin.json": json.dumps({
            "$schema": PLUGIN_SCHEMA_ID, "name": "local.partial", "unknown": True,
        }),
        "local.partial/skills/helper/SKILL.md": "---\nname: helper\ndescription: Valid helper.\n---\nHelp.\n",
        "local.partial/skills/Bad/SKILL.md": "---\nname: Bad\ndescription: no\n---\nno",
        "local.partial/mcp.json": json.dumps({
            "$schema": MCP_SCHEMA_ID,
            "mcpServers": {
                "valid": {"type": "streamable-http", "url": "https://example.test/mcp"},
                "invalid": {"type": "unknown", "url": "https://example.test/mcp"},
            },
        }),
    })
    preview = service.preflight_plugin(
        partial, "partial.zip", actor_user_id="owner", workspace_id="workspace",
        audience=ExtensionAudience(frozenset(AgentKind)),
    )
    assert [item[0] for item in preview.payload.skills] == ["helper"]
    assert [item.name for item in preview.payload.mcp_servers] == ["valid"]
    assert any("unknown top-level field" in item for item in preview.payload.diagnostics)
    assert any("skill:Bad" in item for item in preview.payload.diagnostics)
    assert any("mcp:invalid" in item for item in preview.payload.diagnostics)
    assert not any(item.startswith("review:") for item in preview.payload.diagnostics)
    assert preview.payload.review is not None
    assert preview.payload.review.risk == "low"
    installed = service.confirm_plugin(
        preview.token, actor_user_id="owner", workspace_id="workspace", replace=False,
    )
    assert installed.identity == "local.partial"


def test_mcp_document_issues_one_confirmation_per_connection_and_grants_nothing(tmp_path: Path) -> None:
    service, repository = _service(tmp_path)
    payload = json.dumps({
        "$schema": MCP_SCHEMA_ID,
        "mcpServers": {
            "one": {"type": "streamable-http", "url": "https://one.example.test/mcp"},
            "two": {"type": "sse", "url": "https://two.example.test/sse"},
        },
    }).encode()
    previews = service.preflight_mcp(
        payload, actor_user_id="owner", workspace_id="workspace",
        audience=ExtensionAudience(frozenset({AgentKind.VOICE})),
    )
    assert {item.identity for item in previews} == {"one", "two"}
    installed = service.confirm_mcp(
        previews[0].token, actor_user_id="owner", workspace_id="workspace", replace=False,
    )
    assert installed.kind is ExtensionKind.MCP
    assert not hasattr(repository, "grants")
