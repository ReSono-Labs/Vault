from contextlib import contextmanager
from types import SimpleNamespace

import httpx
import pytest

from app.vault_runtime.decision_routing.contracts import TransportTimeout, TransportUnavailable
from app.vault_runtime.decision_routing.openai_transport import OpenAIDecisionTransport, SharedModelDecisionTransport


@pytest.mark.parametrize("mode", ["ok", "oversize", "timeout", "denied"])
def test_fixed_endpoint_scoped_credentials_and_safe_failures(monkeypatch, mode):
    principal = object()
    calls = []
    def resolve(owner, provider, capability=None):
        assert owner is principal and provider == "openai" and capability == "decisions"
        return SimpleNamespace(value="private-key", auth_method="api_key")
    created = []
    class Client:
        def __init__(self, **kwargs):
            assert kwargs["follow_redirects"] is False
            created.append(self)
        @contextmanager
        def stream(self, method, url, **kwargs):
            assert kwargs.pop("timeout") == 2
            calls.append((method,url,kwargs))
            if mode == "timeout":
                raise httpx.ReadTimeout("private provider error")
            if mode == "denied":
                raise RuntimeError("private provider error")
            yield SimpleNamespace(raise_for_status=lambda:None,
                iter_bytes=lambda:iter([b"x"*65537 if mode=="oversize" else b'{"answers":[]}']))
    monkeypatch.setattr(httpx,"Client",Client)
    import app.vault_runtime.decision_routing.openai_transport as transport
    monkeypatch.setattr(transport,"_SHARED_CLIENT",None)
    adapter = OpenAIDecisionTransport(credential_resolver=SimpleNamespace(resolve=resolve), principal=principal)
    payload = {"model":"gpt-6-luna","input":"synthetic"}
    if mode == "ok":
        assert adapter.evaluate(payload,timeout_seconds=2) == {"answers":[]}
    else:
        with pytest.raises(TransportTimeout if mode=="timeout" else TransportUnavailable) as error:
            adapter.evaluate(payload,timeout_seconds=2)
        assert "private" not in str(error.value)
    assert calls == [("POST","https://api.openai.com/v1/decisions",
        dict(headers={"Authorization":"Bearer private-key"},json=payload))]
    adapter.evaluate(payload,timeout_seconds=2) if mode == "ok" else None
    assert len(created) == 1  # one pooled client is reused across calls


def test_shared_model_selection_uses_selected_oauth_and_existing_wire():
    principal = SimpleNamespace(user_id="u", workspace_id="w")
    credentials = SimpleNamespace(selected_provider=lambda **_:"openai",
        background_access=lambda **_:(SimpleNamespace(value="shared-token",auth_method="chatgpt_oauth"),"configured-model"))
    calls=[]
    async def runner(**kwargs):
        calls.append(kwargs)
        return {"choice":"__fallback__", "confidence":.9,"probabilities":[1.]}
    payload={"model":"unused-api-model","input":"current draft",
        "questions":[{"choices":[{"value":"__fallback__"}]}]}
    result=SharedModelDecisionTransport(credential_resolver=credentials,principal=principal,runner=runner).evaluate(
        payload,timeout_seconds=1)
    assert result["model"]=="configured-model"
    assert calls[0]["api_key"]=="shared-token"
    assert calls[0]["base_url"]=="https://chatgpt.com/backend-api/codex"
    assert calls[0]["max_turns"]==1 and "function_tools" not in calls[0]


def test_shared_model_selection_timeout_cancels_model_work():
    import asyncio
    stopped=[]
    async def runner(**kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            stopped.append(True)
    credentials=SimpleNamespace(selected_provider=lambda **_:"openai",
        background_access=lambda **_:(SimpleNamespace(value="private",auth_method="chatgpt_oauth"),"configured-model"))
    with pytest.raises(TransportTimeout):
        SharedModelDecisionTransport(credential_resolver=credentials,
            principal=SimpleNamespace(user_id="u",workspace_id="w"),runner=runner).evaluate(
            {"input":"current draft","questions":[]},timeout_seconds=.01)
    assert stopped==[True]
