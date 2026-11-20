from __future__ import annotations

from pathlib import Path

import pytest

from app.vault_runtime.folders.errors import (
    DriveDisconnectedError,
    FolderAdminRequiredError,
    FolderHiddenPathError,
    FolderNameTakenError,
    FolderOutsideAccessError,
    FolderUnavailableError,
    FolderWriteNotAllowedError,
)
from app.vault_runtime.folders.models import DeviceLocation
from app.vault_runtime.folders.paths import normalize_relative, resolve_inside
from app.vault_runtime.folders.service import FolderService, normalize_folder_name, suggest_folder_name
from app.vault_runtime.workspace_files.local_operations import LocalFilesystemBridge
from app.vault_runtime.workspace_files.manager import WorkspaceFileUpload
from tests.support.folders import MemoryFolderRepository, _principal


@pytest.fixture
def home(tmp_path: Path) -> Path:
    root = tmp_path / "home"
    (root / "Documents" / "Projects" / "notes").mkdir(parents=True)
    (root / "Documents" / "Projects" / "plan.md").write_text("# Plan\nship it\n")
    (root / "Downloads").mkdir()
    (root / ".ssh").mkdir()
    (root / ".ssh" / "id_rsa").write_text("secret")
    (root / "Private").mkdir()
    return root


@pytest.fixture
def setup(home: Path, tmp_path: Path):
    drives = tmp_path / "media"
    (drives / "USB").mkdir(parents=True)
    repository = MemoryFolderRepository({"admin", "kid"})
    service = FolderService(
        repository=repository,
        locations=(
            DeviceLocation("home", "Home", home, "home"),
            DeviceLocation("media", "Drives", drives, "drives"),
        ),
        documents_folder="Documents",
    )
    return service, repository, _principal("admin", admin=True), _principal("kid")


# Paths


@pytest.mark.parametrize("value", ["../etc", "/etc", "~/x", "a/../b", "a//b", "a\\..\\b"])
def test_traversal_is_refused(value: str) -> None:
    with pytest.raises(FolderOutsideAccessError):
        normalize_relative(value)


@pytest.mark.parametrize("value", [".ssh", "Documents/.git", ".config/app"])
def test_hidden_segments_are_refused(value: str) -> None:
    with pytest.raises(FolderHiddenPathError):
        normalize_relative(value)


def test_symlinks_are_refused_at_every_level(home: Path) -> None:
    (home / "Escape").symlink_to("/etc")
    with pytest.raises(FolderOutsideAccessError):
        resolve_inside(home, "Escape")
    with pytest.raises(FolderOutsideAccessError):
        resolve_inside(home, "Escape/passwd")


def test_folder_names() -> None:
    assert normalize_folder_name("  My   Projects ") == "My Projects"
    with pytest.raises(Exception):
        normalize_folder_name("../x")
    assert suggest_folder_name("Tax / 2024") == "Tax - 2024"
    assert suggest_folder_name("...") == "Folder"


# Admin access


def test_only_the_admin_manages_access(setup) -> None:
    service, _repo, _admin, kid = setup
    with pytest.raises(FolderAdminRequiredError):
        service.admin_locations(principal=kid)
    with pytest.raises(FolderAdminRequiredError):
        service.give_access(principal=kid, user_id="kid", location_id="home", path="", max_permission="write")


def test_admin_places_and_browse_hide_hidden_folders(setup) -> None:
    service, _repo, admin, _kid = setup
    places = service.admin_locations(principal=admin)["places"]
    labels = [place["label"] for place in places]
    assert labels[:3] == ["Home", "Documents", "Downloads"]
    assert "USB" in labels
    listing = service.admin_browse(principal=admin, location_id="home", path="")
    assert [item["name"] for item in listing["directories"]] == ["Documents", "Downloads", "Private"]


def test_user_cannot_browse_above_their_access(setup) -> None:
    service, _repo, admin, kid = setup
    grant = service.give_access(principal=admin, user_id="kid", location_id="home",
                                path="Documents", max_permission="read")
    listing = service.browse(principal=kid, grant_id=grant["grantId"], path="")
    assert listing["breadcrumbs"] == [{"label": "Documents", "path": ""}]
    assert [item["name"] for item in listing["directories"]] == ["Projects"]
    with pytest.raises(FolderOutsideAccessError):
        service.browse(principal=kid, grant_id=grant["grantId"], path="..")
    with pytest.raises(FolderUnavailableError):
        service.browse(principal=admin, grant_id=grant["grantId"], path="")


# User folders


def test_write_is_capped_by_the_access_the_admin_gave(setup) -> None:
    service, _repo, admin, kid = setup
    grant = service.give_access(principal=admin, user_id="kid", location_id="home",
                                path="Documents", max_permission="read")
    with pytest.raises(FolderWriteNotAllowedError):
        service.add_folder(principal=kid, grant_id=grant["grantId"], path="Projects",
                           name="Projects", permission="write")
    with pytest.raises(FolderWriteNotAllowedError):
        service.add_folder(principal=kid, grant_id=grant["grantId"], path="", name="New",
                           permission="read", create=True)
    folder = service.add_folder(principal=kid, grant_id=grant["grantId"], path="Projects",
                                name="Projects", permission="read")
    assert folder["path"] == "local/Projects"
    assert folder["location"] == "Documents/Projects"
    assert folder["status"] == "ok"


def test_lowering_access_lowers_folders_and_removing_it_removes_them(setup) -> None:
    service, _repo, admin, kid = setup
    grant = service.give_access(principal=admin, user_id="kid", location_id="home",
                                path="Documents", max_permission="write")
    service.add_folder(principal=kid, grant_id=grant["grantId"], path="Projects",
                       name="Projects", permission="write")
    service.set_access_permission(principal=admin, grant_id=grant["grantId"], max_permission="read")
    assert service.list_folders(principal=kid)["folders"][0]["permission"] == "read"
    service.remove_access(principal=admin, grant_id=grant["grantId"])
    assert service.list_folders(principal=kid) == {"available": True, "hasAccess": False, "canAddAnywhere": False, "folders": []}


def test_make_a_new_folder_and_remove_keeps_files(setup, home: Path) -> None:
    service, _repo, admin, kid = setup
    grant = service.give_access(principal=admin, user_id="kid", location_id="home",
                                path="Documents", max_permission="write")
    folder = service.add_folder(principal=kid, grant_id=grant["grantId"], path="", name="School",
                                permission="write", create=True)
    assert (home / "Documents" / "School").is_dir()
    assert folder["createdByVault"] is True
    service.remove_folder(principal=kid, folder_id=folder["folderId"])
    assert (home / "Documents" / "School").is_dir()


def test_names_are_unique_per_user(setup) -> None:
    service, _repo, admin, kid = setup
    grant = service.give_access(principal=admin, user_id="kid", location_id="home",
                                path="", max_permission="read")
    service.add_folder(principal=kid, grant_id=grant["grantId"], path="Documents", name="Stuff", permission="read")
    with pytest.raises(FolderNameTakenError):
        service.add_folder(principal=kid, grant_id=grant["grantId"], path="Downloads", name="stuff",
                           permission="read")


def test_disconnected_drive_is_reported(setup, tmp_path: Path) -> None:
    service, _repo, admin, _kid = setup
    grant = service.give_access(principal=admin, user_id="admin", location_id="media",
                                path="USB", max_permission="read")
    service.add_folder(principal=admin, grant_id=grant["grantId"], path="", name="USB", permission="read")
    (tmp_path / "media" / "USB").rmdir()
    assert service.list_folders(principal=admin)["folders"][0]["status"] == "drive_disconnected"
    with pytest.raises(DriveDisconnectedError):
        service.resolve(principal=admin, view_path="local/USB")


# Setup wizard


def test_setup_vault_folder_is_idempotent(setup, home: Path) -> None:
    service, _repo, admin, _kid = setup
    first = service.setup_vault_folder(principal=admin)
    second = service.setup_vault_folder(principal=admin)
    assert (home / "Documents" / "ReSono Vault").is_dir()
    assert first["folderId"] == second["folderId"]
    assert first["permission"] == "write"


def test_setup_add_dedupes_names(setup) -> None:
    service, _repo, admin, _kid = setup
    service.setup_add(principal=admin, location_id="home", path="Documents/Projects", permission="read")
    second = service.setup_add(principal=admin, location_id="home", path="Documents/Projects/notes", permission="read")
    third = service.setup_add(principal=admin, location_id="media", path="USB", permission="read")
    assert second["name"] == "notes"
    assert third["name"] == "USB"


# Agents through local/{name}


def test_agents_read_and_write_through_local_paths(setup, home: Path) -> None:
    service, _repo, admin, kid = setup
    bridge = LocalFilesystemBridge(folders=service)
    grant = service.give_access(principal=admin, user_id="kid", location_id="home",
                                path="Documents", max_permission="write")
    service.add_folder(principal=kid, grant_id=grant["grantId"], path="Projects", name="Projects",
                       permission="write")

    root = bridge.list_root(principal=kid)
    assert [entry.path for entry in root.entries] == ["local/Projects"]
    listing = bridge.list_directory(principal=kid, view_path="local/Projects")
    assert {entry.path for entry in listing.entries} == {"local/Projects/notes", "local/Projects/plan.md"}
    assert listing.parentDirectory == "local"
    read_back = bridge.read_file(principal=kid, view_path="local/Projects/plan.md")
    assert "ship it" in read_back.contentMarkdown
    assert read_back.fileKey == "local/Projects/plan.md"

    bridge.write_text_file(principal=kid, view_path="local/Projects/notes/today.md", content_markdown="hi")
    written = home / "Documents" / "Projects" / "notes" / "today.md"
    assert written.read_text() == "hi"
    assert written.stat().st_mode & 0o044, "files Vault writes must be readable like normal user files"

    moved = bridge.move_path(principal=kid, source_path="local/Projects/notes/today.md",
                             destination_path="local/Projects/today.md")
    assert moved.destinationPath == "local/Projects/today.md"
    bridge.upload_files(principal=kid, view_path="local/Projects",
                        uploads=[WorkspaceFileUpload(filename="a.txt", content=b"x", mime_type="text/plain")])
    assert (home / "Documents" / "Projects" / "a.txt").exists()
    bridge.delete_path(principal=kid, view_path="local/Projects/a.txt", recursive=False)
    assert not (home / "Documents" / "Projects" / "a.txt").exists()
    with pytest.raises(FolderOutsideAccessError):
        bridge.delete_path(principal=kid, view_path="local/Projects", recursive=True)


def test_agents_cannot_write_view_only_folders(setup) -> None:
    service, _repo, admin, kid = setup
    bridge = LocalFilesystemBridge(folders=service)
    grant = service.give_access(principal=admin, user_id="kid", location_id="home",
                                path="Documents", max_permission="read")
    service.add_folder(principal=kid, grant_id=grant["grantId"], path="Projects", name="Projects",
                       permission="read")
    with pytest.raises(FolderWriteNotAllowedError):
        bridge.save_file(principal=kid, view_path="local/Projects/plan.md", content_markdown="x")
    assert bridge.read_file(principal=kid, view_path="local/Projects/plan.md").editable is False


def test_agents_cannot_reach_hidden_or_outside_paths(setup) -> None:
    service, _repo, admin, _kid = setup
    bridge = LocalFilesystemBridge(folders=service)
    grant = service.give_access(principal=admin, user_id="admin", location_id="home",
                                path="", max_permission="read")
    service.add_folder(principal=admin, grant_id=grant["grantId"], path="", name="Home", permission="read")
    with pytest.raises(FolderHiddenPathError):
        bridge.read_file(principal=admin, view_path="local/Home/.ssh/id_rsa")
    listing = bridge.list_directory(principal=admin, view_path="local/Home")
    assert all(not entry.name.startswith(".") for entry in listing.entries)
    with pytest.raises(Exception):
        bridge.read_file(principal=admin, view_path="local/Home/../../etc/passwd")


def test_access_changes_apply_on_the_next_request(setup, home: Path) -> None:
    service, _repo, admin, kid = setup
    bridge = LocalFilesystemBridge(folders=service)
    grant = service.give_access(principal=admin, user_id="kid", location_id="home",
                                path="Documents", max_permission="read")
    service.add_folder(principal=kid, grant_id=grant["grantId"], path="Projects", name="Projects",
                       permission="read")
    bridge.list_directory(principal=kid, view_path="local/Projects")

    # A folder swapped for a symlink after it was added is refused.
    target = home / "Documents" / "Projects"
    target.rename(home / "Documents" / "Projects-real")
    target.symlink_to(home / "Private")
    with pytest.raises(FolderOutsideAccessError):
        bridge.list_directory(principal=kid, view_path="local/Projects")

    service.remove_access(principal=admin, grant_id=grant["grantId"])
    with pytest.raises(FolderUnavailableError):
        bridge.list_directory(principal=kid, view_path="local/Projects")


def test_other_users_folders_are_invisible(setup) -> None:
    service, _repo, admin, kid = setup
    grant = service.give_access(principal=admin, user_id="admin", location_id="home",
                                path="Private", max_permission="write")
    service.add_folder(principal=admin, grant_id=grant["grantId"], path="", name="Private", permission="write")
    with pytest.raises(FolderUnavailableError):
        service.resolve(principal=kid, view_path="local/Private")
    assert service.agent_descriptors(principal=kid) == []


# Master account


def test_admin_adds_any_folder_directly_and_removing_it_cleans_up(setup, home: Path) -> None:
    service, repo, admin, kid = setup
    state = service.list_folders(principal=admin)
    assert state["hasAccess"] is True and state["canAddAnywhere"] is True
    assert service.list_folders(principal=kid)["canAddAnywhere"] is False

    folder = service.admin_add_folder(principal=admin, location_id="home", path="Documents/Projects",
                                      name="Projects", permission="write")
    assert folder["path"] == "local/Projects" and folder["permission"] == "write"
    made = service.admin_add_folder(principal=admin, location_id="home", path="Documents", name="Taxes",
                                    permission="read", create=True, new_folder_name="Taxes")
    assert (home / "Documents" / "Taxes").is_dir() and made["createdByVault"] is True

    service.remove_folder(principal=admin, folder_id=folder["folderId"])
    service.remove_folder(principal=admin, folder_id=made["folderId"])
    assert repo.list_grants(user_id="admin") == []
    assert (home / "Documents" / "Taxes").is_dir(), "Remove never deletes files"


def test_only_the_admin_can_add_any_folder(setup) -> None:
    service, _repo, _admin, kid = setup
    with pytest.raises(FolderAdminRequiredError):
        service.admin_add_folder(principal=kid, location_id="home", path="", name="Home", permission="read")


# Hidden files


def _projects(home: Path) -> None:
    (home / "Documents" / "Projects" / ".github").mkdir()
    (home / "Documents" / "Projects" / ".github" / "ci.yml").write_text("on: push\n")
    (home / "Documents" / "Projects" / "notes" / ".draft.md").write_text("draft")


def test_hidden_files_stay_hidden_unless_the_admin_switches_them_on(setup, home: Path) -> None:
    _projects(home)
    service, _repo, admin, kid = setup
    bridge = LocalFilesystemBridge(folders=service)
    grant = service.give_access(principal=admin, user_id="kid", location_id="home",
                                path="Documents", max_permission="read")
    service.add_folder(principal=kid, grant_id=grant["grantId"], path="Projects", name="Projects", permission="read")
    names = {entry.name for entry in bridge.list_directory(principal=kid, view_path="local/Projects").entries}
    assert ".github" not in names
    with pytest.raises(FolderHiddenPathError):
        bridge.read_file(principal=kid, view_path="local/Projects/.github/ci.yml")

    service.set_access_hidden(principal=admin, grant_id=grant["grantId"], include_hidden=True)
    # Inherits downward: the folder, its subfolders and the picker all show hidden entries.
    names = {entry.name for entry in bridge.list_directory(principal=kid, view_path="local/Projects").entries}
    assert ".github" in names
    assert "on: push" in bridge.read_file(principal=kid, view_path="local/Projects/.github/ci.yml").contentMarkdown
    nested = {entry.name for entry in bridge.list_directory(principal=kid, view_path="local/Projects/notes").entries}
    assert ".draft.md" in nested
    assert ".github" in [d["name"] for d in service.browse(principal=kid, grant_id=grant["grantId"], path="Projects")["directories"]]
    assert service.list_folders(principal=kid)["folders"][0]["includeHidden"] is True

    service.set_access_hidden(principal=admin, grant_id=grant["grantId"], include_hidden=False)
    with pytest.raises(FolderHiddenPathError):
        bridge.read_file(principal=kid, view_path="local/Projects/.github/ci.yml")


def test_people_cannot_switch_hidden_files_on_folders_they_did_not_make(setup, home: Path) -> None:
    _projects(home)
    service, _repo, admin, kid = setup
    grant = service.give_access(principal=admin, user_id="kid", location_id="home",
                                path="Documents", max_permission="write")
    existing = service.add_folder(principal=kid, grant_id=grant["grantId"], path="Projects", name="Projects",
                                  permission="read")
    assert existing["canChangeHidden"] is False
    with pytest.raises(FolderAdminRequiredError):
        service.set_folder_hidden(principal=kid, folder_id=existing["folderId"], include_hidden=True)
    with pytest.raises(FolderAdminRequiredError):
        service.set_access_hidden(principal=kid, grant_id=grant["grantId"], include_hidden=True)
    with pytest.raises(FolderAdminRequiredError):
        service.add_folder(principal=kid, grant_id=grant["grantId"], path="Projects/notes", name="Notes",
                           permission="read", include_hidden=True)


def test_people_can_switch_hidden_files_on_folders_they_made(setup, home: Path) -> None:
    service, _repo, admin, kid = setup
    bridge = LocalFilesystemBridge(folders=service)
    grant = service.give_access(principal=admin, user_id="kid", location_id="home",
                                path="Documents", max_permission="write")
    made = service.add_folder(principal=kid, grant_id=grant["grantId"], path="", name="Code",
                              permission="write", create=True)
    assert made["canChangeHidden"] is True and made["includeHidden"] is False
    (home / "Documents" / "Code" / "app" / ".config").mkdir(parents=True)
    (home / "Documents" / "Code" / "app" / ".config" / "settings.json").write_text("{}")
    with pytest.raises(FolderHiddenPathError):
        bridge.read_file(principal=kid, view_path="local/Code/app/.config/settings.json")
    updated = service.set_folder_hidden(principal=kid, folder_id=made["folderId"], include_hidden=True)
    assert updated["includeHidden"] is True and updated["hiddenFromAccess"] is False
    assert bridge.read_file(principal=kid, view_path="local/Code/app/.config/settings.json").contentMarkdown == "{}"
    bridge.write_text_file(principal=kid, view_path="local/Code/.gitignore", content_markdown="dist\n")
    assert (home / "Documents" / "Code" / ".gitignore").read_text() == "dist\n"
    # Making a folder with hidden files on from the start is also allowed.
    started = service.add_folder(principal=kid, grant_id=grant["grantId"], path="", name="Dotfiles",
                                 permission="read", create=True, include_hidden=True)
    assert started["includeHidden"] is True


def test_symlinks_stay_blocked_with_hidden_files_on(setup, home: Path) -> None:
    service, _repo, admin, _kid = setup
    bridge = LocalFilesystemBridge(folders=service)
    (home / "Private" / ".link").symlink_to("/etc")
    folder = service.admin_add_folder(principal=admin, location_id="home", path="Private", name="Private",
                                      permission="read", include_hidden=True)
    assert folder["includeHidden"] is True
    assert ".link" not in {e.name for e in bridge.list_directory(principal=admin, view_path="local/Private").entries}
    with pytest.raises(FolderOutsideAccessError):
        bridge.read_file(principal=admin, view_path="local/Private/.link/passwd")


# Search


def test_search_finds_folders_by_name_and_skips_dependency_folders(setup, home: Path) -> None:
    from app.vault_runtime.workspace_files.repository import WorkspaceFileRepository
    from app.vault_runtime.workspace_files.service import WorkspaceFileService
    from app.vault_runtime.workspace_storage import WorkspaceStorage

    service, _repo, admin, _kid = setup
    root = home / "Documents" / "Projects"
    (root / "ReSono-Labs-Link" / "docs").mkdir(parents=True)
    (root / "ReSono-Labs-Link" / "docs" / "intro.md").write_text("About the Link platform\n")
    (root / "app" / "node_modules" / "resono-link-pkg").mkdir(parents=True)
    (root / "app" / "node_modules" / "resono-link-pkg" / "index.js").write_text("resono link")
    service.admin_add_folder(principal=admin, location_id="home", path="Documents/Projects", name="Projects",
                             permission="read")

    class NoShares:
        def list_shares_for_grantee(self, **_kwargs):
            return []

    storage = WorkspaceStorage(home.parent / "vault-private")
    storage.ensure_root()
    storage.ensure_workspace(admin.workspace_id) if hasattr(storage, "ensure_workspace") else None
    files = WorkspaceFileService(NoShares(), storage, folders=service)  # type: ignore[arg-type]
    result = files.search_files(principal=admin, query="resono-labs-link", directory="local/Projects")
    assert result["matches"][0]["fileKey"] == "local/Projects/ReSono-Labs-Link"
    assert result["matches"][0]["kind"] == "directory"
    assert result["truncated"] is False

    content = files.search_files(principal=admin, query="link platform", directory="local/Projects")
    assert [m["fileKey"] for m in content["matches"]] == ["local/Projects/ReSono-Labs-Link/docs/intro.md"]
    assert "Link platform" in content["matches"][0]["snippet"]

    deps = files.search_files(principal=admin, query="index.js", directory="local/Projects")
    assert deps["matches"] == [], "node_modules is matched by name only, never walked into"


def test_workspace_root_counts_added_folders_and_shares(setup, home: Path) -> None:
    from app.vault_runtime.workspace_files.service import WorkspaceFileService
    from app.vault_runtime.workspace_storage import WorkspaceStorage

    service, _repo, admin, _kid = setup
    (home / "Documents" / "Projects").mkdir(parents=True, exist_ok=True)
    service.admin_add_folder(principal=admin, location_id="home", path="Documents/Projects", name="Projects",
                             permission="read")

    class NoShares:
        def list_shares_for_grantee(self, **_kwargs):
            return []

    storage = WorkspaceStorage(home.parent / "vault-private")
    storage.provision(user_id=admin.user_id, workspace_id=admin.workspace_id)
    files = WorkspaceFileService(NoShares(), storage, folders=service)  # type: ignore[arg-type]
    root = {entry.path: entry for entry in files.list_directory(principal=admin, directory=None).entries}
    assert root["local"].childCount == 1 and root["local"].linked is True
    assert root["shared"].childCount == 0
