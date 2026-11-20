from app.vault_runtime.voice.provider import ProviderCredential, RealtimeSessionRequest
from app.vault_runtime.voice.xai_realtime import XAIRealtimeProvider


def test_xai_realtime_mints_browser_secret_and_session_update() -> None:
    observed = {}

    def transport(url, headers, payload):
        observed.update(url=url, headers=headers, payload=payload)
        return {"id": "secret-1", "value": "ephemeral-xai", "expires_at": 42}

    result = XAIRealtimeProvider(json_transport=transport).create_realtime_session(
        RealtimeSessionRequest(
            model_key="grok-voice-latest", connection_mode="provider-websocket",
            instructions="Vault context", voice="eve", audio_format="audio/pcm", audio_rate=24_000,
        ), credential=ProviderCredential("xai-key"),
    )
    assert observed["url"].endswith("/realtime/client_secrets")
    assert observed["headers"]["Authorization"] == "Bearer xai-key"
    assert result.client_secret == "ephemeral-xai"
    assert result.websocket_protocol == "xai-client-secret.ephemeral-xai"
    assert result.session_update_event["session"]["instructions"] == "Vault context"
