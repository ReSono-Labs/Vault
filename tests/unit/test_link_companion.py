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
        return "approved" if self.approved else "pending"

    def pairing_by_code(self, *, pairing_code: str):
        assert pairing_code == "ABCD-EF01"
        return {"pairingId": "p1", "displayName": "This computer", "status": "pending"}

    def approve_pairing(self, *, pairing_id: str):
        self.approved = pairing_id
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

    def unpair(self) -> None:
        self.unpaired = True
        self.approved = None


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
    status = VaultLocalApiApp(store=Health(), token="secret", link_companion=companion).handle(
        method="POST",
        target="/link-companion/pairing/status",
        headers={},
        body=b'{"pairingId":"p1","pollToken":"poll"}',
    )
    assert status.status_code == 200
    assert status.payload["status"] == "approved"


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
