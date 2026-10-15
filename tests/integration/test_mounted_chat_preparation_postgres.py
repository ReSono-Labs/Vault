"""Actual authenticated production mount, SQL recall and synthetic Decisions wire."""
import json
from threading import Event
from time import monotonic
from types import SimpleNamespace as NS

import psycopg

from tests.integration.test_mounted_voice_decision_review_postgres import mounted
from tests.integration.test_indexed_memory_postgres import _memory, _install


def test_mounted_drafts_recall_decide_edit_delete_discard_and_deny(mounted, monkeypatch):
    m = mounted
    runtime = m.app._conversation_runtime
    live = runtime.preparation
    assert live.maintenance.ready.wait(10), live.maintenance.state
    from app.vault_runtime.memory_search.indexed import PgvectorMemorySearchBackend
    assert isinstance(runtime.memories._search_backend, PgvectorMemorySearchBackend)
    runtime.memories._embedder_factory = None
    authority = runtime.authority
    authority.ensure_builtin_grants(user_id=m.principal.user_id, workspace_id=m.principal.workspace_id,
        definitions=m.app._voice_tools.definitions(user_id=m.principal.user_id, workspace_id=m.principal.workspace_id))
    vector = [1.] + [0.] * 767
    fact = _memory(runtime.memories._repository, m.principal, "contacts", vector=vector)
    _install(m.url)
    class Embedder:
        model_key = "embeddinggemma:300m"
        def embed(self, text):
            assert text == "Find my contacts"
            return vector
    runtime.memories._embedder_factory = lambda *_: Embedder()
    calls = []
    release_selection = Event()
    class Transport:
        def __init__(self, **_):
            pass
        def evaluate(self, payload, **_):
            calls.append(payload)
            if len(calls) == 1:
                assert release_selection.wait(2), "Interim memory was not exposed while selection waited"
            choices = payload["questions"][0]["choices"]
            chosen = next(c["value"] for c in choices if "contacts_search" in c["description"])
            return {"answers": [{"type": "choice", "name": "workflow", "choice": chosen,
                "confidence": .8, "probabilities": [{"value": c["value"],
                "probability": 1. if c["value"] == chosen else 0.} for c in choices]}]}
    live.transport_factory = Transport
    monkeypatch.setattr(runtime.catalog, "invoke", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("Draft executed a tool")))
    conversation = m.post("/conversations", {"createKey": "live-chat"}, m.headers).payload["conversationId"]
    path = f"/conversations/{conversation}/preparation"
    def update(text, revision, headers=None):
        return m.post(path, dict(utteranceId="draft", revision=revision, text=text, composing=False), headers or m.headers)
    def status(revision):
        return m.app.handle(method="GET", target=path+f"?utteranceId=draft&revision={revision}", headers=m.headers)
    assert update("Find my contacts", 1).status_code == 202
    deadline = monotonic()+2
    while monotonic()<deadline:
        interim = status(1).payload
        if interim["memories"]:
            break
        Event().wait(.02)
    release_selection.set()
    assert interim["state"] == "searching" and interim["tools"] == []
    assert fact.memory_id in [v["id"] for v in interim["memories"]]
    deadline = monotonic()+10
    while monotonic()<deadline:
        response = status(1)
        assert response.status_code == 200, response.payload
        if response.payload["state"] == "ready":
            break
        Event().wait(.05)
    assert response.payload["state"] == "ready", response.payload
    assert fact.memory_id in [v["id"] for v in response.payload["memories"]]
    assert "semantic" in response.payload["memories"][0]["methods"]
    assert response.payload["tools"][0]["kind"] == "catalog_proposal"
    # Selection is independent of memory: only the upcoming input reaches the selector.
    assert calls and all(fact.content_text not in call["input"] for call in calls)
    assert all(json.loads(call["input"])["context_sources"] == [] for call in calls)
    assert update("", 2).status_code == 202
    assert status(1).payload["state"] == "stale"
    assert status(2).payload["memories"] == []
    assert update("conflicting", 2).status_code == 409
    assert update("Find my contacts", 3, {"Cookie": m.headers["Cookie"]}).status_code == 403
    assert m.app.handle(method="GET", target=path+"?utteranceId=draft&revision=2", headers={}).status_code == 403
    deleted = m.app.handle(method="DELETE", target=path, headers=m.headers,
        body=json.dumps({"utteranceId": "draft"}).encode())
    assert deleted.status_code == 200
    assert update("Find my contacts", 4).status_code == 409  # Delayed pre-Send work fenced.
    with psycopg.connect(m.url) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_conversation_turns").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM vault_private.vault_voice_tool_invocations").fetchone()[0] == 0
    next_draft = m.post(path, dict(utteranceId="next",revision=1,text="Find my contacts",composing=False),m.headers)
    assert next_draft.status_code == 202
    deadline = monotonic()+10
    while monotonic()<deadline:
        response = m.app.handle(method="GET",target=path+"?utteranceId=next&revision=1",headers=m.headers)
        if response.payload["state"] == "ready":
            break
        Event().wait(.05)
    if response.payload["state"] != "ready":
        entry = next(iter(live._entries.values()))
        snap = entry.stream._current
        assert False, dict(status=response.payload, external=entry.stream.preparation.ports.guard.external_current(snap,None),
            canonical=live.loader.capture(snap.scope,snap.identity).fingerprint == snap.validity_fingerprint,
            revision=entry.revision, snapshot_revision=snap.identity.revision,
            context=entry.context_fp==snap.context_fingerprint,tools=entry.tool_fp==live._tool_fingerprint(m.principal))
    model_inputs = []
    async def runner(**kwargs):
        model_inputs.append(json.loads(kwargs["input_text"]))
        kwargs["model_response_sink"](NS(response_id="answer",output=[NS(type="message",id="a",role="assistant",
            content=[NS(type="output_text",text="Found the context")])]))
        return "Found the context"
    runtime.runner = runner
    monkeypatch.setattr(runtime.memories,"search",lambda **_: (_ for _ in ()).throw(AssertionError("Repeated final recall")))
    sent = m.post(f"/conversations/{conversation}/turns",dict(submissionKey="send",input="Find my contacts",
        expectedHistoryVersion=0),m.headers)
    assert sent.status_code == 202, sent.payload
    from tests.integration.test_mounted_conversation_runtime_postgres import wait
    assert wait(m,conversation,sent.payload["turnId"])["state"] == "completed"
    assert model_inputs[0]["finalPreparation"]["memoryReused"] is True
    assert model_inputs[0]["finalPreparation"]["executionAuthority"] is False
    # The same live tool route Voice uses reaches the Chat model on Send, as a named proposal.
    assert [t["name"] for t in model_inputs[0]["finalPreparation"]["toolProposals"]] == ["contacts_search"]
    assert model_inputs[0]["authorizedMemory"][0]["memoryId"] == fact.memory_id
    assert m.app.handle(method="GET",target=path+"?utteranceId=next&revision=1",headers=m.headers).payload["state"] == "stale"
