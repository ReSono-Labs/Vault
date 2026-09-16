from app.vault_runtime.local_api.app import VaultLocalApiApp


class Health:
    def health(self) -> dict[str, object]:
        return {"schemaReady": True, "backend": "test"}


class Companion:
    def __init__(self, paired: bool) -> None:
        self.paired = paired

    def current_link(self):
        if not self.paired:
            return None
        return {"status": "paired", "displayName": "This computer"}

    def start_pairing(self, **kwargs):
        raise AssertionError("pairing is not this test")

    def pairing_status(self, **kwargs):
        raise AssertionError("pairing is not this test")


class A2A:
    def __init__(self) -> None:
        self.calls = []

    def apply_link_snapshot(self, *, inbound, outbound):
        self.calls.append((inbound, outbound))
        return {"applied": True, "workspaces": 1, "inbound": len(inbound), "outbound": len(outbound)}


def test_apply_requires_pairing() -> None:
    app = VaultLocalApiApp(
        store=Health(), token="secret", link_companion=Companion(False), a2a_service=A2A(),
    )
    response = app.handle(
        method="POST",
        target="/link-companion/agent-network/apply",
        headers={"Content-Type": "application/json"},
        body=b'{"inbound":[],"outbound":[]}',
    )
    assert response.status_code == 403


def test_apply_writes_snapshot_when_paired() -> None:
    a2a = A2A()
    app = VaultLocalApiApp(
        store=Health(), token="secret", link_companion=Companion(True), a2a_service=a2a,
    )
    body = b'{"inbound":[{"grant_id":"g1","token":"in"}],"outbound":[{"grant_id":"g2","name":"link-abc","url":"https://agent.example:8443","token":"out"}]}'
    response = app.handle(
        method="POST",
        target="/link-companion/agent-network/apply",
        headers={"Content-Type": "application/json"},
        body=body,
    )
    assert response.status_code == 200
    assert response.payload["applied"] is True
    assert a2a.calls[0][0][0]["token"] == "in"
    assert a2a.calls[0][1][0]["url"] == "https://agent.example:8443"


def test_apply_returns_400_when_agent2agent_is_off() -> None:
    class Off:
        def apply_link_snapshot(self, **kwargs):
            raise ValueError("Turn on Agent2Agent in Vault before Link can apply Agent Network peers.")

    app = VaultLocalApiApp(
        store=Health(), token="secret", link_companion=Companion(True), a2a_service=Off(),
    )
    response = app.handle(
        method="POST",
        target="/link-companion/agent-network/apply",
        headers={"Content-Type": "application/json"},
        body=b'{"inbound":[],"outbound":[]}',
    )
    assert response.status_code == 400
