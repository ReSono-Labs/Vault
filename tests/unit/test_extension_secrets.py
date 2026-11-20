from pathlib import Path

import pytest

from app.vault_runtime.extensions.secrets import ExtensionSecretError, LocalMasterKey


def test_master_key_is_32_bytes_stable_and_private(tmp_path: Path) -> None:
    path = tmp_path / "private" / "extension.key"
    owner = LocalMasterKey(path)
    first = owner.load_or_create()
    assert len(first) == 32 and owner.load_or_create() == first
    assert path.stat().st_mode & 0o777 == 0o600


def test_master_key_rejects_broad_permissions_and_invalid_size(tmp_path: Path) -> None:
    path = tmp_path / "key"
    path.write_bytes(b"short")
    path.chmod(0o600)
    with pytest.raises(ExtensionSecretError, match="invalid"):
        LocalMasterKey(path).load_or_create()
    path.write_bytes(b"x" * 32)
    path.chmod(0o644)
    with pytest.raises(ExtensionSecretError, match="permissions"):
        LocalMasterKey(path).load_or_create()
