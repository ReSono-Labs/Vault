from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.voice.oauth import (
    ProviderOAuthError,
    ProviderOAuthService,
    XAI_OAUTH_CLIENT_ID,
    XAI_OAUTH_SCOPE,
)


class _Store:
    def __init__(self) -> None:
        self.saved: dict[str, object] | None = None

    def set_oauth_tokens(self, principal: LocalPrincipal, **kwargs: object) -> None:
        del principal
        self.saved = kwargs


class _Response:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://auth.x.ai/oauth2/token")
            raise httpx.HTTPStatusError("xAI OAuth failed", request=request, response=httpx.Response(self.status_code, request=request))

    def json(self) -> object:
        return self._payload


def _principal() -> LocalPrincipal:
    return LocalPrincipal(
        user_id="u1", username="owner", display_name="Owner", experience_style="strict",
        is_device_owner=True, session_id="s1", workspace_id="w1",
        expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
    )


def test_xai_device_code_start_and_poll_stores_oauth_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _Store()
    service = ProviderOAuthService(credentials=store, clock=lambda: 1_000)  # type: ignore[arg-type]
    posts: list[tuple[str, dict[str, str]]] = []

    def fake_get(url: str, **_kwargs: object) -> _Response:
        assert url == "https://auth.x.ai/.well-known/openid-configuration"
        return _Response(200, {
            "device_authorization_endpoint": "https://auth.x.ai/oauth2/device/code",
            "token_endpoint": "https://auth.x.ai/oauth2/token",
        })

    def fake_post(url: str, **kwargs: object) -> _Response:
        data = dict(kwargs.get("data") or {})
        posts.append((url, data))
        if url.endswith("/oauth2/device/code"):
            assert data["client_id"] == XAI_OAUTH_CLIENT_ID
            assert data["scope"] == XAI_OAUTH_SCOPE
            return _Response(200, {
                "device_code": "device-1",
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://auth.x.ai/device",
                "verification_uri_complete": "https://auth.x.ai/device?user_code=ABCD-EFGH",
                "expires_in": 300,
                "interval": 5,
            })
        if url.endswith("/oauth2/token") and data.get("grant_type") == "urn:ietf:params:oauth:grant-type:device_code":
            if len([item for item in posts if item[0].endswith("/oauth2/token")]) == 1:
                return _Response(400, {"error": "authorization_pending"})
            return _Response(200, {
                "access_token": "access-1",
                "refresh_token": "refresh-1",
                "expires_in": 3600,
            })
        raise AssertionError(url)

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    started = service.start_xai(_principal())
    assert started["verificationUrl"] == "https://auth.x.ai/device?user_code=ABCD-EFGH"
    assert started["userCode"] == "ABCD-EFGH"
    assert started["pollIntervalSeconds"] == 5
    pending = service.poll_xai(_principal(), str(started["authSessionId"]))
    assert pending == {"authSessionId": started["authSessionId"], "status": "pending"}
    completed = service.poll_xai(_principal(), str(started["authSessionId"]))
    assert completed["status"] == "completed"
    assert store.saved is not None
    assert store.saved["provider_key"] == "xai"
    assert store.saved["auth_method"] == "xai_oauth"
    payload = store.saved["token_payload"]
    assert isinstance(payload, dict)
    assert payload["access_token"] == "access-1"
    assert payload["_resono_token_endpoint"] == "https://auth.x.ai/oauth2/token"
    assert store.saved["background_model_key"] == "grok-4.6"


def test_xai_discovery_rejects_untrusted_token_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ProviderOAuthService(credentials=_Store(), clock=lambda: 1_000)  # type: ignore[arg-type]

    def fake_get(url: str, **_kwargs: object) -> _Response:
        del url
        return _Response(200, {"token_endpoint": "https://evil.example/token"})

    monkeypatch.setattr(httpx, "get", fake_get)
    with pytest.raises(ProviderOAuthError, match="trusted xAI endpoint"):
        service.start_xai(_principal())
