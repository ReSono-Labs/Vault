from __future__ import annotations

import httpx
import pytest

from app.vault_runtime.agent_network.client import (
    A2AClient,
    A2AError,
    task_result,
    validate_card_url,
)
from app.vault_runtime.link_companion.transport import link_agent_network_host


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


def test_docker_companion_carries_link_agent_network(monkeypatch) -> None:
    captured = {}
    link_card = (
        "https://agent-cd4dde174d9743cbaed79031f947edca.account-"
        "33478cb6f19e4283933c9f5b5f69be95.agents.resonolink.com:8443/"
        ".well-known/agent-card.json"
    )

    def fake_get(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return httpx.Response(200, json={
            "name": "Hermes",
            "supportedInterfaces": [{
                "protocolBinding": "JSONRPC", "protocolVersion": "1.0",
                "url": url.replace("/.well-known/agent-card.json", "/a2a"),
            }],
        }, request=httpx.Request("GET", url))

    monkeypatch.setenv("RESONO_VAULT_RUNTIME_PUBLISH_PORTS", "1")
    monkeypatch.setattr(httpx, "get", fake_get)
    assert link_agent_network_host("agent-cd4dde174d9743cbaed79031f947edca.account-33478cb6f19e4283933c9f5b5f69be95.agents.resonolink.com")
    A2AClient().discover(link_card, "secret")
    assert captured["proxy"] == "http://host.docker.internal:8769"


def test_link_discovery_preserves_card_path_on_authorized_source_lane(monkeypatch) -> None:
    card_url = (
        "https://agent-b264f978d37c4c28a838160aaeb23e35.account-"
        "33478cb6f19e4283933c9f5b5f69be95.agents.resonolink.com:8453/"
        ".well-known/agent-card.json"
    )

    def fake_get(url, **_kwargs):
        return httpx.Response(200, json={
            "name": "OpenClaw",
            "supportedInterfaces": [{
                "protocolBinding": "JSONRPC", "protocolVersion": "1.0",
                "url": url.replace(":8453/.well-known/agent-card.json", ":8443/a2a/v1"),
            }],
        }, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", fake_get)
    discovered = A2AClient().discover(card_url, "secret")
    assert discovered.rpc_url == card_url.replace("/.well-known/agent-card.json", "/a2a/v1")


def test_standalone_and_non_link_cards_do_not_use_companion_gateway(monkeypatch) -> None:
    captured = {}

    def fake_get(url, **kwargs):
        captured.update({"url": url, **kwargs})
        rpc = url.replace("/.well-known/agent-card.json", "/a2a")
        return httpx.Response(200, json={
            "name": "Hermes",
            "supportedInterfaces": [{
                "protocolBinding": "JSONRPC", "protocolVersion": "1.0",
                "url": rpc,
            }],
        }, request=httpx.Request("GET", url))

    monkeypatch.setenv("RESONO_VAULT_RUNTIME_PUBLISH_PORTS", "1")
    monkeypatch.setattr(httpx, "get", fake_get)
    A2AClient().discover("https://agent.example/.well-known/agent-card.json", "secret")
    assert "proxy" not in captured
    captured.clear()
    monkeypatch.setenv("RESONO_VAULT_RUNTIME_PUBLISH_PORTS", "0")
    link_card = (
        "https://agent-cd4dde174d9743cbaed79031f947edca.account-"
        "33478cb6f19e4283933c9f5b5f69be95.agents.resonolink.com:8443/"
        ".well-known/agent-card.json"
    )
    A2AClient().discover(link_card, "secret")
    assert "proxy" not in captured


def test_failed_task_becomes_user_visible_issue() -> None:
    assert task_result({
        "status": {
            "state": "TASK_STATE_FAILED",
            "message": {"parts": [{"text": "Peer lost its model route."}]},
        },
    }) == ("failed", "Peer lost its model route.", "Peer lost its model route.")
