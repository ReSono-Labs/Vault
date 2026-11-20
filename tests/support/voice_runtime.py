"""Shared test helpers moved out of test modules (TST-01)."""

from __future__ import annotations

from app.vault_runtime.voice.repository import VoiceSessionRepository


def _new_session(voices: VoiceSessionRepository, principal):
    return voices.create_session(
        user_id=principal.user_id, workspace_id=principal.workspace_id,
        local_session_id=principal.session_id, provider_key="openai",
        model_key="realtime-model", connection_mode="webrtc",
    )
