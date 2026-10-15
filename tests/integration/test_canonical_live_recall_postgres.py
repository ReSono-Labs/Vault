import asyncio
from dataclasses import replace
from hashlib import sha256
import json
import os
from urllib.parse import urlsplit

import pytest

from app.vault_runtime.live_memory.canonical_ports import CanonicalPreparationPorts
from app.vault_runtime.live_memory.current_state import CurrentStateGuard
from app.vault_runtime.live_memory.preparation import ParallelPreparation, WorkerBudget
from app.vault_runtime.live_memory.stream_registry import ScopedStreamRegistry
from app.vault_runtime.live_memory.voicemem_stream import VoiceMemStream
from app.vault_runtime.local_api.app import VaultLocalApiApp
from app.vault_runtime.memory_search.indexed import PgvectorMemorySearchBackend
from tests.integration.test_memory_postgres import memory_context
from tests.integration.test_live_memory_current_state_postgres import setup
from tests.integration.test_indexed_memory_postgres import _memory, _install, OPTIONS
from tests.unit.test_live_memory_component import choice, settle, until


@pytest.fixture(autouse=True)
def exact_test_database():
    value = os.getenv("VAULT_TEST_DATABASE_URL")
    if value:
        parsed = urlsplit(value)
        if (parsed.hostname, parsed.port, parsed.path, parsed.username) != (
            "127.0.0.1", 55436, "/resono_vault_test", "vault_test"
        ):
            pytest.fail("Canonical live recall requires the exact isolated database")


def test_real_indexed_drafts_retain_research_change_final_and_off(memory_context, monkeypatch):
    url, identity, owner, second, memories, conversations, prefs, loader, initial = setup(memory_context)
    first_vector, second_vector = [1.0] + [0.0] * 767, [0.0, 1.0] + [0.0] * 766  # local EmbeddingGemma profile
    invoice = _memory(memories, owner.principal, "abc-invoice", vector=first_vector)
    contact = _memory(memories, owner.principal, "sarah-contact", vector=second_vector)
    foreign = _memory(memories, second.principal, "private-other-user", vector=first_vector)
    assert _install(url)["compatible"] == 3
    # Installing/storing synthetic test vectors above is not draft execution.
    for method in ("embeddings_for", "store_embedding", "reconcile_memory"):
        monkeypatch.setattr(memories, method, lambda *args, **kwargs: pytest.fail("Draft scanned/wrote canonical vectors or facts"))
    observed, embedded, factory_scopes = [], [], []
    class SyntheticEmbedder:
        model_key = "embeddinggemma:300m"
        def embed(self, query):
            embedded.append(query)
            return second_vector if "Sarah" in query else first_vector
    def factory(user, workspace):
        factory_scopes.append((user, workspace))
        return SyntheticEmbedder()
    def decisions(snapshot, matches, retained):
        observed.append((snapshot, matches))
        return (choice(matches[0].memory.memory_key if matches else "await-context"),)
    guard = CurrentStateGuard(loader=loader, external_current=lambda *_: True)
    adapter = CanonicalPreparationPorts(guard=guard,
        search_backend=PgvectorMemorySearchBackend(memories=memories, options=OPTIONS),
        limit=2, query_builder=lambda snap: snap.text, decision_retriever=decisions,
        embedder_factory=factory)
    def draft(text, revision):
        item = replace(initial.identity, revision=revision, input_fingerprint=sha256(text.encode()).hexdigest())
        captured = loader.capture(initial.scope, item)
        return replace(initial, text=text, identity=item, validity_fingerprint=captured.fingerprint)
    async def run():
        workers = WorkerBudget(global_limit=4, user_limits={owner.principal.user_id: 4})
        current = VoiceMemStream(ParallelPreparation(ports=adapter, workers=workers),
            debounce_s=0, max_wait_s=0.1, meaningful=lambda _: True)
        registry = ScopedStreamRegistry(capacity=1)
        first = draft("ABC invoice", 1)
        await current.feed_partial(first)
        registry.register(loader.capture(first.scope, first.identity), first.identity.utterance_id, current)
        try:
            result = await settle(current)
            assert [match.memory.memory_id for match in result.memories] == [invoice.memory_id]
            assert "semantic" in result.memories[0].match_methods
            same = draft("ABC invoice", 2)
            await current.feed_partial(same)
            assert (await settle(current)).memories == result.memories
            assert len(embedded) == 1  # Exact validated reuse, not another model call.
            expanded = draft("ABC invoice paid", 3)
            await current.feed_partial(expanded)
            result = await settle(current)
            assert result.memories[0].memory.memory_id == invoice.memory_id and len(embedded) == 2
            changed = draft("Sarah contact", 4)
            await current.feed_partial(changed)
            result = await settle(current)
            assert [match.memory.memory_id for match in result.memories] == [contact.memory_id]
            assert result.decisions == (choice("sarah-contact"),) and len(embedded) == 3
            assert any(snapshot == changed and matches == result.memories for snapshot, matches in observed)
            assert all(foreign.memory_id not in {m.memory.memory_id for m in matches} for _, matches in observed)
            assert set(factory_scopes) == {(owner.principal.user_id, owner.principal.workspace_id)}
            turn = conversations.submit_text(owner.principal, changed.identity.conversation_id,
                                             "send", changed.text, 0)
            final = replace(changed, identity=replace(changed.identity, turn_id=turn.turn_id))
            final_result = await current.finalize(final, timeout_s=3)
            assert final_result.snapshot == final and final_result.memories == result.memories
            assert len(embedded) == 3  # Actual immutable exact-final rebind.
            app = VaultLocalApiApp(store=object(), token="unused", identity_service=identity,
                live_memory_preferences=prefs, live_memory_invalidator=registry.preference_changed)
            headers = {"Cookie": f"resono_refresh={owner.session_token}; resono_csrf={owner.csrf_token}",
                       "X-Resono-Csrf": owner.csrf_token}
            response = await asyncio.to_thread(app.handle, method="POST", target="/live-memory",
                headers=headers, body=json.dumps({"enabled": False, "expectedEpoch": 0}).encode())
            assert response.status_code == 200
            await until(lambda: current._closed)
            assert await current.ready() is None
        finally:
            current.invalidate()
            await current.wait_closed()
            await workers.drain()
    asyncio.run(run())
