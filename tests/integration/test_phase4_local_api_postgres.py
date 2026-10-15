from __future__ import annotations

import json
import os

import psycopg
import pytest

from app.core.security.tokens import hash_token
from app.vault_runtime.background_agent.repository import BackgroundRunRepository
from app.vault_runtime.background_agent.service import BackgroundAgentService
from app.vault_runtime.local_api.app import VaultLocalApiApp
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.local_identity.service import LocalIdentityService
from app.vault_runtime.memory.repository import MemoryRepository
from app.vault_runtime.memory.contracts import MemoryCandidate, MemoryReview, ReviewedMemoryCandidate
from app.vault_runtime.memory.voice_learning import VoiceMemoryLearning
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.voice.context import VoiceContextBuilder
from app.vault_runtime.voice.provider import (
    ProviderCredential,
    ProviderRegistry,
    RealtimeSessionResult,
    VoiceSessionCoordinator,
)
from app.vault_runtime.voice.repository import VoiceSessionRepository


class _Health:
    def health(self):
        return {"database": "ok"}


class _Provider:
    provider_key = "test-provider"

    def create_realtime_session(self, request, *, credential):
        assert credential.value == "owner-key"
        return RealtimeSessionResult(
            provider_key=self.provider_key, model_key=request.model_key,
            connection_mode=request.connection_mode, provider_session_id="provider-session",
            session_update_event={"type": "session.update"}, client_secret="ephemeral",
        )


class _Executor:
    def execute(self, request, *, tools, context, progress):
        return {"summary": request.objective}


class _MemoryReviewer:
    def review(self, transcript: str) -> MemoryReview:
        assert "Remember that I prefer tea" in transcript
        assert "I will remember that you prefer tea" in transcript
        return MemoryReview(
            summary="The user prefers tea.", model="test-reviewer", memories=(
                ReviewedMemoryCandidate(MemoryCandidate(
                    subject_id="owner", domain="personal", memory_type="preference",
                    memory_key="drink.tea", content_text="Prefers tea",
                    source_authority="user_asserted", confidence="high",
                    sensitivity="normal", intent="create", visibility="private",
                ), (0,)),
            ),
        )


class _UnusedCredentials:
    pass


@pytest.fixture()
def phase4_app():
    database_url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("VAULT_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
    identity = LocalIdentityService(
        repository=LocalIdentityRepository(database_url=database_url),
        setup_credential_hash=hash_token("setup"),
    )
    identity.ensure_schema()
    tokens = identity.bootstrap_owner(
        setup_credential="setup", username="owner", password="owner-password",
        display_name="Owner", experience_style="funny",
    )
    memories = MemoryRepository(database_url=database_url)
    memories.ensure_schema()
    voices = VoiceSessionRepository(database_url=database_url)
    voices.ensure_schema()
    runs = BackgroundRunRepository(database_url=database_url)
    runs.ensure_schema()
    catalog = ToolCatalog(authorizer=lambda _definition, _context: True)
    coordinator = VoiceSessionCoordinator(
        sessions=voices, contexts=VoiceContextBuilder(memories=memories), tools=catalog,
        providers=ProviderRegistry((_Provider(),)),
    )
    background = BackgroundAgentService(repository=runs, catalog=catalog, executor=_Executor())
    learning = VoiceMemoryLearning(
        memories=memories, sessions=voices, credentials=_UnusedCredentials(),
        reviewer_factory=lambda _user_id, _workspace_id: _MemoryReviewer(),
    )
    app = VaultLocalApiApp(
        store=_Health(), token="unused", identity_service=identity,
        voice_coordinator=coordinator, voice_sessions=voices,
        provider_credential_resolver=lambda _principal, _provider: ProviderCredential("owner-key"),
        background_service=background, background_runs=runs,
        voice_learning=learning,
    )
    headers = {
        "Cookie": f"resono_refresh={tokens.session_token}; resono_csrf={tokens.csrf_token}",
        "X-ReSono-CSRF": tokens.csrf_token,
    }
    yield app, headers
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")


def _post(app, path, payload, headers):
    return app.handle(
        method="POST", target=path, headers=headers,
        body=json.dumps(payload, separators=(",", ":")).encode(),
    )


def test_phase4_api_exposes_only_two_agents_and_voice_lifecycle(phase4_app) -> None:
    app, headers = phase4_app
    inventory = app.handle(method="GET", target="/system-agents", headers=headers)
    assert [item["kind"] for item in inventory.payload["items"]] == ["voice", "background"]
    started = _post(app, "/voice/sessions", {
        "providerKey": "test-provider", "modelKey": "realtime-model",
        "connectionMode": "webrtc", "voice": "alloy",
    }, headers)
    assert started.status_code == 201 and started.payload["clientSecret"] == "ephemeral"
    session_id = started.payload["voiceRealtimeSessionId"]
    closed = _post(app, f"/voice/sessions/{session_id}/close", {}, headers)
    assert closed.payload == {
        "voiceRealtimeSessionId": session_id, "status": "closed",
        "captureState": "unknown",
        "learning": "skipped_empty", "memoryCount": 0,
        "embeddedCount": 0, "embeddingsAvailable": False,
    }


def test_phase4_api_background_submit_read_cancel_and_strict_json(phase4_app) -> None:
    app, headers = phase4_app
    payload = {
        "objective": "Research locally.", "instructionProfile": "default",
        "successCriteria": ["Return a summary."],
        "resultSchema": {"type": "object", "properties": {"summary": {"type": "string"}}},
        "originalRequest": "Research locally.", "verificationMethod": "Check summary.",
        "completionConditions": ["Summary exists."], "requestedToolNames": [],
    }
    created = _post(app, "/background/runs", payload, headers)
    assert created.status_code == 202 and created.payload["agentKind"] == "background"
    run_id = created.payload["runId"]
    read = app.handle(method="GET", target=f"/background/runs/{run_id}", headers=headers)
    assert read.payload["state"] == "queued"
    cancelled = _post(app, f"/background/runs/{run_id}/cancel", {}, headers)
    assert cancelled.payload["cancellationRequested"] is True

    unsafe = app.handle(
        method="POST", target="/background/runs", headers=headers,
        body=b'{"objective":"one","objective":"two"}',
    )
    assert unsafe.status_code == 400


def test_voice_api_captures_final_event_and_learns_on_close(phase4_app) -> None:
    app, headers = phase4_app
    started = _post(app, "/voice/sessions", {
        "providerKey": "test-provider", "modelKey": "realtime-model",
        "connectionMode": "webrtc", "voice": "alloy",
    }, headers)
    session_id = started.payload["voiceRealtimeSessionId"]
    captured = _post(app, f"/voice/sessions/{session_id}/events", {
        "providerEventId": "user-final-1",
        "eventType": "conversation.item.input_audio_transcription.completed",
        "role": "user", "transcriptText": "Remember that I prefer tea",
        "transcriptEntryIndex": 0,
        "providerPayload": {"type": "conversation.item.input_audio_transcription.completed"},
    }, headers)
    assert captured.status_code == 201 and captured.payload["accepted"] is True
    replay = _post(app, f"/voice/sessions/{session_id}/events", {
        "providerEventId": "user-final-1",
        "eventType": "conversation.item.input_audio_transcription.completed",
        "role": "user", "transcriptText": "Remember that I prefer tea",
        "transcriptEntryIndex": 0,
        "providerPayload": {"type": "conversation.item.input_audio_transcription.completed"},
    }, headers)
    assert replay.status_code == 200 and replay.payload["accepted"] is False
    assistant = _post(app, f"/voice/sessions/{session_id}/events", {
        "providerEventId": "assistant-final-1",
        "eventType": "response.output_audio_transcript.done",
        "role": "assistant", "transcriptText": "I will remember that you prefer tea",
        "transcriptEntryIndex": 1,
        "providerPayload": {"type": "response.output_audio_transcript.done"},
    }, headers)
    assert assistant.status_code == 201 and assistant.payload["accepted"] is True
    closed = _post(app, f"/voice/sessions/{session_id}/close", {}, headers)
    assert closed.payload["learning"] == "completed"
    assert closed.payload["memoryCount"] == 1
    retried = _post(app, f"/voice/sessions/{session_id}/finalize", {}, headers)
    assert retried.status_code == 200
    assert retried.payload["learning"] == "already_completed"
    assert retried.payload["summary"] == "The user prefers tea."
