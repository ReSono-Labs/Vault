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
    def background_access(self, *, user_id: str, workspace_id: str, provider_key: str = "openai", capability=None):
        assert user_id == "user-1"
        assert workspace_id == "workspace-1"
        assert provider_key == "openai"
        assert capability == "web_search"
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



def test_openai_web_search_with_an_api_key_uses_the_platform_api(monkeypatch):
    seen = {}
    class Selected(_Credentials):
        def background_access(self, **kwargs):
            seen.update(kwargs)
            return ProviderCredential("sk-from-capability"), "gpt-search"
    def search(*, api_key, model_key, query):
        seen["api_key"] = api_key
        return _provider_payload()
    monkeypatch.setattr(web_search, "_responses_web_search", search)
    monkeypatch.setattr(web_search, "_codex_web_search", lambda **_: (_ for _ in ()).throw(AssertionError("codex")))
    result = web_search.run_web_search(credentials=Selected(), context=_context(), query="official documentation")
    assert seen["capability"] == "web_search" and seen["api_key"] == "sk-from-capability"
    assert result["results"][0]["url"] == "https://example.test/current"
    assert "sk-from-capability" not in json.dumps(result)


def _jwt(account: str) -> str:
    import base64
    claims = base64.urlsafe_b64encode(json.dumps(
        {"https://api.openai.com/auth": {"chatgpt_account_id": account}}).encode()).decode().rstrip("=")
    return f"header.{claims}.signature"


def _stream_lines(*events):
    return [f"data: {json.dumps(event)}" for event in events] + ["data: [DONE]"]


class _Stream:
    def __init__(self, lines, status=200):
        self.lines, self.status_code = lines, status
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self):
        return b""
    def iter_lines(self):
        return iter(self.lines)


def test_chatgpt_sign_in_searches_through_the_codex_endpoint_with_the_same_tool_contract(monkeypatch):
    """2026-11-23: web search needed a platform API key even with ChatGPT sign-in selected."""
    token = _jwt("acct-123")
    class SignedIn(_Credentials):
        def background_access(self, **kwargs):
            return ProviderCredential(token, auth_method="chatgpt_oauth"), "gpt-6-luna"
    captured = {}
    message = _provider_payload()["output"][0]
    def stream(method, url, **kwargs):
        captured.update(method=method, url=url, **kwargs)
        return _Stream(_stream_lines(
            {"type": "response.web_search_call.completed"},
            {"type": "response.output_item.done", "item": {"type": "web_search_call", "status": "completed"}},
            {"type": "response.output_item.done", "item": message},
            {"type": "response.completed", "response": {"id": "resp-codex-1", "output": []}},
        ))
    monkeypatch.setattr(web_search.httpx, "stream", stream)
    monkeypatch.setattr(web_search, "_responses_web_search", lambda **_: (_ for _ in ()).throw(AssertionError("api")))
    catalog = ToolCatalog(authorizer=lambda definition, context: True)
    web_search.register_web_search_tool(catalog=catalog, credentials=SignedIn())  # type: ignore[arg-type]
    result = catalog.invoke("web_search", {"query": "latest result"}, context=_context(AgentKind.BACKGROUND))
    assert result.is_error is False
    content = result.structured_content
    assert content["results"][0]["url"] == "https://example.test/current"
    assert content["metadata"]["responseId"] == "resp-codex-1" and content["metadata"]["model"] == "gpt-6-luna"
    assert captured["url"] == "https://chatgpt.com/backend-api/codex/responses" and captured["method"] == "POST"
    assert captured["headers"]["Authorization"] == f"Bearer {token}"
    assert captured["headers"]["chatgpt-account-id"] == "acct-123"
    body = captured["json"]
    assert body["stream"] is True and body["store"] is False and body["tool_choice"] == "required"
    assert body["tools"] == [{"type": "web_search"}] and body["model"] == "gpt-6-luna"
    assert token not in json.dumps(content)


def test_a_chatgpt_stream_that_fails_with_http_200_is_an_error_not_an_answer(monkeypatch):
    """A used-up plan arrives as an error event inside a 200 stream; partial output is never used."""
    for events in (
        ({"type": "error", "error": {"type": "usage_limit_reached", "message": "The usage limit has been reached"}},),
        ({"type": "response.output_item.done", "item": _provider_payload()["output"][0]},
         {"type": "response.failed", "response": {"error": None, "output": []}}),
        ({"type": "response.output_item.done", "item": _provider_payload()["output"][0]},
         {"type": "response.completed", "response": {"output": []}}),  # no web search ran
    ):
        try:
            web_search._read_response_stream(_stream_lines(*events))
        except RuntimeError as error:
            assert "ChatGPT web search" in str(error)
        else:
            raise AssertionError(events)
