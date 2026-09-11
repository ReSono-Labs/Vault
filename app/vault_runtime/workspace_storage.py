"""Private user/workspace storage lifecycle for the packaged Vault."""

from __future__ import annotations

import json
import os
from pathlib import Path
import os
import shutil
from uuid import uuid4

from app.vault_runtime.workspace_files.constants import WORKSPACE_SEED_MARKDOWN


class WorkspaceStorageError(RuntimeError):
    code = "workspace_storage_error"


class WorkspaceStorage:
    """Creates private roots and independent key material for local identities."""

    def __init__(self, root: Path) -> None:
        self._root = root.expanduser().absolute()

    def ensure_root(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        if self._root.is_symlink():
            raise WorkspaceStorageError("Vault private storage root cannot be a symlink.")
        self._root.chmod(0o700)
        for name in ("users", "workspaces", ".provisioning", ".deleted"):
            path = self._root / name
            path.mkdir(mode=0o700, exist_ok=True)
            if path.is_symlink():
                raise WorkspaceStorageError("Vault private storage contains a symlinked boundary.")

    def provision(self, *, user_id: str, workspace_id: str) -> None:
        self.ensure_root()
        _identifier(user_id)
        _identifier(workspace_id)
        user_root = self._root / "users" / user_id
        workspace_root = self._root / "workspaces" / workspace_id
        if user_root.exists() or workspace_root.exists():
            raise WorkspaceStorageError("Vault private storage identity already exists.")
        staging = self._root / ".provisioning" / str(uuid4())
        try:
            staged_user, staged_workspace = staging / "user", staging / "workspace"
            _make_tree(staged_user, ("keys", "runtime", "tmp"))
            _make_tree(staged_workspace, ("files", "memory", "keys", "runtime", "tmp"))
            _seed_workspace_files(staged_workspace / "files")
            _write_key(staged_user / "keys/user.key")
            _write_key(staged_workspace / "keys/workspace.key")
            _write_metadata(staged_user / "identity.json", {"userId": user_id})
            _write_metadata(
                staged_workspace / "identity.json",
                {"workspaceId": workspace_id, "ownerUserId": user_id},
            )
            os.replace(staged_user, user_root)
            try:
                os.replace(staged_workspace, workspace_root)
            except Exception:
                shutil.rmtree(user_root)
                raise
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def provision_workspace(self, *, owner_user_id: str, workspace_id: str) -> None:
        self.ensure_root()
        _identifier(owner_user_id)
        _identifier(workspace_id)
        user_root = self._root / "users" / owner_user_id
        if not user_root.is_dir() or user_root.is_symlink():
            raise WorkspaceStorageError("Vault user storage is unavailable.")
        _verify_metadata(user_root / "identity.json", {"userId": owner_user_id})
        workspace_root = self._root / "workspaces" / workspace_id
        if workspace_root.exists():
            raise WorkspaceStorageError("Vault workspace storage already exists.")
        staging = self._root / ".provisioning" / str(uuid4())
        try:
            _make_tree(staging, ("files", "memory", "keys", "runtime", "tmp"))
            _seed_workspace_files(staging / "files")
            _write_key(staging / "keys/workspace.key")
            _write_metadata(
                staging / "identity.json",
                {"workspaceId": workspace_id, "ownerUserId": owner_user_id},
            )
            os.replace(staging, workspace_root)
        finally:
            if staging.exists():
                shutil.rmtree(staging)

    def reconcile_identity(self, *, user_id: str, workspace_id: str) -> None:
        """Recover a committed identity after interruption without replacing keys."""
        self.ensure_root()
        user_root = self.user_root(user_id)
        workspace_root = self.workspace_root(workspace_id)
        if not user_root.exists() and not workspace_root.exists():
            self.provision(user_id=user_id, workspace_id=workspace_id)
            return
        if not user_root.is_dir():
            raise WorkspaceStorageError("Vault user storage is inconsistent.")
        if user_root.is_symlink():
            raise WorkspaceStorageError("Vault user storage cannot be a symlink.")
        _verify_metadata(user_root / "identity.json", {"userId": user_id})
        if not workspace_root.exists():
            self.provision_workspace(owner_user_id=user_id, workspace_id=workspace_id)
            return
        if not workspace_root.is_dir():
            raise WorkspaceStorageError("Vault workspace storage is inconsistent.")
        if workspace_root.is_symlink():
            raise WorkspaceStorageError("Vault workspace storage cannot be a symlink.")
        _verify_metadata(
            workspace_root / "identity.json",
            {"workspaceId": workspace_id, "ownerUserId": user_id},
        )
        for key in (user_root / "keys/user.key", workspace_root / "keys/workspace.key"):
            if not key.is_file() or key.is_symlink() or key.stat().st_size != 32:
                raise WorkspaceStorageError("Vault private key boundary is inconsistent.")
        files_root = workspace_root / "files"
        files_root.mkdir(mode=0o700, exist_ok=True)
        _seed_workspace_files(files_root)

    def remove_user(self, *, user_id: str, owned_workspace_ids: tuple[str, ...]) -> None:
        self.ensure_root()
        targets = [self._root / "users" / _identifier(user_id)]
        targets.extend(self._root / "workspaces" / _identifier(value) for value in owned_workspace_ids)
        for target in targets:
            if not target.exists():
                continue
            if target.is_symlink() or not target.is_dir():
                raise WorkspaceStorageError("Vault private storage target is inconsistent.")
            tombstone = self._root / ".deleted" / f"{target.name}-{uuid4()}"
            os.replace(target, tombstone)
            shutil.rmtree(tombstone)

    def user_root(self, user_id: str) -> Path:
        return self._root / "users" / _identifier(user_id)

    def workspace_root(self, workspace_id: str) -> Path:
        return self._root / "workspaces" / _identifier(workspace_id)

    def workspace_files_root(self, workspace_id: str) -> Path:
        root = self.workspace_root(workspace_id) / "files"
        root.mkdir(mode=0o700, exist_ok=True)
        if root.is_symlink():
            raise WorkspaceStorageError("Vault workspace files root cannot be a symlink.")
        return root


def _identifier(value: str) -> str:
    if not value or value.strip() != value or "/" in value or "\\" in value or value in {".", ".."}:
        raise WorkspaceStorageError("Vault storage identity is invalid.")
    return value


def _make_tree(root: Path, children: tuple[str, ...]) -> None:
    root.mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    for child in children:
        path = root / child
        path.mkdir(mode=0o700)
        path.chmod(0o700)


def _write_key(path: Path) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as target:
        target.write(os.urandom(32))


def _seed_workspace_files(files_root: Path) -> None:
    files_root.mkdir(mode=0o700, exist_ok=True)
    seed_path = files_root / "WORKSPACE.md"
    if seed_path.exists():
        return
    descriptor = os.open(seed_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        target.write(WORKSPACE_SEED_MARKDOWN)


def _write_metadata(path: Path, value: dict[str, str]) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        json.dump(value, target, sort_keys=True, separators=(",", ":"))
        target.write("\n")


def _verify_metadata(path: Path, expected: dict[str, str]) -> None:
    if not path.is_file() or path.is_symlink():
        raise WorkspaceStorageError("Vault private storage identity metadata is unavailable.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkspaceStorageError("Vault private storage identity metadata is invalid.") from exc
    if value != expected:
        raise WorkspaceStorageError("Vault private storage identity does not match its scope.")
