from __future__ import annotations

import httpx
import pytest

from app.vault_runtime.agent_network.client import (
    A2AClient,
    A2AError,
    task_result,
    validate_card_url,
)


def test_remote_agent_cards_require_https() -> None:
    with pytest.raises(A2AError) as caught:
        validate_card_url("http://agents.example/a2a/card")
    assert caught.value.code == "a2a_tls_required"
    assert validate_card_url("http://127.0.0.1:9900/.well-known/agent-card.json")


def test_discovery_requires_jsonrpc_1_card_and_same_origin(monkeypatch) -> None:
    def fake_get(*_args, **_kwargs):
        return httpx.Response(200, json={
            "name": "Hermes",
            "supportedInterfaces": [{
                "protocolBinding": "JSONRPC", "protocolVersion": "1.0",
                "url": "https://agent.example/a2a",
            }],
        }, request=httpx.Request("GET", "https://agent.example/.well-known/agent-card.json"))

    monkeypatch.setattr(httpx, "get", fake_get)
    card = A2AClient().discover("https://agent.example/.well-known/agent-card.json", "secret")
    assert card.name == "Hermes"
    assert card.rpc_url == "https://agent.example/a2a"


def test_send_uses_a2a_message_and_extracts_completion(monkeypatch) -> None:
    captured = {}

    def fake_post(url, **kwargs):
        captured.update({"url": url, **kwargs})
        request_id = kwargs["json"]["id"]
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": request_id,
            "result": {"task": {
                "id": "remote-1", "contextId": "ctx-1",
                "status": {"state": "TASK_STATE_COMPLETED"},
                "artifacts": [{"parts": [{"text": "Finished cleanly."}]}],
            }},
        }, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    task = A2AClient().send(
        rpc_url="https://agent.example/a2a", token="secret",
        message="Do the work", context_id="ctx-1",
    )
    assert captured["json"]["method"] == "SendMessage"
    assert captured["json"]["params"]["configuration"]["returnImmediately"] is True
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert task_result(task) == ("completed", "Finished cleanly.", None)


def test_failed_task_becomes_user_visible_issue() -> None:
    assert task_result({
        "status": {
            "state": "TASK_STATE_FAILED",
            "message": {"parts": [{"text": "Peer lost its model route."}]},
        },
    }) == ("failed", "Peer lost its model route.", "Peer lost its model route.")
