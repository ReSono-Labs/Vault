from datetime import datetime, timezone

from app.vault_runtime.local_api.app import VaultLocalApiApp


class Health:
    def health(self) -> dict[str, object]:
        return {"schemaReady": True, "backend": "test"}


class Principal:
    user_id = "user-1"
    workspace_id = "workspace-1"
    is_device_owner = True


class Guest(Principal):
    is_device_owner = False


class Identity:
    def __init__(self, principal: Principal) -> None:
        self.principal = principal

    def authenticate(self, session_token: str) -> Principal:
        assert session_token == "session"
        return self.principal

    def require_csrf(self, *, principal: Principal, csrf_token: str) -> None:
        assert csrf_token == "csrf"

    def issue_link_companion_session(self, *, principal):
        from types import SimpleNamespace
        assert principal.is_device_owner
        return SimpleNamespace(session_token="companion-token", principal=SimpleNamespace(session_id="cs1"))


class Companion:
    def __init__(self) -> None:
        self.started = None
        self.approved = None
        self.unpaired = False

    def start_pairing(self, *, display_name: str, poll_token: str):
        assert poll_token == "poll"
        self.started = display_name
        return {"pairingId": "p1", "pairingCode": "ABCD-EF01", "status": "pending"}

    def pairing_status(self, *, pairing_id: str, poll_token: str):
        assert pairing_id == "p1" and poll_token == "poll"
        if not self.approved:
            return {"status": "pending"}
        token, self.token = self.token, None
        return {"status": "approved", **({"companionToken": token} if token else {})}

    def pairing_by_code(self, *, pairing_code: str):
        assert pairing_code == "ABCD-EF01"
        return {"pairingId": "p1", "displayName": "This computer", "status": "pending"}

    def approve_pairing(self, *, pairing_id: str, session_id: str, companion_token: str):
        assert session_id == "cs1"
        self.approved, self.token = pairing_id, companion_token
        return {
            "status": "paired",
            "displayName": "This computer",
            "pairingId": pairing_id,
            "pairedAt": datetime.now(timezone.utc).isoformat(),
        }

    def current_link(self):
        if not self.approved:
            return None
        return {"status": "paired", "displayName": "This computer", "pairingId": self.approved}

    def unpair(self, *, reason: str = "owner_unpaired") -> None:
        self.unpaired = reason
        self.approved = None

    def link_session_id(self):
        return "cs1" if self.approved else None

    def touch_session(self, session_id: str) -> None:
        assert session_id == "cs1"


def _headers() -> dict[str, str]:
    return {
        "Authorization": "Bearer session",
        "Cookie": "resono_csrf=csrf",
        "X-Resono-Csrf": "csrf",
    }


def test_pairing_start_does_not_need_a_vault_session() -> None:
    companion = Companion()
    app = VaultLocalApiApp(store=Health(), token="secret", link_companion=companion)
    response = app.handle(
        method="POST",
        target="/link-companion/pairing/start",
        headers={},
        body=b'{"displayName":"This computer","pollToken":"poll"}',
    )
    assert response.status_code == 201
    assert response.payload["pairingCode"] == "ABCD-EF01"
    assert companion.started == "This computer"


def test_owner_confirms_and_guest_cannot() -> None:
    companion = Companion()
    guest = VaultLocalApiApp(
        store=Health(), token="secret", identity_service=Identity(Guest()), link_companion=companion,
    )
    denied = guest.handle(
        method="POST",
        target="/link-companion/pairing/p1/approve",
        headers=_headers(),
        body=b"{}",
    )
    assert denied.status_code == 403
    owner = VaultLocalApiApp(
        store=Health(), token="secret", identity_service=Identity(Principal()), link_companion=companion,
    )
    approved = owner.handle(
        method="POST",
        target="/link-companion/pairing/p1/approve",
        headers=_headers(),
        body=b"{}",
    )
    assert approved.status_code == 200
    assert approved.payload["status"] == "paired"
    assert "companion-token" not in str(approved.payload)  # Never handed to the approving browser.
    poller = VaultLocalApiApp(store=Health(), token="secret", link_companion=companion)
    def poll():
        return poller.handle(method="POST", target="/link-companion/pairing/status", headers={},
                             body=b'{"pairingId":"p1","pollToken":"poll"}')
    first, second = poll(), poll()
    assert first.status_code == 200 and first.payload == {"status": "approved", "companionToken": "companion-token"}
    assert second.payload == {"status": "approved"}  # Delivered once.


def test_wrong_poll_token_is_not_treated_as_success() -> None:
    class StrictCompanion(Companion):
        def pairing_status(self, *, pairing_id: str, poll_token: str):
            from app.vault_runtime.link_companion.repository import LinkCompanionAuthorizationError
            raise LinkCompanionAuthorizationError("Pairing request is unavailable.")

    app = VaultLocalApiApp(store=Health(), token="secret", link_companion=StrictCompanion())
    response = app.handle(
        method="POST",
        target="/link-companion/pairing/status",
        headers={},
        body=b'{"pairingId":"p1","pollToken":"other"}',
    )
    assert response.status_code == 403


def test_link_releases_its_own_pairing_with_the_companion_credential() -> None:
    """Removing Vault from Link ends the pairing on the Vault side too (owner, 2026-11-10)."""
    from types import SimpleNamespace

    class CompanionIdentity(Identity):
        def authenticate(self, session_token: str):
            if session_token != "companion-token":
                raise PermissionError("unknown session")
            return SimpleNamespace(session_id="cs1", is_device_owner=True)

    companion = Companion()
    companion.approved = "p1"
    app = VaultLocalApiApp(store=Health(), token="secret", identity_service=CompanionIdentity(Principal()),
                           link_companion=companion)
    def release(headers):
        return app.handle(method="POST", target="/link-companion/release", headers=headers, body=b"{}")
    assert release({}).status_code == 403
    assert release({"Authorization": "Bearer someone-else"}).status_code == 403
    assert companion.unpaired is False
    released = release({"Authorization": "Bearer companion-token"})
    assert released.status_code == 200 and released.payload == {"status": "unpaired"}
    assert companion.unpaired == "link_removed"
    assert companion.current_link() is None
