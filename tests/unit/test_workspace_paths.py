from pathlib import Path

import pytest

from app.vault_runtime.workspace_paths import (
    UnsafeWorkspacePathError,
    normalize_workspace_file_key,
    normalize_workspace_file_prefix,
    resolve_workspace_staging_path,
)


def test_workspace_file_key_allows_voice_donor_paths() -> None:
    assert normalize_workspace_file_key("signals/business/customer-plan/brief.md") == "signals/business/customer-plan/brief.md"
    assert normalize_workspace_file_prefix("signals/business") == "signals/business"
    assert normalize_workspace_file_key("signals/business/readme") == "signals/business/readme"


@pytest.mark.parametrize(
    "file_key",
    ["../secret.md", "/secret.md", "signals/../secret.md", "signals\\..\\secret.md", "", "~/.ssh/id_rsa"],
)
def test_workspace_file_key_rejects_voice_donor_unsafe_paths(file_key: str) -> None:
    with pytest.raises(UnsafeWorkspacePathError):
        normalize_workspace_file_key(file_key)


def test_workspace_staging_path_stays_beneath_root(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    assert resolve_workspace_staging_path(workspace_root=root, file_key="notes/today.md") == root / "notes" / "today.md"


def test_workspace_staging_rejects_symlinked_root(tmp_path: Path) -> None:
    real_root = tmp_path / "real"
    real_root.mkdir()
    linked_root = tmp_path / "linked"
    linked_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(UnsafeWorkspacePathError, match="root"):
        resolve_workspace_staging_path(workspace_root=linked_root, file_key="notes.md")


def test_workspace_staging_rejects_symlink_component(tmp_path: Path) -> None:
    root, outside = tmp_path / "workspace", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafeWorkspacePathError, match="symbolic"):
        resolve_workspace_staging_path(workspace_root=root, file_key="linked/secret.md")
