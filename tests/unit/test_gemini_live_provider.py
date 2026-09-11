from app.vault_runtime.voice.gemini_live import GeminiLiveProvider
from app.vault_runtime.voice.provider import ProviderCredential, RealtimeSessionRequest


def test_gemini_live_mints_constrained_ephemeral_session() -> None:
    observed = {}

    def transport(url, headers, payload):
        observed.update(url=url, headers=headers, payload=payload)
        return {"name": "ephemeral-token"}

    result = GeminiLiveProvider(json_transport=transport).create_realtime_session(
        RealtimeSessionRequest(
            model_key="gemini-live", connection_mode="provider-websocket",
            instructions="Vault context", voice="Kore",
            tool_definitions=({"name": "memory_search", "description": "Search", "parameters": {"type": "object"}},),
        ), credential=ProviderCredential("google-key"),
    )
    assert observed["headers"]["x-goog-api-key"] == "google-key"
    constraints = observed["payload"]["liveConnectConstraints"]
    assert constraints["model"] == "models/gemini-live"
    assert constraints["config"]["systemInstruction"]["parts"][0]["text"] == "Vault context"
    assert result.client_secret == "ephemeral-token"
    assert result.protocol == "google-live-bidi"
    assert result.websocket_url.startswith("wss://generativelanguage.googleapis.com/")

