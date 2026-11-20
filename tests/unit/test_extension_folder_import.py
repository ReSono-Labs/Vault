"""Folder import goes through the same loader as archives and installs a confirmed snapshot."""
import json
import os
from pathlib import Path

import pytest

from app.vault_runtime.extensions.archives import ArchiveInspector, ArchiveRejected
from app.vault_runtime.extensions.filesystem import ExtensionFilesystem
from app.vault_runtime.extensions.models import ExtensionAudience
from app.vault_runtime.extensions.service import ExtensionImportService
from app.vault_runtime.extensions.specification import MCP_SCHEMA_ID, PLUGIN_SCHEMA_ID
from app.vault_runtime.system_agents.inventory import AgentKind
from tests.unit.test_extension_import_service import _ReconcilingRepository, _zip

AUDIENCE = ExtensionAudience(frozenset(AgentKind))
SKILL = "---\nname: {name}\ndescription: Does a thing.\n---\nBody for {name}.\n"
MIXED = {
    "plugin.json": json.dumps({"$schema": PLUGIN_SCHEMA_ID, "name": "local.mixed",
                               "extensions": {"org.other.client": {"anything": [1, 2]}}}),
    "skills/good-skill/SKILL.md": SKILL.format(name="good-skill"),
    "skills/Bad_Skill/SKILL.md": SKILL.format(name="Bad_Skill"),
    "mcp.json": json.dumps({"$schema": MCP_SCHEMA_ID, "mcpServers": {
        "remote": {"type": "streamable-http", "url": "https://example.test/mcp"},
        "cli": {"type": "stdio", "command": "server"}}}),
}


def _service(tmp_path: Path):
    repository = _ReconcilingRepository()
    return ExtensionImportService(repository=repository, inspector=ArchiveInspector(tmp_path / "quarantine"),
                                  filesystem=ExtensionFilesystem(tmp_path / "extensions")), repository


def _folder(root: Path, files: dict[str, str]) -> Path:
    for relative, text in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    return root


def _summary(preview):
    payload = preview.payload
    return (preview.identity, preview.candidate_hash, sorted(name for name, _doc, _hash in payload.skills),
            [server.name for server in payload.mcp_servers], sorted(payload.diagnostics))


def test_folder_and_archive_give_identical_components_and_diagnostics(tmp_path: Path) -> None:
    service, _repository = _service(tmp_path)
    archive = service.preflight_plugin(_zip({f"local.mixed/{k}": v for k, v in MIXED.items()}), "mixed.zip",
                                       actor_user_id="owner", workspace_id="workspace", audience=AUDIENCE)
    folder = service.preflight_folder(_folder(tmp_path / "src" / "local.mixed", MIXED), kind="plugin",
                                      actor_user_id="owner", workspace_id="workspace", audience=AUDIENCE)
    assert _summary(folder) == _summary(archive)
    identity, _hash, skills, servers, diagnostics = _summary(folder)
    assert skills == ["good-skill"] and servers == ["remote"]
    assert any(item.startswith("skill:Bad_Skill") for item in diagnostics)
    assert any(item.startswith("mcp:cli: unsupported transport stdio") for item in diagnostics)


def test_editing_the_folder_after_preflight_cannot_change_what_installs(tmp_path: Path) -> None:
    service, _repository = _service(tmp_path)
    source = _folder(tmp_path / "src" / "local.mixed", MIXED)
    preview = service.preflight_folder(source, kind="plugin", actor_user_id="owner",
                                       workspace_id="workspace", audience=AUDIENCE)
    (source / "skills" / "good-skill" / "SKILL.md").write_text(SKILL.format(name="good-skill") + "INJECTED\n")
    (source / "skills" / "new-skill").mkdir()
    (source / "skills" / "new-skill" / "SKILL.md").write_text(SKILL.format(name="new-skill"))
    service.confirm_plugin(preview.token, actor_user_id="owner", workspace_id="workspace", replace=False)
    installed = next((tmp_path / "extensions").rglob("good-skill/SKILL.md"))
    assert "INJECTED" not in installed.read_text()
    assert not list((tmp_path / "extensions").rglob("new-skill"))


def test_links_special_files_and_missing_manifests_are_refused(tmp_path: Path) -> None:
    inspector = ArchiveInspector(tmp_path / "quarantine")
    secret = tmp_path / "secret.txt"
    secret.write_text("private")
    linked = _folder(tmp_path / "linked" / "local.demo", {"plugin.json": "{}"})
    os.symlink(secret, linked / "leak.txt")
    with pytest.raises(ArchiveRejected, match="link"):
        inspector.inspect_directory(linked, required_root_file="plugin.json")
    folder_link = _folder(tmp_path / "dirlink" / "local.demo", {"plugin.json": "{}"})
    os.symlink(tmp_path, folder_link / "outside")
    with pytest.raises(ArchiveRejected, match="link"):
        inspector.inspect_directory(folder_link, required_root_file="plugin.json")
    os.symlink(_folder(tmp_path / "real" / "local.demo", {"plugin.json": "{}"}), tmp_path / "root-link")
    with pytest.raises(ArchiveRejected):
        inspector.inspect_directory(tmp_path / "root-link", required_root_file="plugin.json")
    with pytest.raises(ArchiveRejected, match="requires root plugin.json"):
        inspector.inspect_directory(_folder(tmp_path / "skill" / "x", {"SKILL.md": "x"}), required_root_file="plugin.json")
    assert list((tmp_path / "quarantine").iterdir()) == [] if (tmp_path / "quarantine").exists() else True


def test_version_control_and_cache_folders_are_left_out(tmp_path: Path) -> None:
    inspector = ArchiveInspector(tmp_path / "quarantine")
    source = _folder(tmp_path / "src" / "good-skill", {
        "SKILL.md": SKILL.format(name="good-skill"), ".git/config": "[core]", "__pycache__/x.pyc": "x",
        ".DS_Store": "x", "references/notes.md": "notes"})
    snapshot = inspector.inspect_directory(source, required_root_file="SKILL.md")
    try:
        assert snapshot.entries == ("good-skill/SKILL.md", "good-skill/references/notes.md")
    finally:
        snapshot.discard()


def test_the_folder_entry_point_is_limited_to_folders_the_person_was_given(tmp_path: Path) -> None:
    from app.vault_runtime.folders.errors import FolderOutsideAccessError, FolderUnavailableError
    from app.vault_runtime.folders.models import DeviceLocation
    from app.vault_runtime.folders.service import FolderService
    from tests.support.folders import MemoryFolderRepository, _principal

    home = tmp_path / "home"
    _folder(home / "projects" / "local.mixed", MIXED)
    _folder(home / "private", {"notes.txt": "x"})
    repository = MemoryFolderRepository({"member", "other"})
    folders = FolderService(repository=repository, locations=(DeviceLocation("home", "Home", home, "home"),))
    grant = repository.upsert_grant(user_id="member", location_id="home", relative_path="projects",
                                    max_permission="read", created_by="owner")
    member, other = _principal("member"), _principal("other")
    assert folders.resolve_access_path(principal=member, grant_id=grant.grant_id, path="local.mixed") == \
        (home / "projects" / "local.mixed").resolve()
    for path in ("../private", "/etc", "local.mixed/../../private"):
        with pytest.raises((FolderOutsideAccessError, FolderUnavailableError, ValueError)):
            folders.resolve_access_path(principal=member, grant_id=grant.grant_id, path=path)
    with pytest.raises(FolderUnavailableError):            # someone else's access
        folders.resolve_access_path(principal=other, grant_id=grant.grant_id, path="local.mixed")
