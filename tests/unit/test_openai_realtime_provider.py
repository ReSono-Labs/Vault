from app.vault_runtime.voice.openai_realtime import (
    OpenAIRealtimeError,
    OpenAIRealtimeProvider,
    build_openai_realtime_session_object,
    normalize_webrtc_sdp,
    uses_subscription_live_transport,
)


def test_openai_background_text_models_include_luna() -> None:
    assert OpenAIRealtimeProvider.descriptor.default_text_model == "gpt-5.6-sol"
    assert OpenAIRealtimeProvider.descriptor.text_models == ("gpt-5.6-sol", "gpt-5.6-luna")
from app.vault_runtime.voice.provider import ProviderCredential, RealtimeSessionRequest


def test_openai_realtime_uses_owner_credential_and_donor_payload() -> None:
    captured = {}

    def transport(url, headers, payload):
        captured.update(url=url, headers=headers, payload=payload)
        return {"id": "provider-session", "value": "ephemeral", "expires_at": 123}

    provider = OpenAIRealtimeProvider(json_transport=transport)
    result = provider.create_realtime_session(
        RealtimeSessionRequest(
            model_key="gpt-realtime", connection_mode="webrtc",
            instructions="Local scoped instructions.", voice="alloy",
            tool_definitions=({
                "type": "function", "name": "memory_lookup", "description": "Look up memory.",
                "parameters": {"type": "object", "properties": {}},
            },),
            input_audio_transcription_model="gpt-4o-mini-transcribe",
            turn_detection_type="server_vad", turn_detection_create_response=True,
            turn_detection_interrupt_response=False,
            audio_format="audio/pcm", audio_rate=24_000,
            input_noise_reduction_type="near_field",
            turn_detection_threshold=0.92,
            turn_detection_prefix_padding_ms=500,
            turn_detection_silence_duration_ms=1_200,
            tool_choice="auto",
        ),
        credential=ProviderCredential("owner-secret"),
    )
    assert captured["url"] == "https://api.openai.com/v1/realtime/client_secrets"
    assert captured["headers"]["Authorization"] == "Bearer owner-secret"
    assert "owner-secret" not in str(captured["payload"])
    assert captured["payload"]["session"]["tools"][0]["name"] == "memory_lookup"
    session = captured["payload"]["session"]
    assert session["audio"]["input"]["format"] == {"type": "audio/pcm", "rate": 24_000}
    assert session["audio"]["input"]["noise_reduction"] == {"type": "near_field"}
    assert session["audio"]["input"]["turn_detection"] == {
        "type": "server_vad", "create_response": True, "interrupt_response": False,
        "threshold": 0.92, "prefix_padding_ms": 500, "silence_duration_ms": 1_200,
    }
    assert session["tool_choice"] == "auto"
    assert result.client_secret == "ephemeral" and result.provider_session_id == "provider-session"


def test_normalize_webrtc_sdp_preserves_trailing_line_terminator() -> None:
    normalized = normalize_webrtc_sdp("v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n")
    assert normalized.endswith("\r\n")
    assert "m=audio" in normalized


def test_normalize_webrtc_sdp_repairs_stripped_offer() -> None:
    stripped = "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111"
    normalized = normalize_webrtc_sdp(stripped)
    assert normalized.endswith("\r\n")
    assert normalized.startswith("v=0\r\n")


def test_oauth_uses_the_standard_data_channel() -> None:
    assert not uses_subscription_live_transport(auth_method="chatgpt_oauth", model_key="gpt-live-1")
    assert not uses_subscription_live_transport(auth_method="chatgpt_oauth", model_key="gpt-realtime-2.1")
    assert not uses_subscription_live_transport(auth_method="api_key", model_key="gpt-live-1")


def test_chatgpt_oauth_uses_codex_transport(monkeypatch) -> None:
    captured = {}

    class Response:
        text = "v=0\r\no=answer"
        headers = {}

        @staticmethod
        def raise_for_status():
            return None

    def post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return Response()

    monkeypatch.setattr("app.vault_runtime.voice.openai_realtime.httpx.post", post)
    offer = "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"
    result = OpenAIRealtimeProvider().create_realtime_session(
        RealtimeSessionRequest(
            model_key="gpt-live-1", connection_mode="webrtc",
            instructions="Vault context.", voice="Sol", offer_sdp=offer,
            voice_session_id="voice-session-123",
            tool_definitions=({
                "type": "function", "name": "memory_lookup", "description": "Look up memory.",
                "parameters": {"type": "object", "properties": {}},
            },),
        ),
        credential=ProviderCredential("oauth-token", auth_method="chatgpt_oauth"),
    )
    assert captured["url"] == "https://api.openai.com/v1/realtime/calls"
    assert captured["headers"]["Authorization"] == "Bearer oauth-token"
    assert captured["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    body = captured["content"].decode()
    assert '"model":"gpt-live-1"' in body
    assert '"name":"memory_lookup"' in body
    assert result.sdp_answer.startswith("v=0")
    assert result.client_secret is None
    assert result.protocol == "openai-realtime"
    assert result.session_update_event["type"] == "session.update"
    assert result.session_update_event["session"]["tools"][0]["name"] == "memory_lookup"


def test_live_transcription_session_requests_low_delay_and_client_commit() -> None:
    session = build_openai_realtime_session_object(RealtimeSessionRequest(
        model_key="gpt-live-transcribe", connection_mode="webrtc", session_type="transcription",
        input_audio_transcription_model="gpt-live-transcribe", input_audio_transcription_delay="low"))
    assert session == {"type": "transcription", "audio": {"input": {
        "transcription": {"model": "gpt-live-transcribe", "delay": "low"}, "turn_detection": None}}}


def test_server_controlled_call_uses_vault_credential_and_keeps_call_id(monkeypatch) -> None:
    """Link Companion: either credential creates the call server-side; no client secret is produced."""
    captured = []

    class Response:
        text = "v=0\r\no=answer"
        headers = {"location": "/v1/realtime/calls/rtc_abc123"}

        @staticmethod
        def raise_for_status():
            return None

    def post(url, **kwargs):
        captured.append((url, kwargs["headers"]["Authorization"]))
        return Response()

    monkeypatch.setattr("app.vault_runtime.voice.openai_realtime.httpx.post", post)
    offer = "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"
    for credential in (ProviderCredential("sk-key", auth_method="api_key"),
                       ProviderCredential("oauth-token", auth_method="chatgpt_oauth")):
        result = OpenAIRealtimeProvider().create_realtime_session(
            RealtimeSessionRequest(model_key="gpt-realtime", connection_mode="webrtc", offer_sdp=offer,
                                   server_controlled=True), credential=credential)
        assert result.call_id == "rtc_abc123" and result.provider_session_id == "rtc_abc123"
        assert result.client_secret is None and result.sdp_answer.startswith("v=0")
    assert captured == [("https://api.openai.com/v1/realtime/calls", "Bearer sk-key"),
                        ("https://api.openai.com/v1/realtime/calls", "Bearer oauth-token")]
