from types import SimpleNamespace as NS

from app.vault_runtime.local_api.app import VaultLocalApiApp


class Health:
    def health(self) -> dict[str, object]:
        return {"schemaReady": True, "backend": "test"}


class Companion:
    def __init__(self, paired: bool) -> None:
        self.paired = paired
        self.touched = []

    def current_link(self):
        return {"status": "paired", "displayName": "This computer"} if self.paired else None

    def link_session_id(self):
        return "cs1" if self.paired else None

    def touch_session(self, session_id):
        self.touched.append(session_id)


class Identity:
    """companion-token is the linked owner session; browser-token is a normal owner browser session."""
    def authenticate(self, *, session_token: str):
        sessions = {"companion-token": "cs1", "browser-token": "browser-1"}
        if session_token not in sessions:
            raise RuntimeError("invalid")
        return NS(session_id=sessions[session_token], is_device_owner=True, user_id="u", workspace_id="w")


class A2A:
    def __init__(self) -> None:
        self.calls = []

    def apply_link_snapshot(self, *, inbound, outbound):
        self.calls.append((inbound, outbound))
        return {"applied": True, "workspaces": 1, "inbound": len(inbound), "outbound": len(outbound)}


def _apply(app, token=None, body=b'{"inbound":[],"outbound":[]}'):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return app.handle(method="POST", target="/link-companion/agent-network/apply", headers=headers, body=body)


def _app(paired=True, a2a=None):
    return VaultLocalApiApp(store=Health(), token="secret", identity_service=Identity(),
                            link_companion=Companion(paired), a2a_service=a2a or A2A())


def test_apply_requires_pairing() -> None:
    assert _apply(_app(paired=False), "companion-token").status_code == 403


def test_apply_requires_the_companion_credential() -> None:
    app = _app()
    assert _apply(app).status_code == 403  # A loopback/LAN caller without the credential.
    assert _apply(app, "browser-token").status_code == 403  # Even a real owner browser session.
    assert _apply(app, "forged").status_code == 403


def test_apply_writes_snapshot_when_paired() -> None:
    a2a = A2A()
    app = _app(a2a=a2a)
    body = b'{"inbound":[{"grant_id":"g1","token":"in"}],"outbound":[{"grant_id":"g2","name":"link-abc","url":"https://agent.example:8443","token":"out"}]}'
    response = _apply(app, "companion-token", body)
    assert response.status_code == 200
    assert response.payload["applied"] is True
    assert a2a.calls[0][0][0]["token"] == "in"
    assert a2a.calls[0][1][0]["url"] == "https://agent.example:8443"
    assert app._link_companion.touched == ["cs1"]


def test_apply_returns_400_when_agent2agent_is_off() -> None:
    class Off:
        def apply_link_snapshot(self, **kwargs):
            raise ValueError("Turn on Agent2Agent in Vault before Link can apply Agent Network peers.")

    assert _apply(_app(a2a=Off()), "companion-token").status_code == 400
