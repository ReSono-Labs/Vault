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
from app.vault_runtime.extensions.skills import SkillSpecificationError
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
    # HTTP+SSE (2024-11-05) is skipped with a per-server reason; the sibling still imports.
    assert {item.identity for item in previews} == {"one"}
    assert previews[0].payload.diagnostics == (
        "mcp:two: unsupported transport sse; Vault connects only to streamable-http servers",)
    installed = service.confirm_mcp(
        previews[0].token, actor_user_id="owner", workspace_id="workspace", replace=False,
    )
    assert installed.kind is ExtensionKind.MCP
    assert not hasattr(repository, "grants")


def test_standalone_skill_import_rejects_names_the_old_fallback_accepted(tmp_path: Path) -> None:
    service, repository = _service(tmp_path)
    audience = ExtensionAudience(frozenset({AgentKind.VOICE}))
    for text, message in (
        ("---\ndescription: No name.\n---\nBody\n", "requires a name"),
        ("---\nname: Demo\ndescription: Upper case.\n---\nBody\n", "lowercase"),
        ("---\nname: other\ndescription: Mismatch.\n---\nBody\n", "must match the Skill directory 'demo'"),
    ):
        with pytest.raises(SkillSpecificationError, match=message):
            service.preflight_skill(_zip({"demo/SKILL.md": text}), "demo.zip",
                actor_user_id="owner", workspace_id="workspace", audience=audience)
    assert not repository.records
    assert not any((tmp_path / "quarantine").iterdir())


def test_plugin_import_skips_only_the_bad_skill_with_a_diagnostic(tmp_path: Path) -> None:
    service, _repository = _service(tmp_path)
    payload = _zip({
        "local.demo/plugin.json": json.dumps({"$schema": PLUGIN_SCHEMA_ID, "name": "local.demo"}),
        "local.demo/skills/healthy/SKILL.md": "---\nname: healthy\ndescription: Fine.\n---",
        "local.demo/skills/unnamed/SKILL.md": "---\ndescription: The old fallback named me.\n---\n",
        "local.demo/skills/twice/SKILL.md": "---\nname: twice\nname: twice\ndescription: Repeated.\n---\n",
    })
    preview = service.preflight_plugin(payload, "plugin.zip", actor_user_id="owner",
        workspace_id="workspace", audience=ExtensionAudience(frozenset(AgentKind)))
    assert [item[0] for item in preview.payload.skills] == ["healthy"]
    assert any(item.startswith("skill:unnamed:") and "name" in item for item in preview.payload.diagnostics)
    assert any(item.startswith("skill:twice:") and "repeats the key 'name'" in item for item in preview.payload.diagnostics)


_CONFIG = json.dumps({"$schema": "https://schemas.resonolabs.com/vault/plugin-config/v1.json",
    "fields": [{"key": "greeting", "type": "text", "label": "Greeting"}]})


class _ReconcilingRepository(Repository):
    def __init__(self):
        super().__init__()
        self.children = None

    def reconcile_managed_mcp(self, *, servers, **_):
        self.children = servers


def _plugin(files: dict[str, str], name: str = "local.demo", vault: dict | None = None) -> bytes:
    manifest = {"$schema": PLUGIN_SCHEMA_ID, "name": name}
    if vault is not None:
        manifest["extensions"] = {"com.resonolabs.vault": vault, "org.other.client": "any value"}
    return _zip({f"{name}/plugin.json": json.dumps(manifest), **{f"{name}/{key}": value for key, value in files.items()}})


def test_plugin_reads_vault_data_from_the_namespace_and_its_folder(tmp_path: Path) -> None:
    service, repository = _service(tmp_path)
    payload = _plugin({"com.resonolabs.vault/config.schema.json": _CONFIG},
                      vault={"minimumVaultVersion": "0.1.0", "agents": ["voice"], "configuration": "config.schema.json"})
    preview = service.preflight_plugin(payload, "plugin.zip", actor_user_id="owner", workspace_id="workspace",
                                       audience=ExtensionAudience(frozenset(AgentKind)))
    assert preview.payload.vault_manifest.source == "namespace"
    assert preview.payload.configuration_schema["fields"][0]["key"] == "greeting"
    assert preview.payload.diagnostics == ()
    installed = service.confirm_plugin(preview.token, actor_user_id="owner", workspace_id="workspace", replace=False)
    assert installed.configuration["vaultManifest"]["source"] == "namespace"


def test_namespace_wins_over_legacy_vault_json_without_merging(tmp_path: Path) -> None:
    service, _repository = _service(tmp_path)
    legacy = json.dumps({"$schema": "https://schemas.resonolabs.com/vault/plugin/v1.json",
                         "minimumVaultVersion": "0.1.0", "agents": ["background"], "services": ["context.locale"]})
    payload = _plugin({"vault.json": legacy}, vault={"minimumVaultVersion": "0.2.0", "agents": ["voice"]})
    preview = service.preflight_plugin(payload, "plugin.zip", actor_user_id="owner", workspace_id="workspace",
                                       audience=ExtensionAudience(frozenset(AgentKind)))
    manifest = preview.payload.vault_manifest
    assert (manifest.minimum_version, manifest.agents, manifest.services) == ("0.2.0", frozenset({AgentKind.VOICE}), ())
    assert preview.payload.diagnostics == (
        "vault.json ignored: plugin.json extensions.com.resonolabs.vault takes precedence",)


def test_legacy_vault_json_still_loads_and_is_labelled(tmp_path: Path) -> None:
    service, _repository = _service(tmp_path)
    legacy = json.dumps({"$schema": "https://schemas.resonolabs.com/vault/plugin/v1.json",
                         "minimumVaultVersion": "0.1.0", "agents": ["voice"], "configuration": "config.schema.json"})
    payload = _plugin({"vault.json": legacy, "config.schema.json": _CONFIG})
    preview = service.preflight_plugin(payload, "plugin.zip", actor_user_id="owner", workspace_id="workspace",
                                       audience=ExtensionAudience(frozenset(AgentKind)))
    assert preview.payload.vault_manifest.source == "vault.json"
    assert preview.payload.configuration_schema is not None
    installed = service.confirm_plugin(preview.token, actor_user_id="owner", workspace_id="workspace", replace=False)
    assert installed.configuration["vaultManifest"]["source"] == "vault.json"


def test_plugin_skips_unsupported_transports_and_bad_server_names_without_child_rows(tmp_path: Path) -> None:
    repository = _ReconcilingRepository()
    service = ExtensionImportService(
        repository=repository, inspector=ArchiveInspector(tmp_path / "quarantine"),
        filesystem=ExtensionFilesystem(tmp_path / "extensions"),
    )
    mcp = json.dumps({"$schema": MCP_SCHEMA_ID, "mcpServers": {
        "remote": {"type": "streamable-http", "url": "https://example.test/mcp", "headers": {"X-Tenant": "t"}},
        "cli": {"type": "stdio", "command": "server"},
        "legacy": {"type": "sse", "url": "https://example.test/sse"},
        "../other": {"type": "streamable-http", "url": "https://example.test/other"},
        "spaced": {"type": "streamable-http", "url": "https://example.test/x", "headers": {"Bad Name": "x"}},
    }})
    preview = service.preflight_plugin(_plugin({"mcp.json": mcp}), "plugin.zip", actor_user_id="owner",
        workspace_id="workspace", audience=ExtensionAudience(frozenset(AgentKind)))
    assert [item.name for item in preview.payload.mcp_servers] == ["remote"]
    diagnostics = preview.payload.diagnostics
    assert any(item.startswith("mcp:cli: unsupported transport stdio") for item in diagnostics)
    assert any(item.startswith("mcp:legacy: unsupported transport sse") for item in diagnostics)
    assert any(item.startswith("mcp:../other:") and "safe path segment" in item for item in diagnostics)
    assert any(item.startswith("mcp:spaced:") and "valid HTTP field name" in item for item in diagnostics)
    service.confirm_plugin(preview.token, actor_user_id="owner", workspace_id="workspace", replace=False)
    assert [(name, config["transport"], config["executable"]) for name, _hash, config in repository.children] == [
        ("remote", "streamable-http", True)]


def test_kit_starters_import_into_vault_without_diagnostics(tmp_path: Path) -> None:
    import importlib.util

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("vault_plugin_kit_cli_import", root / "plugin-kit/cli/vault_plugin.py")
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    for language in ("python", "typescript"):
        service, _repository = _service(tmp_path / language)
        archive = cli.package(root / "plugin-kit/starters" / language, tmp_path / f"{language}.zip")
        preview = service.preflight_plugin(archive.read_bytes(), archive.name, actor_user_id="owner",
            workspace_id="workspace", audience=ExtensionAudience(frozenset(AgentKind)))
        assert preview.payload.diagnostics == ()
        assert preview.payload.vault_manifest.source == "namespace"
        assert [item[0] for item in preview.payload.skills] == ["starter"]
        assert [item.name for item in preview.payload.mcp_servers] == ["starter"]
