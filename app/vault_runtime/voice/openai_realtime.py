from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import uuid4

import httpx

from app.vault_runtime.voice.provider import (
    ProviderCredential,
    ProviderDescriptor,
    RealtimeSessionRequest,
    RealtimeSessionResult,
)

RealtimeJSONTransport = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]

class OpenAIRealtimeError(RuntimeError):
    code = "openai_realtime_error"


class OpenAIRealtimeProvider:
    """Bounded Voice donor adapter using an owner-supplied OpenAI credential."""

    provider_key = "openai"
    descriptor = ProviderDescriptor(
        provider_key="openai", display_name="OpenAI", connection_mode="webrtc",
        protocol="openai-realtime", default_voice_model="gpt-realtime-2.1",
        default_text_model="gpt-5.6-sol", default_voice="marin",
        voices=("marin", "cedar", "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse"),
        voice_models=("gpt-live-1", "gpt-realtime-2.1", "gpt-realtime-2.1-mini"),
        text_models=("gpt-5.6-sol", "gpt-5.6-luna"),
    )

    def __init__(
        self,
        *,
        base_url: str = "https://api.openai.com/v1",
        organization: str | None = None,
        json_transport: RealtimeJSONTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._organization = organization.strip() if organization else None
        self._transport = json_transport or self._default_transport

    def create_realtime_session(
        self, request: RealtimeSessionRequest, *, credential: ProviderCredential
    ) -> RealtimeSessionResult:
        if request.connection_mode != "webrtc":
            raise OpenAIRealtimeError("Browser client-secret creation requires WebRTC mode.")
        if credential.auth_method == "chatgpt_oauth":
            return self._create_chatgpt_session(request, credential)
        url = f"{self._base_url}/realtime/client_secrets"
        headers = {
            "Authorization": f"Bearer {credential.value}",
            "Content-Type": "application/json",
        }
        if self._organization:
            headers["OpenAI-Organization"] = self._organization
        session = build_openai_realtime_session_object(request)
        try:
            response = self._transport(url, headers, {"session": session})
        except httpx.HTTPError as exc:
            raise OpenAIRealtimeError("OpenAI Realtime client-secret request failed.") from exc
        client_secret = response.get("value")
        if not isinstance(client_secret, str) or not client_secret:
            secret_object = response.get("client_secret")
            if isinstance(secret_object, dict):
                client_secret = secret_object.get("value")
        if not isinstance(client_secret, str) or not client_secret:
            raise OpenAIRealtimeError("OpenAI Realtime response did not contain a client secret.")
        expires_at = response.get("expires_at")
        provider_session_id = response.get("id")
        if not isinstance(provider_session_id, str) or not provider_session_id:
            provider_session_id = f"openai-local-request-{uuid4()}"
        return RealtimeSessionResult(
            provider_key=self.provider_key,
            model_key=request.model_key,
            connection_mode=request.connection_mode,
            provider_session_id=provider_session_id,
            session_update_event={"type": "session.update", "session": session},
            client_secret=client_secret,
            expires_at=expires_at if isinstance(expires_at, int) else None,
        )

    def _create_chatgpt_session(
        self, request: RealtimeSessionRequest, credential: ProviderCredential,
    ) -> RealtimeSessionResult:
        offer = normalize_webrtc_sdp(request.offer_sdp or "")
        validate_webrtc_offer(offer)
        session_object = build_openai_realtime_session_object(request)
        answer = self._create_oauth_realtime_call(
            access_token=credential.value,
            offer_sdp=offer,
            session=session_object,
        )
        return RealtimeSessionResult(
            provider_key=self.provider_key, model_key=request.model_key,
            connection_mode=request.connection_mode,
            provider_session_id=request.voice_session_id or f"chatgpt-oauth-{uuid4()}",
            session_update_event={"type": "session.update", "session": session_object},
            sdp_answer=answer,
        )

    @staticmethod
    def _create_oauth_realtime_call(
        *, access_token: str, offer_sdp: str, session: dict[str, Any],
    ) -> str:
        body, content_type = _multipart_form(
            ("sdp", offer_sdp),
            ("session", json.dumps(session, separators=(",", ":"))),
        )
        try:
            response = httpx.post(
                "https://api.openai.com/v1/realtime/calls",
                content=body,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": content_type,
                    "Accept": "application/sdp, text/plain",
                },
                timeout=30.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _provider_error_detail(exc.response)
            if exc.response.status_code in {401, 403}:
                raise OpenAIRealtimeError(
                    "ChatGPT OAuth rejected this Voice session. Reconnect ChatGPT OAuth in Connections."
                ) from exc
            raise OpenAIRealtimeError(
                f"ChatGPT OAuth Voice session failed ({exc.response.status_code}{detail})."
            ) from exc
        except httpx.HTTPError as exc:
            raise OpenAIRealtimeError("ChatGPT OAuth Voice session failed.") from exc
        answer = response.text.strip()
        if not answer.startswith("v=0"):
            try:
                body = response.json()
                answer = str(body.get("sdp") or body.get("answer") or "")
            except Exception:
                answer = ""
        if not answer.startswith("v=0"):
            raise OpenAIRealtimeError("ChatGPT OAuth Voice returned an invalid answer.")
        return answer + ("" if answer.endswith("\r\n") else "\r\n")

    @staticmethod
    def _default_transport(
        url: str, headers: dict[str, str], payload: dict[str, Any]
    ) -> dict[str, Any]:
        response = httpx.post(url, headers=headers, json=payload, timeout=30.0)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise OpenAIRealtimeError("OpenAI Realtime response was not an object.")
        return data


def uses_subscription_live_transport(*, auth_method: str, model_key: str = "") -> bool:
    return False


def normalize_webrtc_sdp(sdp: str) -> str:
    text = sdp.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in text.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    if not lines or not lines[0].startswith("v=0"):
        raise OpenAIRealtimeError("ChatGPT OAuth Voice requires a WebRTC offer.")
    return "\r\n".join(lines) + "\r\n"


def validate_webrtc_offer(sdp: str) -> None:
    if len(sdp) > 262_144:
        raise OpenAIRealtimeError("ChatGPT OAuth Voice offer is too large.")
    if "m=audio" not in sdp:
        raise OpenAIRealtimeError("ChatGPT OAuth Voice offer is missing audio.")


def _provider_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return f": {message.strip()}"
    return ""


def _multipart_form(*fields: tuple[str, str]) -> tuple[bytes, str]:
    boundary = "----ResonoBoundary" + uuid4().hex[:16]
    chunks: list[bytes] = []
    for name, value in fields:
        chunks.extend((
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode(), b"\r\n",
        ))
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def build_openai_realtime_session_object(request: RealtimeSessionRequest) -> dict[str, Any]:
    modalities = tuple(dict.fromkeys(request.output_modalities))
    if not modalities or any(value not in {"audio", "text"} for value in modalities):
        raise OpenAIRealtimeError("Realtime output modalities are invalid.")
    session: dict[str, Any] = {
        "type": "realtime",
        "model": request.model_key,
        "output_modalities": list(modalities),
    }
    if request.instructions:
        session["instructions"] = request.instructions
    audio_input: dict[str, Any] = {}
    if request.audio_format and request.audio_rate:
        audio_input["format"] = {"type": request.audio_format, "rate": request.audio_rate}
    if request.input_noise_reduction_type:
        audio_input["noise_reduction"] = {"type": request.input_noise_reduction_type}
    if request.input_audio_transcription_model:
        audio_input["transcription"] = {"model": request.input_audio_transcription_model}
    if request.turn_detection_type:
        turn_detection: dict[str, Any] = {"type": request.turn_detection_type}
        if request.turn_detection_create_response is not None:
            turn_detection["create_response"] = request.turn_detection_create_response
        if request.turn_detection_interrupt_response is not None:
            turn_detection["interrupt_response"] = request.turn_detection_interrupt_response
        if request.turn_detection_threshold is not None:
            turn_detection["threshold"] = request.turn_detection_threshold
        if request.turn_detection_prefix_padding_ms is not None:
            turn_detection["prefix_padding_ms"] = request.turn_detection_prefix_padding_ms
        if request.turn_detection_silence_duration_ms is not None:
            turn_detection["silence_duration_ms"] = request.turn_detection_silence_duration_ms
        audio_input["turn_detection"] = turn_detection
    audio: dict[str, Any] = {}
    if audio_input:
        audio["input"] = audio_input
    if request.voice:
        output: dict[str, Any] = {"voice": request.voice}
        if request.audio_format and request.audio_rate:
            output["format"] = {"type": request.audio_format, "rate": request.audio_rate}
        audio["output"] = output
    if audio:
        session["audio"] = audio
    if request.tool_definitions:
        session["tools"] = [
            {
                "type": "function",
                "name": str(tool["name"]),
                "description": str(tool["description"]),
                "parameters": tool["parameters"],
            }
            for tool in request.tool_definitions
        ]
    if request.tool_choice:
        session["tool_choice"] = request.tool_choice
    return session
