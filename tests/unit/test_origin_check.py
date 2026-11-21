import pytest

from app.vault_runtime.local_api.origin_check import cross_site_refusal

SESSION = {"Cookie": "resono_refresh=s; resono_csrf=c", "X-ReSono-CSRF": "c"}


def check(origin=None, host="127.0.0.1:8765", method="POST", **extra):
    headers = {**SESSION, "Host": host, **extra}
    if origin is not None:
        headers["Origin"] = origin
    return cross_site_refusal(method=method, headers=headers)


@pytest.mark.parametrize("origin,host,extra", [
    ("https://127.0.0.1:8765", "127.0.0.1:8765", {}),                         # this computer
    ("https://192.168.1.20:8765", "192.168.1.20:8765", {}),                   # another PC at home (LAN mode)
    ("http://127.0.0.1:8766", "127.0.0.1:8766", {}),                          # through the Link bridge
    ("https://vault.tail1234.ts.net", "vault.tail1234.ts.net", {}),           # Tailscale, default port
    ("https://vault.tail1234.ts.net", "127.0.0.1:8765", {"X-Forwarded-Host": "vault.tail1234.ts.net"}),  # Tailscale Serve
    ("https://VAULT.local:443", "vault.local", {}),                           # case and default port
    ("https://[::1]:8765", "[::1]:8765", {}),
])
def test_the_address_the_person_opened_vault_at_is_accepted(origin, host, extra) -> None:
    assert check(origin, host, **extra) is None


@pytest.mark.parametrize("origin,extra", [
    ("https://attacker.example", {}),
    ("https://127.0.0.1:9999", {}),                                            # another local site
    ("null", {}),                                                              # sandboxed frame or file
    ("ftp://127.0.0.1:8765", {}),
])
def test_another_site_is_refused(origin, extra) -> None:
    assert check(origin, **extra) is not None


def test_missing_origin_falls_back_to_fetch_metadata() -> None:
    assert check(None) is None
    assert check(None, **{"Sec-Fetch-Site": "same-origin"}) is None
    assert check(None, **{"Sec-Fetch-Site": "cross-site"}) == "cross-site"


def test_only_cookie_sessions_that_change_state_are_checked(monkeypatch) -> None:
    assert check("https://attacker.example", method="GET") is None
    bearer = {"Authorization": "Bearer link-token", "Host": "127.0.0.1:8765", "Origin": "https://elsewhere"}
    assert cross_site_refusal(method="POST", headers=bearer) is None             # Link app and other clients
    assert cross_site_refusal(method="POST", headers={"Host": "a", "Origin": "https://b"}) is None   # no session
    monkeypatch.setenv("RESONO_VAULT_TRUSTED_ORIGINS", "https://vault.example.com, https://other.example/")
    assert check("https://vault.example.com", host="10.0.0.5:8765") is None
    assert check("https://other.example", host="10.0.0.5:8765") is None


def test_the_app_refuses_before_any_route_runs() -> None:
    from app.vault_runtime.local_api.app import VaultLocalApiApp

    class Store:
        def health(self):
            return {}

    app = VaultLocalApiApp(store=Store(), token="unused")
    response = app.handle(method="POST", target="/extensions/safe-mode",
                          headers={**SESSION, "Host": "127.0.0.1:8765", "Origin": "https://attacker.example"},
                          body=b"{}")
    assert response.status_code == 403 and response.payload["error"]["code"] == "cross_site_request"
