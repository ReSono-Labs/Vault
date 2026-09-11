from app.vault_runtime.extensions.plugin_package_contract import parse_local_share_block
from app.vault_runtime.extensions.service import ExtensionImportService, LocalShareRegistration


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


def test_resolve_local_share_registration_requires_valid_permission() -> None:
    service = ExtensionImportService(
        repository=object(),
        inspector=object(),
        filesystem=object(),
    )
    share_manifest = parse_local_share_block({
        "mountName": "docs",
        "permission": "read",
        "label": "Docs",
        "required": True,
    })
    try:
        service._resolve_local_share_registration(
            actor_user_id="owner",
            workspace_id="workspace",
            share_manifest=share_manifest,
            registration=LocalShareRegistration("id", "docs", "admin"),
        )
    except Exception as exc:
        assert "read or write" in str(exc)
    else:
        raise AssertionError("expected invalid permission to fail")
