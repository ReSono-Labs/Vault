from hashlib import sha256

from app.vault_runtime.workspace_files.repository import workspace_file_key_hash
from app.vault_runtime.workspace_paths import normalize_workspace_file_key


def test_normalize_workspace_file_key_matches_donor() -> None:
    assert normalize_workspace_file_key("signals/business/readme") == "signals/business/readme"
    assert workspace_file_key_hash("signals/business/readme") == sha256(b"signals/business/readme").hexdigest()
