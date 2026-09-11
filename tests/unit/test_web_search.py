from __future__ import annotations

import json
from types import SimpleNamespace

from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolInvocationContext
from app.vault_runtime.voice.provider import ProviderCredential
from app.vault_runtime import web_search


class _Credentials:
    def selected_provider(self, *, user_id: str, workspace_id: str):
        return "openai"
    def background_access(self, *, user_id: str, workspace_id: str, provider_key: str = "openai"):
        assert user_id == "user-1"
        assert workspace_id == "workspace-1"
        assert provider_key == "openai"
        return ProviderCredential("sk-secret"), "gpt-search"


def _context(agent: AgentKind = AgentKind.VOICE) -> ToolInvocationContext:
    return ToolInvocationContext(
        agent=agent, user_id="user-1", workspace_id="workspace-1",
        tool_call_id="call-1", local_session_id="session-1", voice_session_id="voice-1",
    )


def _provider_payload() -> dict[str, object]:
    answer = "Current answer from an authoritative source."
    return {
        "id": "resp-search-1",
        "output": [{
            "type": "message",
            "content": [{
                "type": "output_text",
                "text": answer,
                "annotations": [{
                    "type": "url_citation",
                    "url": "https://example.test/current",
                    "title": "Current source",
                    "start_index": 0,
                    "end_index": 14,
                }],
            }],
        }],
    }


def test_web_search_is_exposed_to_both_fixed_system_agents(monkeypatch) -> None:
    catalog = ToolCatalog(authorizer=lambda definition, context: True)
    web_search.register_web_search_tool(catalog=catalog, credentials=_Credentials())  # type: ignore[arg-type]
    monkeypatch.setattr(web_search, "_responses_web_search", lambda **kwargs: _provider_payload())

    realtime = catalog.realtime_definitions(user_id="user-1", workspace_id="workspace-1")
    assert realtime == ({
        "type": "function",
        "name": "web_search",
        "description": (
            "Search the web for current or external information when the answer is time-sensitive, uncertain, "
            "or requires up-to-date public context. Preamble sample phrase: 'I'm checking that online now.'"
        ),
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "The web query to research."}},
            "required": ["query"],
            "additionalProperties": False,
        },
    },)
    assert [item.name for item in catalog.definitions_for(AgentKind.BACKGROUND)] == ["web_search"]

    result = catalog.invoke("web_search", {"query": "  latest   result  "}, context=_context())
    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["operation"] == "web.search"
    assert result.structured_content["query"] == "latest result"
    assert result.structured_content["results"] == [{
        "title": "Current source",
        "url": "https://example.test/current",
        "snippet": "Current answer",
    }]


def test_web_search_rejects_missing_or_overlong_query() -> None:
    catalog = ToolCatalog(authorizer=lambda definition, context: True)
    web_search.register_web_search_tool(catalog=catalog, credentials=_Credentials())  # type: ignore[arg-type]

    assert catalog.invoke("web_search", {"query": "  "}, context=_context()).is_error
    assert catalog.invoke(
        "web_search", {"query": "x" * 2001}, context=_context(),
    ).is_error


def test_web_search_requires_valid_public_citations(monkeypatch) -> None:
    catalog = ToolCatalog(authorizer=lambda definition, context: True)
    web_search.register_web_search_tool(catalog=catalog, credentials=_Credentials())  # type: ignore[arg-type]
    payload = _provider_payload()
    payload["output"][0]["content"][0]["annotations"] = [{  # type: ignore[index]
        "type": "url_citation", "url": "https://user:pass@example.test/private",
    }]
    monkeypatch.setattr(web_search, "_responses_web_search", lambda **kwargs: payload)

    result = catalog.invoke("web_search", {"query": "current"}, context=_context())
    assert result.is_error
    assert "provider did not complete" in result.text


def test_responses_request_matches_successful_voice_adapter(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"id": "resp-1"}

    def post(url: str, **kwargs: object) -> _Response:
        captured.update({"url": url, **kwargs})
        return _Response()

    monkeypatch.setattr(web_search.httpx, "post", post)
    web_search._responses_web_search(api_key="sk-private", model_key="gpt-search", query="current news")

    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["timeout"] == 45.0
    assert captured["headers"] == {
        "Authorization": "Bearer sk-private", "Content-Type": "application/json",
    }
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["tools"] == [{"type": "web_search", "search_context_size": "low"}]
    assert payload["prompt_cache_key"] == "vault-direct-web-search-v1"
    input_text = payload["input"][0]["content"][0]["text"]  # type: ignore[index]
    assert json.loads(input_text)["freshnessPolicy"] == "live_only"


def test_gemini_search_uses_only_gemini_endpoint_and_normalizes_grounding(monkeypatch) -> None:
    class GeminiCredentials:
        def selected_provider(self, **_kwargs): return "gemini"
        def background_access(self, **_kwargs): return ProviderCredential("gemini-secret"), "gemini-2.5-pro"
    captured = {}
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"candidates":[{"content":{"parts":[{"text":"Grounded Gemini answer"}]},"groundingMetadata":{"groundingChunks":[{"web":{"uri":"https://example.test/gemini","title":"Gemini source"}}]}}]}
    def post(url, **kwargs): captured.update({"url":url, **kwargs}); return Response()
    monkeypatch.setattr(web_search.httpx, "post", post)
    result = web_search.run_web_search(credentials=GeminiCredentials(), context=_context(), query="current")
    assert captured["url"].startswith("https://generativelanguage.googleapis.com/")
    assert captured["headers"]["x-goog-api-key"] == "gemini-secret"
    assert captured["json"]["tools"] == [{"google_search": {}}]
    assert result["metadata"]["provider"] == "gemini"
    assert result["results"][0]["url"] == "https://example.test/gemini"


def test_xai_search_uses_only_xai_endpoint_and_normalizes_citations(monkeypatch) -> None:
    class XAICredentials:
        def selected_provider(self, **_kwargs): return "xai"
        def background_access(self, **_kwargs): return ProviderCredential("xai-secret"), "grok-4.6"
    captured = {}
    class Response:
        def raise_for_status(self): pass
        def json(self): return {"output_text":"Grounded Grok answer","citations":[{"url":"https://example.test/xai","title":"xAI source"}]}
    def post(url, **kwargs): captured.update({"url":url, **kwargs}); return Response()
    monkeypatch.setattr(web_search.httpx, "post", post)
    result = web_search.run_web_search(credentials=XAICredentials(), context=_context(), query="current")
    assert captured["url"] == "https://api.x.ai/v1/responses"
    assert captured["headers"]["Authorization"] == "Bearer xai-secret"
    assert captured["json"]["tools"] == [{"type":"web_search"}]
    assert result["metadata"]["provider"] == "xai"
    assert result["results"][0]["url"] == "https://example.test/xai"
