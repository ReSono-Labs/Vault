from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.workspace_files.manager import WorkspaceFileManagerService
from app.vault_runtime.workspace_files.store import WorkspaceFilesystemStore
from app.vault_runtime.workspace_storage import WorkspaceStorage


def _principal(workspace_id: str = "workspace-1") -> LocalPrincipal:
    return LocalPrincipal(
        user_id="user-1",
        username="owner",
        display_name="Owner",
        experience_style="balanced",
        is_device_owner=True,
        session_id="session-1",
        workspace_id=workspace_id,
        expires_at=datetime.now(UTC),
    )


@pytest.fixture
def workspace_store(tmp_path: Path) -> tuple[WorkspaceStorage, WorkspaceFileManagerService]:
    storage = WorkspaceStorage(tmp_path / "private")
    storage.provision(user_id="user-1", workspace_id="workspace-1")
    store = WorkspaceFilesystemStore(storage)
    return storage, WorkspaceFileManagerService(store)


def test_provision_seeds_workspace_markdown(workspace_store: tuple[WorkspaceStorage, WorkspaceFileManagerService]) -> None:
    storage, _manager = workspace_store
    seed = storage.workspace_files_root("workspace-1") / "WORKSPACE.md"
    assert seed.is_file()
    assert "authorized files root" in seed.read_text(encoding="utf-8")


def test_write_read_and_list_files(workspace_store: tuple[WorkspaceStorage, WorkspaceFileManagerService]) -> None:
    _storage, manager = workspace_store
    actor = _principal()
    manager.write_text_file(
        actor=actor,
        file_key="notes/today.md",
        content_markdown="# Today",
        overwrite_existing=False,
    )
    listing = manager.list_directory(actor=actor, directory=None)
    paths = {entry.path for entry in listing.entries}
    assert "notes" in paths
    read = manager.read_file(actor=actor, file_key="notes/today.md")
    assert read.contentMarkdown == "# Today"


def test_upload_zip_is_allowed(workspace_store: tuple[WorkspaceStorage, WorkspaceFileManagerService]) -> None:
    from app.vault_runtime.workspace_files.manager import WorkspaceFileUpload

    _storage, manager = workspace_store
    actor = _principal()
    manager.upload_files(
        actor=actor,
        directory="archives",
        uploads=[WorkspaceFileUpload(filename="bundle.zip", content=b"PK\x03\x04")],
    )
    _, media_type, content = manager.read_file_bytes(actor=actor, file_key="archives/bundle.zip")
    assert media_type == "application/zip"
    assert content.startswith(b"PK")


def test_write_bytes_works_when_files_root_already_exists(
    workspace_store: tuple[WorkspaceStorage, WorkspaceFileManagerService],
) -> None:
    storage, _manager = workspace_store
    store = WorkspaceFilesystemStore(storage)
    entry = store.write_bytes(
        workspace_id="workspace-1",
        file_key="vault-import-root-test.md",
        content=b"imported",
    )
    assert entry.file_key == "vault-import-root-test.md"


def test_delete_folder_requires_recursive(workspace_store: tuple[WorkspaceStorage, WorkspaceFileManagerService]) -> None:
    from app.vault_runtime.workspace_files.errors import WorkspaceFileBadRequestError

    _storage, manager = workspace_store
    actor = _principal()
    manager.write_text_file(
        actor=actor,
        file_key="projects/a/readme.md",
        content_markdown="hello",
        overwrite_existing=False,
    )
    with pytest.raises(WorkspaceFileBadRequestError):
        manager.delete_path(actor=actor, payload={"path": "projects", "recursive": False})
    manager.delete_path(actor=actor, payload={"path": "projects", "recursive": True})
    listing = manager.list_directory(actor=actor, directory=None)
    assert all(entry.path != "projects" for entry in listing.entries)
