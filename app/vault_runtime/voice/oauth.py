from __future__ import annotations

from dataclasses import dataclass
import base64
from hashlib import sha256
import secrets
import threading
import time
from typing import Any, Callable
from urllib.parse import urlencode, urlsplit

import httpx

from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.voice.credentials import VoiceProviderCredentialStore


OPENAI_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
OPENAI_ISSUER = "https://auth.openai.com"
OPENAI_REDIRECT_URI = "https://auth.openai.com/deviceauth/callback"


class ProviderOAuthError(RuntimeError):
    code = "provider_oauth_error"


@dataclass(slots=True)
class _OpenAIPending:
    principal: LocalPrincipal
    device_auth_id: str
    user_code: str
    expires_at: int


@dataclass(slots=True)
class _GeminiPending:
    principal: LocalPrincipal
    redirect_uri: str
    code_verifier: str
    expires_at: int


class ProviderOAuthService:
    """Two bounded OAuth flows: R1-proven ChatGPT device auth and Google OAuth."""

    def __init__(
        self, *, credentials: VoiceProviderCredentialStore,
        google_client_id: str | None = None, google_client_secret: str | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._credentials = credentials
        self._google_client_id = google_client_id
        self._google_client_secret = google_client_secret
        self._clock = clock
        self._openai: dict[str, _OpenAIPending] = {}
        self._gemini: dict[str, _GeminiPending] = {}
        self._lock = threading.Lock()

    def start_openai(self, principal: LocalPrincipal) -> dict[str, object]:
        response = httpx.post(
            f"{OPENAI_ISSUER}/api/accounts/deviceauth/usercode",
            json={"client_id": OPENAI_CLIENT_ID},
            headers={"Accept": "application/json"}, timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        device_auth_id = payload.get("device_auth_id")
        user_code = payload.get("user_code") or payload.get("usercode")
        if not isinstance(device_auth_id, str) or not isinstance(user_code, str):
            raise ProviderOAuthError("ChatGPT OAuth returned an invalid response.")
        auth_session_id = secrets.token_urlsafe(24)
        expires_at = int(self._clock()) + 900
        with self._lock:
            self._openai[auth_session_id] = _OpenAIPending(principal, device_auth_id, user_code, expires_at)
        return {
            "authSessionId": auth_session_id, "verificationUrl": f"{OPENAI_ISSUER}/codex/device",
            "userCode": user_code, "expiresAt": expires_at,
            "pollIntervalSeconds": min(30, max(1, int(payload.get("interval") or 5))),
        }

    def poll_openai(self, principal: LocalPrincipal, auth_session_id: str) -> dict[str, object]:
        with self._lock:
            pending = self._openai.get(auth_session_id)
        if pending is None or pending.expires_at <= int(self._clock()):
            raise ProviderOAuthError("ChatGPT OAuth session expired.")
        if pending.principal.user_id != principal.user_id or pending.principal.workspace_id != principal.workspace_id:
            raise ProviderOAuthError("ChatGPT OAuth session does not belong to this account.")
        response = httpx.post(
            f"{OPENAI_ISSUER}/api/accounts/deviceauth/token",
            json={"device_auth_id": pending.device_auth_id, "user_code": pending.user_code},
            headers={"Accept": "application/json"}, timeout=30.0,
        )
        if response.status_code in {403, 404}:
            return {"authSessionId": auth_session_id, "status": "pending"}
        response.raise_for_status()
        payload = response.json()
        authorization_code, verifier = payload.get("authorization_code"), payload.get("code_verifier")
        if not isinstance(authorization_code, str) or not isinstance(verifier, str):
            raise ProviderOAuthError("ChatGPT OAuth returned an invalid authorization.")
        token_response = httpx.post(
            f"{OPENAI_ISSUER}/oauth/token", data={
                "grant_type": "authorization_code", "code": authorization_code,
                "redirect_uri": OPENAI_REDIRECT_URI, "client_id": OPENAI_CLIENT_ID,
                "code_verifier": verifier,
            }, headers={"Accept": "application/json"}, timeout=30.0,
        )
        token_response.raise_for_status()
        tokens = _token_payload(token_response.json(), self._clock)
        self._credentials.set_oauth_tokens(
            principal, provider_key="openai", auth_method="chatgpt_oauth", token_payload=tokens,
            model_key="gpt-live-1", background_model_key="gpt-5.6-sol", voice="marin",
        )
        with self._lock:
            self._openai.pop(auth_session_id, None)
        return {"authSessionId": auth_session_id, "status": "completed"}

    def start_gemini(self, principal: LocalPrincipal, redirect_uri: str) -> dict[str, object]:
        if not self._google_client_id or not self._google_client_secret:
            raise ProviderOAuthError("Gemini OAuth client credentials are not configured for this Vault.")
        parsed = urlsplit(redirect_uri)
        if parsed.scheme not in {"https", "http"} or parsed.path != "/providers/gemini/oauth/callback":
            raise ValueError("Gemini OAuth redirect URI is invalid.")
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        with self._lock:
            self._gemini[state] = _GeminiPending(principal, redirect_uri, verifier, int(self._clock()) + 900)
        query = urlencode({
            "client_id": self._google_client_id, "redirect_uri": redirect_uri,
            "response_type": "code", "scope": "openid email https://www.googleapis.com/auth/generative-language.retriever https://www.googleapis.com/auth/cloud-platform",
            "access_type": "offline", "prompt": "consent", "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256",
        })
        return {"authorizationUrl": f"https://accounts.google.com/o/oauth2/v2/auth?{query}"}

    def complete_gemini(self, *, state: str, code: str) -> None:
        with self._lock:
            pending = self._gemini.pop(state, None)
        if pending is None or pending.expires_at <= int(self._clock()):
            raise ProviderOAuthError("Gemini OAuth session expired.")
        response = httpx.post("https://oauth2.googleapis.com/token", data={
            "grant_type": "authorization_code", "code": code,
            "client_id": self._google_client_id, "client_secret": self._google_client_secret,
            "redirect_uri": pending.redirect_uri, "code_verifier": pending.code_verifier,
        }, timeout=30.0)
        response.raise_for_status()
        self._credentials.set_oauth_tokens(
            pending.principal, provider_key="gemini", auth_method="gemini_oauth",
            token_payload=_token_payload(response.json(), self._clock),
            model_key="gemini-3.1-flash-live-preview", background_model_key="gemini-2.5-pro", voice="Kore",
        )


def _token_payload(payload: Any, clock: Callable[[], float]) -> dict[str, object]:
    if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
        raise ProviderOAuthError("OAuth token response was invalid.")
    result: dict[str, object] = dict(payload)
    if isinstance(result.get("expires_in"), int):
        result["_resono_expires_at"] = int(clock()) + int(result["expires_in"])
    return result
