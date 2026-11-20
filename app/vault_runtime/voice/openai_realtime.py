from __future__ import annotations

import json
import logging
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

logger = logging.getLogger(__name__)

LIVE_SESSIONS_URL = "https://api.openai.com/v1/live/sessions"
# GPT-Live on a ChatGPT sign-in runs through Codex's voice broker, as Codex itself and other
# subscription clients do (hermes-talk, hermes-live-voice): its own model id, client delegation
# only (Vault's agent does the work), and its own sideband.
SUBSCRIPTION_LIVE_URL = "https://chatgpt.com/backend-api/codex/realtime/calls?intent=quicksilver&architecture=avas"
SUBSCRIPTION_LIVE_MODEL = "gpt-live-1-codex"
SUBSCRIPTION_LIVE_SIDEBAND = "wss://api.openai.com/v1/live/{call_id}"
SUBSCRIPTION_LIVE_VOICES = ("arbor", "breeze", "cove", "ember", "juniper", "maple", "sol", "spruce", "vale")
DEFAULT_SUBSCRIPTION_LIVE_VOICE = "sol"
DEFAULT_LIVE_DELEGATION_MODEL = "gpt-5.6-luna"


def is_live_model(model_key: str) -> bool:
    """GPT-Live conversation models (gpt-live-1, gpt-live-1-codex) run on the Live API, not on Realtime.
    Not gpt-live-transcribe: that transcription model stays on Realtime (live memory's words)."""
    model = str(model_key or "")
    return model == "gpt-live-1" or model.startswith("gpt-live-1-")

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
        if is_live_model(request.model_key) and request.server_controlled and request.session_type == "realtime":
            # Link calls: the Live API (Vault's tools as the backend). If OpenAI does not offer it to
            # this credential, the call falls back to the Realtime endpoint as before.
            try:
                return self._create_live_session(request, credential)
            except OpenAIRealtimeError as exc:
                if not getattr(exc, "fallback", False):
                    raise
                logger.info("openai_live_fallback_realtime reason=%s", str(exc)[:200])
        if request.server_controlled:
            return self._create_server_call(request, credential)
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

    def _create_server_call(
        self, request: RealtimeSessionRequest, credential: ProviderCredential,
    ) -> RealtimeSessionResult:
        """Create the call with Vault's credential (API key or ChatGPT sign-in) and keep its call_id."""
        offer = normalize_webrtc_sdp(request.offer_sdp or "")
        validate_webrtc_offer(offer)
        session_object = build_openai_realtime_session_object(request)
        answer, call_id = self._realtime_call(access_token=credential.value, offer_sdp=offer,
                                              session=session_object, organization=self._organization)
        if not call_id:
            raise OpenAIRealtimeError("OpenAI Realtime did not return a call id.")
        return RealtimeSessionResult(
            provider_key=self.provider_key, model_key=request.model_key,
            connection_mode=request.connection_mode, provider_session_id=call_id,
            session_update_event={"type": "session.update", "session": session_object},
            sdp_answer=answer, call_id=call_id,
        )

    @staticmethod
    def _create_oauth_realtime_call(
        *, access_token: str, offer_sdp: str, session: dict[str, Any],
    ) -> str:
        return OpenAIRealtimeProvider._realtime_call(access_token=access_token, offer_sdp=offer_sdp, session=session)[0]

    @staticmethod
    def _realtime_call(
        *, access_token: str, offer_sdp: str, session: dict[str, Any], organization: str | None = None,
    ) -> tuple[str, str | None]:
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
                    **({"OpenAI-Organization": organization} if organization else {}),
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
        location = response.headers.get("location") or ""
        call_id = location.rstrip("/").rsplit("/", 1)[-1] if location else None
        if call_id is not None and not (0 < len(call_id) <= 128
                                        and call_id.replace("_", "").replace("-", "").isalnum()):
            call_id = None
        return answer + ("" if answer.endswith("\r\n") else "\r\n"), call_id

    def _create_live_session(
        self, request: RealtimeSessionRequest, credential: ProviderCredential,
    ) -> RealtimeSessionResult:
        """GPT-Live (OpenAI "Getting started with GPT-Live", "WebRTC"): POST /v1/live/sessions with the
        session and the phone's WebRTC offer; returns the session id and SDP answer. The live model only
        talks; Vault's Voice tools go to the Responses backend, and Vault runs each call they make."""
        offer = normalize_webrtc_sdp(request.offer_sdp or "")
        validate_webrtc_offer(offer)
        if credential.auth_method == "chatgpt_oauth":
            return self._create_subscription_live_call(request, credential, offer)
        session = build_openai_live_session_object(request)
        headers = {"Authorization": f"Bearer {credential.value}", "Content-Type": "application/json",
                   **({"OpenAI-Organization": self._organization} if self._organization else {})}
        try:
            response = httpx.post(LIVE_SESSIONS_URL, headers=headers, timeout=30.0,
                                  json={"session": session, "transport": {"type": "webrtc", "sdp": offer}})
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            detail = _provider_error_detail(exc.response)
            error = OpenAIRealtimeError(f"GPT-Live session failed ({exc.response.status_code}{detail}).")
            # Not offered to this credential or endpoint: let the Realtime path try.
            error.fallback = exc.response.status_code in {401, 403, 404}
            raise error from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise OpenAIRealtimeError("GPT-Live session failed.") from exc
        session_id = str(((body or {}).get("session") or {}).get("id") or "")
        answer = str(((body or {}).get("transport") or {}).get("sdp") or "")
        if not answer.startswith("v=0"):
            raise OpenAIRealtimeError("GPT-Live returned an invalid answer.")
        if not (0 < len(session_id) <= 128 and session_id.replace("_", "").replace("-", "").isalnum()):
            raise OpenAIRealtimeError("GPT-Live did not return a session id.")
        return RealtimeSessionResult(
            provider_key=self.provider_key, model_key=request.model_key,
            connection_mode=request.connection_mode, provider_session_id=session_id,
            session_update_event={"type": "session.update", "session": session},
            sdp_answer=answer + ("" if answer.endswith("\r\n") else "\r\n"),
            call_id=session_id, protocol="openai-live",
        )

    def _create_subscription_live_call(
        self, request: RealtimeSessionRequest, credential: ProviderCredential, offer: str,
    ) -> RealtimeSessionResult:
        """GPT-Live on the ChatGPT sign-in: Codex's voice broker returns the SDP answer and the call id;
        the live model hands work to Vault (client delegation), which runs it with its own agent and tools."""
        account = chatgpt_account_id(credential.value)
        if not account:
            raise OpenAIRealtimeError("ChatGPT sign-in has no account id; reconnect ChatGPT in Connections.")
        headers = {"Authorization": f"Bearer {credential.value}", "Content-Type": "application/json",
                   "OpenAI-Alpha": "quicksilver=v2", "chatgpt-account-id": account,
                   "session-id": str(uuid4()), "thread-id": str(uuid4()), "x-session-id": str(uuid4())}
        session = build_subscription_live_session_object(request)
        try:
            response = httpx.post(SUBSCRIPTION_LIVE_URL, headers=headers, timeout=30.0,
                                  json={"sdp": offer, "session": session})
            if response.status_code == 400 and "input" in session:
                # The broker is not the public Live API; if it refuses the startup greeting message,
                # start without it (the greeting is still sent after session.started).
                logger.info("openai_live_broker_input_refused")
                session = {k: v for k, v in session.items() if k != "input"}
                response = httpx.post(SUBSCRIPTION_LIVE_URL, headers=headers, timeout=30.0,
                                      json={"sdp": offer, "session": session})
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _provider_error_detail(exc.response)
            raise OpenAIRealtimeError(f"GPT-Live (ChatGPT) session failed ({exc.response.status_code}{detail}).") from exc
        except httpx.HTTPError as exc:
            raise OpenAIRealtimeError("GPT-Live (ChatGPT) session failed.") from exc
        answer = response.text.strip()
        if not answer.startswith("v=0"):
            raise OpenAIRealtimeError("GPT-Live returned an invalid answer.")
        call_id = _subscription_call_id(response.headers)
        if not call_id:
            raise OpenAIRealtimeError("GPT-Live did not return a call id.")
        return RealtimeSessionResult(
            provider_key=self.provider_key, model_key=request.model_key,
            connection_mode=request.connection_mode, provider_session_id=call_id,
            session_update_event={"type": "session.update", "session": session},
            sdp_answer=answer + ("" if answer.endswith("\r\n") else "\r\n"),
            call_id=call_id, protocol="openai-live-client",
            sideband_url=SUBSCRIPTION_LIVE_SIDEBAND.format(call_id=call_id),
            sideband_headers={k: v for k, v in headers.items() if k != "Content-Type"},
        )

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


def live_function_tools(definitions) -> list[dict[str, Any]]:
    """Vault's Voice tools as Responses function tools for the GPT-Live backend (never strict: Vault's
    schemas are not all strict-compatible, and Vault validates every call's arguments itself)."""
    tools = []
    for item in definitions or ():
        if not isinstance(item, dict) or item.get("type") != "function" or not item.get("name"):
            continue
        tools.append({"type": "function", "name": item["name"], "description": str(item.get("description") or "")[:4000],
                      "parameters": item.get("parameters") or {"type": "object", "properties": {}}, "strict": False})
    return tools


def build_openai_live_session_object(request: RealtimeSessionRequest) -> dict[str, Any]:
    """The GPT-Live session: a short conversation prompt for the live model, and Vault's full Voice
    instructions and tools for the Responses backend it delegates to. WebRTC negotiates audio, so no
    audio format; GPT-Live has no turn detection (it listens while speaking)."""
    from app.vault_runtime.voice.instructions import LIVE_BACKEND_PREAMBLE, live_voice_instructions
    from app.vault_runtime.voice.greeting import live_greeting_input
    greeting = live_greeting_input(request.display_name)
    return {
        "model": request.model_key,
        "instructions": live_voice_instructions(_shared_prompt(request)),
        **({"input": greeting} if greeting else {}),
        "delegation": {"type": "responses", "responses": {
            "model": request.delegation_model or DEFAULT_LIVE_DELEGATION_MODEL,
            "instructions": LIVE_BACKEND_PREAMBLE + (request.instructions or ""),
            "tools": live_function_tools(request.tool_definitions),
            "tool_choice": "auto",
            "parallel_tool_calls": False,
        }},
    }


def chatgpt_account_id(access_token: str) -> str:
    """The ChatGPT account id carried in the sign-in's access token (its auth claim)."""
    import base64
    try:
        part = access_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        value = (claims.get("https://api.openai.com/auth") or {}).get("chatgpt_account_id") or ""
    except Exception:
        return ""
    value = str(value)
    return value if 0 < len(value) <= 128 and value.replace("-", "").replace("_", "").isalnum() else ""


def _subscription_call_id(headers) -> str:
    """The broker's call id: its openai-session-id header, or the last segment of its location."""
    def ok(value: str) -> bool:
        return 0 < len(value) <= 128 and value.replace("_", "").replace("-", "").isalnum()
    session_id = str(headers.get("openai-session-id") or "")
    location = str(headers.get("location") or "")
    candidate = location.split("?")[0].rstrip("/").rsplit("/", 1)[-1] if location else ""
    if ok(candidate):
        return candidate
    return session_id if ok(session_id) else ""


def _shared_prompt(request: RealtimeSessionRequest) -> str:
    """The shared Voice prompt; a request built without it falls back to a minimal one with the name."""
    if request.conversation_instructions:
        return request.conversation_instructions
    from app.vault_runtime.voice.instructions import PRIMARY_VOICE_INSTRUCTIONS
    name = (request.display_name or "").strip()
    return PRIMARY_VOICE_INSTRUCTIONS + (f"\n\nAccount Profile Context:\n- User display name: {name}" if name else "")


def build_subscription_live_session_object(request: RealtimeSessionRequest) -> dict[str, Any]:
    """GPT-Live on the ChatGPT sign-in: the short conversation prompt with the greeting (the
    session is configured at call time), the subscription voice, and client delegation."""
    from app.vault_runtime.voice.instructions import live_voice_instructions
    # The greeting is sent as speakable context once the phone's audio is up (companion).
    instructions = live_voice_instructions(_shared_prompt(request))
    from app.vault_runtime.voice.greeting import live_greeting_input
    greeting = live_greeting_input(request.display_name)
    voice = (request.voice or "").lower()
    return {
        "model": SUBSCRIPTION_LIVE_MODEL,
        "instructions": instructions,
        "audio": {"output": {"voice": voice if voice in SUBSCRIPTION_LIVE_VOICES else DEFAULT_SUBSCRIPTION_LIVE_VOICE}},
        "delegation": {"type": "client"},
        **({"input": greeting} if greeting else {}),
    }


def build_openai_realtime_session_object(request: RealtimeSessionRequest) -> dict[str, Any]:
    if request.session_type=="transcription":
        transcription={"model":request.input_audio_transcription_model}
        if request.input_audio_transcription_delay:
            transcription["delay"]=request.input_audio_transcription_delay
        return {"type":"transcription","audio":{"input":{"transcription":transcription,"turn_detection":None}}}
    if request.session_type!="realtime":
        raise OpenAIRealtimeError("Unsupported Realtime session type.")
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
