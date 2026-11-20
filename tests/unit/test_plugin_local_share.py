from datetime import UTC, datetime

import pytest

from app.vault_runtime.extensions.plugin_package_contract import parse_local_share_block
from app.vault_runtime.extensions.service import ExtensionImportService, LocalShareRegistration
from app.vault_runtime.folders.models import UserFolder
from app.vault_runtime.local_identity.models import LocalPrincipal


def test_parse_local_share_accepts_read_and_write_permissions() -> None:
    read_manifest = parse_local_share_block({
        "mountName": "docs",
        "permission": "read",
        "label": "Docs",
    })
    write_manifest = parse_local_share_block({
        "mountName": "docs",
        "permission": "write",
        "label": "Docs",
        "required": True,
    })
    assert read_manifest.permission == "read"
    assert write_manifest.permission == "write"
    assert write_manifest.required is True


def _principal() -> LocalPrincipal:
    return LocalPrincipal(
        user_id="owner", username="owner", display_name="Owner", experience_style="balanced",
        is_device_owner=True, session_id="s", workspace_id="workspace", expires_at=datetime.now(UTC),
    )


class _Folders:
    def __init__(self, folder: UserFolder | None) -> None:
        self.folder = folder

    def get_folder(self, *, principal: LocalPrincipal, folder_id: str) -> UserFolder | None:
        return self.folder if self.folder and self.folder.folder_id == folder_id else None


def _folder(permission: str) -> UserFolder:
    return UserFolder(
        folder_id="f1", user_id="owner", grant_id="g1", relative_path="", name="Docs",
        permission=permission, created_vault=False, created_at=datetime.now(UTC),
    )


def _service(folder: UserFolder | None) -> ExtensionImportService:
    return ExtensionImportService(
        repository=object(), inspector=object(), filesystem=object(), folders=_Folders(folder),
    )


def _manifest(permission: str):
    return parse_local_share_block({
        "mountName": "docs", "permission": permission, "label": "Docs", "required": True,
    })


def test_resolve_local_share_uses_the_users_folder() -> None:
    result = _service(_folder("read"))._resolve_local_share_registration(
        principal=_principal(), share_manifest=_manifest("read"),
        registration=LocalShareRegistration(folder_id="f1"),
    )
    assert result == {
        "folderId": "f1", "mountName": "Docs", "permission": "read",
        "label": "Docs", "pathPrefix": "local/Docs",
    }


def test_resolve_local_share_requires_an_editable_folder_for_write_packages() -> None:
    with pytest.raises(Exception, match="Can view and edit"):
        _service(_folder("read"))._resolve_local_share_registration(
            principal=_principal(), share_manifest=_manifest("write"),
            registration=LocalShareRegistration(folder_id="f1"),
        )


def test_resolve_local_share_rejects_unknown_folders() -> None:
    with pytest.raises(Exception, match="no longer available"):
        _service(None)._resolve_local_share_registration(
            principal=_principal(), share_manifest=_manifest("read"),
            registration=LocalShareRegistration(folder_id="missing"),
        )
