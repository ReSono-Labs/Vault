from __future__ import annotations

from pathlib import Path

import pytest

from app.vault_runtime.workspace_storage import WorkspaceStorage, WorkspaceStorageError


def test_provisions_private_user_workspace_and_independent_keys(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "private")
    storage.provision(user_id="user-1", workspace_id="workspace-1")

    user_root = storage.user_root("user-1")
    workspace_root = storage.workspace_root("workspace-1")
    assert {item.name for item in user_root.iterdir()} == {"identity.json", "keys", "runtime", "tmp"}
    assert {item.name for item in workspace_root.iterdir()} == {
        "identity.json", "files", "memory", "keys", "runtime", "tmp",
    }
    assert (workspace_root / "files/WORKSPACE.md").is_file()
    user_key = user_root / "keys/user.key"
    workspace_key = workspace_root / "keys/workspace.key"
    assert len(user_key.read_bytes()) == 32
    assert len(workspace_key.read_bytes()) == 32
    assert user_key.read_bytes() != workspace_key.read_bytes()
    assert user_key.stat().st_mode & 0o777 == 0o600
    assert workspace_root.stat().st_mode & 0o777 == 0o700


def test_user_removal_deletes_keys_and_owned_workspace(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "private")
    storage.provision(user_id="user-1", workspace_id="workspace-1")
    storage.provision_workspace(owner_user_id="user-1", workspace_id="workspace-2")

    storage.remove_user(
        user_id="user-1", owned_workspace_ids=("workspace-1", "workspace-2"),
    )

    assert not storage.user_root("user-1").exists()
    assert not storage.workspace_root("workspace-1").exists()
    assert not storage.workspace_root("workspace-2").exists()
    assert list((tmp_path / "private" / ".deleted").iterdir()) == []


def test_storage_rejects_symlinked_root(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    root = tmp_path / "private"
    root.symlink_to(target, target_is_directory=True)

    with pytest.raises(WorkspaceStorageError):
        WorkspaceStorage(root).ensure_root()


def test_second_provision_cannot_overwrite_identity(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "private")
    storage.provision(user_id="user-1", workspace_id="workspace-1")

    with pytest.raises(WorkspaceStorageError):
        storage.provision(user_id="user-1", workspace_id="workspace-2")


def test_reconcile_preserves_keys_and_recovers_additional_workspace(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "private")
    storage.provision(user_id="user-1", workspace_id="workspace-1")
    original = (storage.user_root("user-1") / "keys/user.key").read_bytes()

    storage.reconcile_identity(user_id="user-1", workspace_id="workspace-1")
    storage.reconcile_identity(user_id="user-1", workspace_id="workspace-2")

    assert (storage.user_root("user-1") / "keys/user.key").read_bytes() == original
    assert (storage.workspace_root("workspace-2") / "keys/workspace.key").is_file()


def test_reconcile_rejects_mismatched_workspace_identity(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "private")
    storage.provision(user_id="user-1", workspace_id="workspace-1")
    metadata = storage.workspace_root("workspace-1") / "identity.json"
    metadata.write_text(
        '{"ownerUserId":"user-2","workspaceId":"workspace-1"}\n',
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceStorageError):
        storage.reconcile_identity(user_id="user-1", workspace_id="workspace-1")


def test_additional_workspace_rejects_symlinked_user_root(tmp_path: Path) -> None:
    storage = WorkspaceStorage(tmp_path / "private")
    storage.ensure_root()
    outside = tmp_path / "outside"
    outside.mkdir()
    storage.user_root("user-1").symlink_to(outside, target_is_directory=True)

    with pytest.raises(WorkspaceStorageError):
        storage.provision_workspace(owner_user_id="user-1", workspace_id="workspace-1")
