from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import httpx

from app.vault_runtime.voice.provider import (
    ProviderCredential, ProviderDescriptor, RealtimeSessionRequest, RealtimeSessionResult,
)

JSONTransport = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


class GeminiLiveError(RuntimeError):
    code = "gemini_live_error"


class GeminiLiveProvider:
    provider_key = "gemini"
    descriptor = ProviderDescriptor(
        provider_key="gemini", display_name="Google Gemini", connection_mode="provider-websocket",
        protocol="google-live-bidi", default_voice_model="gemini-3.1-flash-live-preview",
        default_text_model="gemini-2.5-pro", default_voice="Kore",
        voices=("Kore", "Puck", "Charon", "Fenrir", "Aoede", "Leda", "Orus", "Zephyr"),
        voice_models=("gemini-3.1-flash-live-preview",),
    )

    def __init__(self, *, json_transport: JSONTransport | None = None) -> None:
        self._transport = json_transport or self._default_transport

    def create_realtime_session(self, request: RealtimeSessionRequest, *, credential: ProviderCredential) -> RealtimeSessionResult:
        if request.connection_mode != self.descriptor.connection_mode:
            raise GeminiLiveError("Gemini Live browser sessions require provider-websocket mode.")
        config = _live_config(request)
        now = datetime.now(timezone.utc)
        payload = {
            "uses": 1,
            "expireTime": (now + timedelta(minutes=30)).isoformat().replace("+00:00", "Z"),
            "newSessionExpireTime": (now + timedelta(minutes=2)).isoformat().replace("+00:00", "Z"),
            "liveConnectConstraints": {"model": f"models/{request.model_key}", "config": config},
        }
        try:
            response = self._transport(
                "https://generativelanguage.googleapis.com/v1beta/auth_tokens",
                ({"Authorization": f"Bearer {credential.value}", "Content-Type": "application/json"}
                 if credential.auth_method == "gemini_oauth" else
                 {"x-goog-api-key": credential.value, "Content-Type": "application/json"}), payload,
            )
        except httpx.HTTPError as exc:
            raise GeminiLiveError("Gemini Live ephemeral-token request failed.") from exc
        token = response.get("name")
        if not isinstance(token, str) or not token:
            raise GeminiLiveError("Gemini Live response did not contain an ephemeral token.")
        setup = {"setup": {"model": f"models/{request.model_key}", **config}}
        return RealtimeSessionResult(
            provider_key=self.provider_key, model_key=request.model_key,
            connection_mode=request.connection_mode,
            provider_session_id=f"gemini-local-request-{uuid4()}",
            session_update_event=setup, client_secret=token,
            protocol=self.descriptor.protocol,
            websocket_url=("wss://generativelanguage.googleapis.com/ws/"
                           "google.ai.generativelanguage.v1beta.GenerativeService."
                           "BidiGenerateContentConstrained"),
            input_sample_rate=16_000, output_sample_rate=24_000,
        )

    @staticmethod
    def _default_transport(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
        response = httpx.post(url, headers=headers, json=payload, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise GeminiLiveError("Gemini Live response was not an object.")
        return data


def _live_config(request: RealtimeSessionRequest) -> dict[str, Any]:
    config: dict[str, Any] = {
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": request.voice or "Kore"}}},
        },
        "inputAudioTranscription": {}, "outputAudioTranscription": {},
    }
    if request.instructions:
        config["systemInstruction"] = {"parts": [{"text": request.instructions}]}
    if request.tool_definitions:
        config["tools"] = [{"functionDeclarations": [
            {"name": str(tool["name"]), "description": str(tool["description"]),
             "parameters": tool["parameters"]} for tool in request.tool_definitions
        ]}]
    return config
