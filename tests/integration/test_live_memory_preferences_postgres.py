from concurrent.futures import ThreadPoolExecutor
import json
import http.client
import os
from urllib.parse import urlsplit

import psycopg
import pytest

from app.vault_runtime.live_memory.preferences import (
    LiveMemoryPreferenceRepository, PreferenceConflictError,
)
from app.vault_runtime.local_identity.repository import LocalSessionError
from app.vault_runtime.local_api.app import VaultLocalApiApp
from app.vault_runtime.local_api.config import VaultLocalApiConfig
from app.vault_runtime.local_api.server import VaultLocalServer
from tests.integration.test_memory_postgres import memory_context


@pytest.fixture(autouse=True)
def exact_test_database():
    value = os.getenv("VAULT_TEST_DATABASE_URL")
    if value:
        parsed = urlsplit(value)
        if (parsed.hostname, parsed.port, parsed.path, parsed.username) != (
            "127.0.0.1", 55436, "/resono_vault_test", "vault_test"
        ):
            pytest.fail("Preference tests require the exact isolated database")


def repository(url):
    result = LiveMemoryPreferenceRepository(database_url=url)
    result.ensure_schema()
    return result


def test_default_scope_persistence_cas_noop_aba_and_erasure(memory_context):
    url, identity, owner, second, _memories = memory_context
    prefs = repository(url)
    principal = owner.principal
    assert prefs.get(principal).enabled and prefs.get(principal).epoch == 0
    off = prefs.set(principal, enabled=False, expected_epoch=0)
    assert off.epoch == 1 and not off.enabled
    assert prefs.set(principal, enabled=False, expected_epoch=1) == off
    with pytest.raises(PreferenceConflictError):
        prefs.set(principal, enabled=True, expected_epoch=0)
    assert prefs.set(principal, enabled=True, expected_epoch=1).epoch == 2
    assert repository(url).get(principal).epoch == 2
    assert prefs.get(second.principal).enabled and prefs.get(second.principal).epoch == 0
    identity.add_member(principal=principal, workspace_id=principal.workspace_id, username="second")
    identity.switch_workspace(principal=second.principal, workspace_id=principal.workspace_id)
    member = identity.authenticate(session_token=second.session_token)
    with pytest.raises(LocalSessionError):
        prefs.get(second.principal)
    prefs.set(member, enabled=False, expected_epoch=0)
    assert prefs.get(principal).enabled
    identity.remove_user(actor=principal, user_id=member.user_id)
    with psycopg.connect(url) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_live_memory_preferences WHERE user_id=%s",
                                  (member.user_id,)).fetchone()[0] == 0


def test_concurrent_initial_writes_have_one_winner(memory_context):
    url, _identity, owner, _second, _memories = memory_context
    prefs = repository(url)
    def update(enabled):
        try:
            return prefs.set(owner.principal, enabled=enabled, expected_epoch=0)
        except PreferenceConflictError:
            return None
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(update, [True, False]))
    assert sum(result is not None for result in results) == 1
    assert prefs.get(owner.principal).epoch == 1


@pytest.mark.parametrize("change", ["expired", "revoked", "membership"])
def test_current_authority_denies_get_and_set(memory_context, change):
    url, _identity, owner, _second, _memories = memory_context
    prefs = repository(url)
    principal = owner.principal
    with psycopg.connect(url) as connection:
        if change == "membership":
            connection.execute("UPDATE vault_private.local_workspace_memberships SET status='revoked' WHERE user_id=%s",
                               (principal.user_id,))
        elif change == "expired":
            connection.execute("UPDATE vault_private.local_sessions SET expires_at=now()-interval '1 second' WHERE session_id=%s",
                               (principal.session_id,))
        else:
            connection.execute("UPDATE vault_private.local_sessions SET status='revoked' WHERE session_id=%s",
                               (principal.session_id,))
    with pytest.raises(LocalSessionError):
        prefs.get(principal)
    with pytest.raises(LocalSessionError):
        prefs.set(principal, enabled=False, expected_epoch=0)


def test_local_api_authentication_csrf_scope_and_conflict(memory_context):
    url, identity, owner, _second, _memories = memory_context
    prefs = repository(url)
    app = VaultLocalApiApp(store=object(), token="unused", identity_service=identity,
                           live_memory_preferences=prefs)
    cookies = {"Cookie": f"resono_refresh={owner.session_token}; resono_csrf={owner.csrf_token}"}
    def request(method, payload=None, headers=None):
        return app.handle(method=method, target="/live-memory", headers=headers or {},
                          body=json.dumps(payload).encode() if payload is not None else b"")
    assert request("GET").status_code == 401
    initial = request("GET", headers=cookies)
    assert initial.payload == {"enabled": True, "epoch": 0}
    assert ("Cache-Control", "no-store") in initial.headers
    assert request("POST", {"enabled": False, "expectedEpoch": 0}, cookies).status_code == 401
    headers = {**cookies, "X-Resono-Csrf": owner.csrf_token}
    assert request("POST", {"enabled": False, "expectedEpoch": 0, "userId": "other"}, headers).status_code == 400
    assert request("POST", {"enabled": False, "expectedEpoch": 0}, headers).payload == {"enabled": False, "epoch": 1}
    assert request("POST", {"enabled": True, "expectedEpoch": 0}, headers).status_code == 409
    assert request("DELETE", headers=headers).status_code == 404
    missing = VaultLocalApiApp(store=object(), token="unused", identity_service=identity)
    assert missing.handle(method="GET", target="/live-memory", headers=cookies).status_code == 503


def test_http_cookie_csrf_and_read_only_default(memory_context):
    url, identity, owner, _second, _memories = memory_context
    prefs = repository(url)
    class Health:
        def health(self):
            return {"database": "test"}
    app = VaultLocalApiApp(store=Health(), token="unused", identity_service=identity,
                           live_memory_preferences=prefs)
    runtime = VaultLocalServer(config=VaultLocalApiConfig(
        host="127.0.0.1", port=0, token="unused", data_root="/tmp/vault-preference-test",
        storage_status_file="/tmp/vault-preference-test/status.json",
        storage_mount_point="/tmp/vault-preference-test/private", database_url=url,
    ), app=app)
    host, port = runtime.start()
    connection = http.client.HTTPConnection(host, port, timeout=4)
    cookies = {"Cookie": f"resono_refresh={owner.session_token}; resono_csrf={owner.csrf_token}"}
    try:
        connection.request("GET", "/live-memory", headers=cookies)
        response = connection.getresponse()
        assert response.status == 200
        assert {value.strip() for value in response.getheader("Cache-Control").split(",")} == {"no-store"}
        assert json.loads(response.read()) == {"enabled": True, "epoch": 0}
        with psycopg.connect(url) as database:
            assert database.execute("SELECT count(*) FROM vault_private.vault_live_memory_preferences").fetchone()[0] == 0
        body = json.dumps({"enabled": False, "expectedEpoch": 0})
        connection.request("POST", "/live-memory", body=body,
                           headers={**cookies, "Content-Type": "application/json"})
        response = connection.getresponse()
        assert response.status == 401
        response.read()
        connection.request("POST", "/live-memory", body=body,
                           headers={**cookies, "Content-Type": "application/json",
                                    "X-Resono-Csrf": owner.csrf_token})
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read()) == {"enabled": False, "epoch": 1}
    finally:
        connection.close()
        runtime.stop()
