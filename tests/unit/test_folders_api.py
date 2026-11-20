from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.vault_runtime.folders.models import DeviceLocation
from app.vault_runtime.folders.service import FolderService
from app.vault_runtime.local_api.app import VaultLocalApiApp
from tests.support.folders import MemoryFolderRepository, _principal


class Identity:
    def __init__(self) -> None:
        self.principals = {"admin": _principal("admin", admin=True), "kid": _principal("kid")}

    def authenticate(self, session_token: str):
        return self.principals[session_token]

    def require_csrf(self, *, principal, csrf_token: str) -> None:
        if csrf_token != "csrf":
            raise PermissionError("CSRF proof is invalid.")


class Health:
    def health(self) -> dict[str, object]:
        return {"schemaReady": True, "backend": "test"}


def _headers(user: str, csrf: str = "csrf") -> dict[str, str]:
    return {"Authorization": f"Bearer {user}", "Cookie": f"resono_csrf={csrf}", "X-Resono-Csrf": csrf}


@pytest.fixture
def api(tmp_path: Path):
    home = tmp_path / "secret-host-home"
    (home / "Documents" / "Projects").mkdir(parents=True)
    service = FolderService(
        repository=MemoryFolderRepository({"admin", "kid"}),
        locations=(DeviceLocation("home", "Home", home, "home"),),
        documents_folder="Documents",
    )
    app = VaultLocalApiApp(store=Health(), token="secret", identity_service=Identity(), folders=service)

    def call(method: str, target: str, user: str, body: dict | None = None, csrf: str = "csrf"):
        response = app.handle(
            method=method, target=target, headers=_headers(user, csrf),
            body=json.dumps(body).encode() if body is not None else b"",
        )
        return response.status_code, response.payload

    return call


def test_admin_routes_are_master_account_only(api) -> None:
    status, payload = api("GET", "/admin/folders/locations", "kid")
    assert status == 403 and payload["error"]["code"] == "admin_required"
    status, payload = api("POST", "/admin/users/kid/folder-access", "kid",
                          {"locationId": "home", "path": "Documents", "maxPermission": "write"})
    assert status == 403


def test_post_requires_csrf(api) -> None:
    status, _payload = api("POST", "/folders/setup/vault-folder", "admin", {}, csrf="wrong")
    assert status in {400, 403}


def test_full_flow_never_shows_host_paths(api) -> None:
    status, grant = api("POST", "/admin/users/kid/folder-access", "admin",
                        {"locationId": "home", "path": "Documents", "maxPermission": "write"})
    assert status == 201
    status, places = api("GET", "/folders/places", "kid")
    assert status == 200 and places["items"][0]["label"] == "Documents"
    status, listing = api("GET", f"/folders/browse?grantId={grant['grantId']}&path=", "kid")
    assert status == 200 and [d["name"] for d in listing["directories"]] == ["Projects"]
    status, folder = api("POST", "/folders", "kid", {
        "grantId": grant["grantId"], "path": "Projects", "name": "Projects", "permission": "write",
    })
    assert status == 201
    status, folders = api("GET", "/folders", "kid")
    assert status == 200 and folders["folders"][0]["path"] == "local/Projects"
    for payload in (grant, places, listing, folder, folders):
        assert "secret-host-home" not in json.dumps(payload)

    status, _ = api("POST", f"/folders/{folder['folderId']}/permission", "kid", {"permission": "read"})
    assert status == 200
    status, _ = api("POST", f"/folders/{folder['folderId']}/remove", "kid", {})
    assert status == 200
    status, _ = api("POST", f"/admin/folder-access/{grant['grantId']}/remove", "admin", {})
    assert status == 200
    status, payload = api("GET", f"/folders/browse?grantId={grant['grantId']}", "kid")
    assert status == 404 and payload["error"]["code"] == "folder_unavailable"


def test_path_errors_use_folder_codes(api) -> None:
    status, grant = api("POST", "/admin/users/admin/folder-access", "admin",
                        {"locationId": "home", "path": "", "maxPermission": "read"})
    status, payload = api("GET", f"/folders/browse?grantId={grant['grantId']}&path=.ssh", "admin")
    assert status == 400 and payload["error"]["code"] == "hidden_path"
    status, payload = api("GET", f"/folders/browse?grantId={grant['grantId']}&path=../x", "admin")
    assert status == 400 and payload["error"]["code"] == "outside_access"
