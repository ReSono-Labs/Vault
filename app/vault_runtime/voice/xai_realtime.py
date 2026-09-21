from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4

import httpx

from app.vault_runtime.voice.openai_realtime import build_openai_realtime_session_object
from app.vault_runtime.voice.provider import (
    ProviderCredential, ProviderDescriptor, RealtimeSessionRequest, RealtimeSessionResult,
)

JSONTransport = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]


class XAIRealtimeError(RuntimeError):
    code = "xai_realtime_error"


class XAIRealtimeProvider:
    provider_key = "xai"
    descriptor = ProviderDescriptor(
        provider_key="xai", display_name="xAI Grok", connection_mode="provider-websocket",
        protocol="xai-realtime", default_voice_model="grok-voice-latest",
        default_text_model="grok-4-0709", default_voice="eve",
        voices=("eve", "ara", "rex", "sal", "leo"),
        voice_models=("grok-voice-latest",),
        text_models=("grok-4.6", "grok-4-0709"),
    )

    def __init__(self, *, json_transport: JSONTransport | None = None) -> None:
        self._transport = json_transport or self._default_transport

    def create_realtime_session(self, request: RealtimeSessionRequest, *, credential: ProviderCredential) -> RealtimeSessionResult:
        if request.connection_mode != self.descriptor.connection_mode:
            raise XAIRealtimeError("xAI browser sessions require provider-websocket mode.")
        try:
            response = self._transport(
                "https://api.x.ai/v1/realtime/client_secrets",
                {"Authorization": f"Bearer {credential.value}", "Content-Type": "application/json"}, {},
            )
        except httpx.HTTPError as exc:
            raise XAIRealtimeError("xAI Realtime client-secret request failed.") from exc
        secret = response.get("value")
        if not isinstance(secret, str) or not secret:
            raise XAIRealtimeError("xAI Realtime response did not contain a client secret.")
        session = build_openai_realtime_session_object(request)
        session["model"] = request.model_key
        return RealtimeSessionResult(
            provider_key=self.provider_key, model_key=request.model_key,
            connection_mode=request.connection_mode,
            provider_session_id=str(response.get("id") or f"xai-local-request-{uuid4()}"),
            session_update_event={"type": "session.update", "session": session},
            client_secret=secret,
            expires_at=response.get("expires_at") if isinstance(response.get("expires_at"), int) else None,
            protocol=self.descriptor.protocol,
            websocket_url=f"wss://api.x.ai/v1/realtime?model={request.model_key}",
            websocket_protocol=f"xai-client-secret.{secret}",
            input_sample_rate=24_000, output_sample_rate=24_000,
        )

    @staticmethod
    def _default_transport(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
        response = httpx.post(url, headers=headers, json=payload, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise XAIRealtimeError("xAI Realtime response was not an object.")
        return data
