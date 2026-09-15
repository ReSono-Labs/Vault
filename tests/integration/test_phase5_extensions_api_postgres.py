from __future__ import annotations

import base64
from io import BytesIO
import json
import os
from pathlib import Path
import zipfile

import psycopg
import pytest

from app.core.security.tokens import hash_token
from app.vault_runtime.extensions.archives import ArchiveInspector
from app.vault_runtime.extensions.filesystem import ExtensionFilesystem
from app.vault_runtime.extensions.repository import ExtensionRepository
from app.vault_runtime.extensions.secrets import ExtensionSecretStore, LocalMasterKey
from app.vault_runtime.extensions.service import ExtensionImportService
from app.vault_runtime.local_api.app import VaultLocalApiApp
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.local_identity.service import LocalIdentityService


class Health:
    def health(self):
        return {"database": "ok"}


def _zip(files: dict[str, str]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return output.getvalue()


@pytest.fixture()
def extension_api(tmp_path: Path):
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
    tokens = identities.bootstrap_owner(
        setup_credential="setup", username="owner", password="owner-password",
        display_name="Owner", experience_style="strict",
    )
    repository = ExtensionRepository(database_url=database_url)
    repository.ensure_schema()
    filesystem = ExtensionFilesystem(tmp_path / "extensions")
    imports = ExtensionImportService(
        repository=repository, inspector=ArchiveInspector(tmp_path / "extensions/quarantine"),
        filesystem=filesystem,
    )
    secrets = ExtensionSecretStore(
        repository=repository, master_key=LocalMasterKey(tmp_path / "extension.key"),
    )
    app = VaultLocalApiApp(
        store=Health(), token="unused", identity_service=identities,
        extension_imports=imports, extensions=repository, extension_secrets=secrets,
    )
    headers = {
        "Cookie": f"resono_refresh={tokens.session_token}; resono_csrf={tokens.csrf_token}",
        "X-ReSono-CSRF": tokens.csrf_token,
    }
    yield app, headers, tokens, repository
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")


def _post(app, path, value, headers):
    return app.handle(method="POST", target=path, headers=headers, body=json.dumps(value, separators=(",", ":")).encode())


def test_skill_preflight_confirm_list_grant_and_safe_mode(extension_api) -> None:
    app, headers, tokens, _repository = extension_api
    archive = _zip({"demo/SKILL.md": "---\nname: demo\ndescription: Demo when requested.\n---\nDo it.\n"})
    preview = _post(app, "/extensions/skills/preflight", {
        "filename": "demo.zip", "archiveBase64": base64.b64encode(archive).decode(),
        "audience": ["voice"],
    }, headers)
    assert preview.status_code == 200 and preview.payload["identity"] == "demo"
    confirmed = _post(app, "/extensions/confirm", {
        "kind": "skill", "token": preview.payload["token"], "replace": False,
    }, headers)
    assert confirmed.status_code == 201 and confirmed.payload["kind"] == "skill"
    extension_id = confirmed.payload["extensionId"]
    listed = app.handle(method="GET", target="/extensions", headers=headers)
    assert [item["identity"] for item in listed.payload["items"]] == ["demo"]
    granted = _post(app, f"/extensions/{extension_id}/grants", {
        "targetUserId": tokens.principal.user_id, "agentKind": "voice",
        "capabilityName": "", "enabled": True,
    }, headers)
    assert granted.payload == {"status": "grant_updated"}
    listed_grants = app.handle(method="GET", target=f"/extensions/{extension_id}/grants", headers=headers)
    assert listed_grants.status_code == 200
    assert listed_grants.payload["items"] == [{
        "capabilityName": "",
        "agentKind": "voice",
        "enabled": True,
        "effectClass": None,
    }]
    safe = _post(app, "/extensions/safe-mode", {"enabled": True}, headers)
    assert safe.payload == {"safeMode": True}
    runtime = app.handle(method="GET", target="/extensions/runtime", headers=headers)
    assert runtime.status_code == 200 and runtime.payload == {"safeMode": True}


def test_mcp_credentials_never_echo_and_invalid_agent_is_rejected(extension_api) -> None:
    app, headers, tokens, _repository = extension_api
    document = {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
        "mcpServers": {"demo": {"type": "streamable-http", "url": "https://example.test/mcp"}},
    }
    preview = _post(app, "/extensions/mcp/preflight", {
        "documentBase64": base64.b64encode(json.dumps(document).encode()).decode(),
        "audience": ["voice", "background"],
    }, headers)
    token = preview.payload["items"][0]["token"]
    confirmed = _post(app, "/extensions/confirm", {"kind": "mcp", "token": token, "replace": False}, headers)
    extension_id = confirmed.payload["extensionId"]
    credential = "Bearer must-not-echo"
    updated = _post(app, f"/extensions/{extension_id}/credentials", {
        "headers": {"Authorization": credential},
    }, headers)
    assert updated.payload == {"status": "credentials_updated"}
    assert credential not in json.dumps(updated.payload)
    assert credential not in json.dumps(app.handle(method="GET", target="/extensions", headers=headers).payload)
    invalid = _post(app, f"/extensions/{extension_id}/grants", {
        "targetUserId": tokens.principal.user_id, "agentKind": "build",
        "capabilityName": "tool", "enabled": True, "effectClass": "read",
    }, headers)
    assert invalid.status_code == 400


def test_plugin_preflight_reports_nonfatal_standard_diagnostics(extension_api) -> None:
    app, headers, _tokens, _repository = extension_api
    archive = _zip({
        "portable/plugin.json": json.dumps({
            "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
            "name": "portable", "futureField": True,
        }),
        "portable/skills/valid/SKILL.md": "---\nname: valid\ndescription: Valid portable Skill.\n---\nUse it.\n",
        "portable/skills/Bad/SKILL.md": "---\nname: Bad\ndescription: invalid\n---\nNo.\n",
        "portable/mcp.json": json.dumps({
            "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
            "mcpServers": {},
        }),
    })
    preview = _post(app, "/extensions/plugins/preflight", {
        "filename": "portable.zip", "archiveBase64": base64.b64encode(archive).decode(),
        "audience": ["voice"],
    }, headers)
    assert preview.status_code == 200
    assert preview.payload["identity"] == "portable"
    assert any("futureField" in item for item in preview.payload["diagnostics"])
    assert any("skill:Bad" in item for item in preview.payload["diagnostics"])


def test_extension_mutation_requires_csrf_and_strict_json(extension_api) -> None:
    app, headers, _tokens, _repository = extension_api
    without_csrf = dict(headers)
    without_csrf.pop("X-ReSono-CSRF")
    denied = _post(app, "/extensions/safe-mode", {"enabled": True}, without_csrf)
    assert denied.status_code == 403
    duplicate = app.handle(
        method="POST", target="/extensions/safe-mode", headers=headers,
        body=b'{"enabled":true,"enabled":false}',
    )
    assert duplicate.status_code == 400
