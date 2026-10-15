from dataclasses import replace
import asyncio
from hashlib import sha256
import json
import os
from urllib.parse import urlsplit

import psycopg
import pytest

from app.vault_runtime.conversation.repository import ConversationRepository
from app.vault_runtime.conversation.contracts import ConflictError, NotFoundError
from app.vault_runtime.decision_routing.contracts import InputIdentity, ScopedPrincipalRef
from app.vault_runtime.live_memory.contracts import InputSnapshot, PreparedContext
from app.vault_runtime.live_memory.current_state import LiveStateLoader, CurrentStateGuard
from app.vault_runtime.live_memory.preferences import LiveMemoryPreferenceRepository
from app.vault_runtime.local_api.app import VaultLocalApiApp
from app.vault_runtime.memory.retrieval import RetrievalMatch
from app.vault_runtime.live_memory.stream_registry import ScopedStreamRegistry
from app.vault_runtime.live_memory.preparation import ParallelPreparation, WorkerBudget
from app.vault_runtime.live_memory.voicemem_stream import VoiceMemStream
from tests.unit.test_live_memory_component import Ports, until
from tests.integration.test_memory_postgres import memory_context
from tests.integration.test_memory_retrieval_state_postgres import create


@pytest.fixture(autouse=True)
def exact_test_database():
    value = os.getenv("VAULT_TEST_DATABASE_URL")
    if value:
        parsed = urlsplit(value)
        if (parsed.hostname, parsed.port, parsed.path, parsed.username) != (
            "127.0.0.1", 55436, "/resono_vault_test", "vault_test"
        ):
            pytest.fail("Live-state tests require the exact isolated database")


def setup(memory_context):
    url, identity, owner, second, memories = memory_context
    conversations = ConversationRepository(database_url=url)
    conversations.ensure_schema()
    conversation = conversations.create(owner.principal, "live-test")
    preferences = LiveMemoryPreferenceRepository(database_url=url)
    preferences.ensure_schema()
    scope = ScopedPrincipalRef(owner.principal.user_id, owner.principal.workspace_id, owner.principal.session_id)
    text = "Remember tea"
    item = InputIdentity(conversation.conversation_id, conversation.segments[0].segment_id,
                         "utterance", 1, None, sha256(text.encode()).hexdigest())
    loader = LiveStateLoader(database_url=url, memories=memories, preferences=preferences)
    captured = loader.capture(scope, item)
    snap = InputSnapshot(scope, item, text, (), "synthetic-source-context", captured.fingerprint)
    return url, identity, owner, second, memories, conversations, preferences, loader, snap


def test_final_identity_rebind_and_newer_turn_rejection(memory_context):
    _url, _identity, owner, _second, _memories, conversations, _prefs, loader, snap = setup(memory_context)
    turn = conversations.submit_text(owner.principal, snap.identity.conversation_id, "send", snap.text, 0)
    final = replace(snap, identity=replace(snap.identity, turn_id=turn.turn_id))
    guard = CurrentStateGuard(loader=loader, external_current=lambda *_: True)
    assert guard.is_current(final, PreparedContext(final, (), ()))
    with pytest.raises(ConflictError):
        loader.capture(final.scope, replace(final.identity, input_fingerprint="0" * 64))
    with pytest.raises(NotFoundError):
        loader.capture(final.scope, replace(final.identity, segment_id="wrong"))
    conversations.submit_text(owner.principal, snap.identity.conversation_id, "next", "new turn", 1)
    assert not guard.is_current(final, None)


def test_metadata_deleted_memory_off_and_aba_reject_preparation(memory_context):
    url, _identity, owner, _second, memories, _conversations, prefs, loader, snap = setup(memory_context)
    record = create(memories, owner.principal)
    snap = replace(snap, validity_fingerprint=loader.capture(snap.scope, snap.identity).fingerprint)
    prepared = PreparedContext(snap, (RetrievalMatch(record, 1.0, ("synthetic",)),), ())
    guard = CurrentStateGuard(loader=loader, external_current=lambda *_: True)
    assert guard.is_current(snap, prepared)
    with psycopg.connect(url) as connection:
        connection.execute("UPDATE vault_private.vault_memory_records SET confidence='low' WHERE memory_id=%s", (record.memory_id,))
    assert not guard.is_current(snap, prepared)
    fresh = replace(snap, validity_fingerprint=loader.capture(snap.scope, snap.identity).fingerprint)
    assert not guard.is_current(fresh, replace(prepared, snapshot=fresh))
    memories.delete_memory(user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id, memory_id=record.memory_id)
    fresh = replace(snap, validity_fingerprint=loader.capture(snap.scope, snap.identity).fingerprint)
    assert not guard.is_current(fresh, replace(prepared, snapshot=fresh))
    assert guard.is_current(fresh, None)
    prefs.set(owner.principal, enabled=False, expected_epoch=0)
    assert not guard.is_current(fresh, None)
    prefs.set(owner.principal, enabled=True, expected_epoch=1)
    assert not guard.is_current(fresh, None)


def test_repeatable_read_does_not_mix_concurrently_changed_preference_and_memory(memory_context):
    url, _identity, owner, _second, memories, _conversations, prefs, loader, snap = setup(memory_context)
    record = create(memories, owner.principal)
    prefs.set(owner.principal, enabled=True, expected_epoch=0)
    before = loader.capture(snap.scope, snap.identity, memory_ids=[record.memory_id])
    class MutatingPreferences(LiveMemoryPreferenceRepository):
        def _get_cursor(self, cursor, **scope):
            preference = super()._get_cursor(cursor, **scope)
            with psycopg.connect(url) as connection:
                connection.execute("UPDATE vault_private.vault_live_memory_preferences SET enabled=false,epoch=epoch+1")
                connection.execute("UPDATE vault_private.vault_memory_records SET confidence='low' WHERE memory_id=%s", (record.memory_id,))
            return preference
    coherent = LiveStateLoader(database_url=url, memories=memories,
                              preferences=MutatingPreferences(database_url="must-not-connect"))
    captured = coherent.capture(snap.scope, snap.identity, memory_ids=[record.memory_id])
    assert captured == before
    current = loader.capture(snap.scope, snap.identity, memory_ids=[record.memory_id])
    assert not current.preference.enabled and current.memory.records[0].memory.confidence == "low"
    assert current.fingerprint != captured.fingerprint


def test_wrong_scope_and_revoked_session_fail_closed(memory_context):
    url, _identity, owner, second, _memories, _conversations, _prefs, loader, snap = setup(memory_context)
    guard = CurrentStateGuard(loader=loader, external_current=lambda *_: True)
    other = ScopedPrincipalRef(second.principal.user_id, second.principal.workspace_id, second.principal.session_id)
    assert not guard.is_current(replace(snap, scope=other), None)
    with psycopg.connect(url) as connection:
        connection.execute("UPDATE vault_private.local_sessions SET status='revoked' WHERE session_id=%s", (owner.principal.session_id,))
    assert not guard.is_current(snap, None)


def test_committed_setting_notification_and_failure_are_truthful(memory_context):
    _url, identity, owner, _second, _memories, _conversations, prefs, _loader, _snap = setup(memory_context)
    notified = []
    def changed(preference):
        assert prefs.get(owner.principal) == preference  # Notification is after commit.
        notified.append(preference)
    app = VaultLocalApiApp(store=object(), token="unused", identity_service=identity,
                           live_memory_preferences=prefs, live_memory_invalidator=changed)
    headers = {"Cookie": f"resono_refresh={owner.session_token}; resono_csrf={owner.csrf_token}",
               "X-Resono-Csrf": owner.csrf_token}
    def send(epoch):
        return app.handle(method="POST", target="/live-memory", headers=headers,
                          body=json.dumps({"enabled": False, "expectedEpoch": epoch}).encode())
    assert send(0).status_code == 200 and len(notified) == 1
    assert send(0).status_code == 409 and len(notified) == 1
    def failed(preference):
        raise RuntimeError("Synthetic callback failure")
    app._live_memory_invalidator = failed
    response = send(1)
    assert response.status_code == 503 and response.payload["epoch"] == 1
    assert response.payload["error"]["code"] == "live_memory_invalidation_failed"
    assert not prefs.get(owner.principal).enabled


def test_actual_off_api_invalidates_registered_voicemem_stream(memory_context):
    _url, identity, owner, _second, _memories, _conversations, prefs, loader, snap = setup(memory_context)
    async def run():
        guard = CurrentStateGuard(loader=loader, external_current=lambda *_: True)
        class GuardedPorts(Ports):
            def is_current(self, snapshot, prepared):
                return guard.is_current(snapshot, prepared)
        ports = GuardedPorts()
        workers = WorkerBudget(global_limit=2, user_limits={owner.principal.user_id: 2})
        stream = VoiceMemStream(ParallelPreparation(ports=ports, workers=workers),
            debounce_s=1, max_wait_s=1, meaningful=lambda _: True)
        registry = ScopedStreamRegistry(capacity=1)
        captured = loader.capture(snap.scope, snap.identity)
        await stream.feed_partial(snap)
        key = registry.register(captured, snap.identity.utterance_id, stream)
        app = VaultLocalApiApp(store=object(), token="unused", identity_service=identity,
            live_memory_preferences=prefs, live_memory_invalidator=registry.preference_changed)
        headers = {"Cookie": f"resono_refresh={owner.session_token}; resono_csrf={owner.csrf_token}",
                   "X-Resono-Csrf": owner.csrf_token}
        try:
            response = await asyncio.to_thread(app.handle, method="POST", target="/live-memory",
                headers=headers, body=json.dumps({"enabled": False, "expectedEpoch": 0}).encode())
            assert response.status_code == 200
            await until(lambda: stream._closed)
            assert not guard.is_current(snap, None)
            assert not registry.unregister(key) and await stream.ready() is None
            await stream.wait_closed()
            assert not ports.calls
        finally:
            stream.invalidate()
            await stream.wait_closed()
            await workers.drain()
    asyncio.run(run())
