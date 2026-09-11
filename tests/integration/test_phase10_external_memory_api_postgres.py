from __future__ import annotations

import json
import os

import psycopg
import pytest

from app.core.security.tokens import hash_token
from app.vault_runtime.external_memory.repository import ExternalMemoryRepository
from app.vault_runtime.external_memory.service import ExternalMemoryService
from app.vault_runtime.local_api.app import VaultLocalApiApp
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.local_identity.service import LocalIdentityService
from app.vault_runtime.memory.pipeline import FinalizeResult
from app.vault_runtime.memory.contracts import MemoryCandidate
from app.vault_runtime.memory.repository import MemoryRepository
from app.vault_runtime.memory.service import MemoryService


class Health:
    def health(self):
        return {"database": "ok"}


@pytest.fixture()
def external_memory_api():
    database_url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("VAULT_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
    identities = LocalIdentityService(
        repository=LocalIdentityRepository(database_url=database_url),
        setup_credential_hash=hash_token("setup"),
    )
    identities.ensure_schema()
    tokens = identities.bootstrap_owner(
        setup_credential="setup", username="owner", password="owner-password",
        display_name="Owner", experience_style="strict",
    )
    memories = MemoryRepository(database_url=database_url)
    memories.ensure_schema()
    owner_entry = memories.append_transcript(
        user_id=tokens.principal.user_id, workspace_id=tokens.principal.workspace_id,
        voice_session_id="owner-session", entry_index=0, role="user",
        event_type="test", text_content="Owner likes long reports.",
    )
    owner_memory = memories.reconcile_memory(
        user_id=tokens.principal.user_id, workspace_id=tokens.principal.workspace_id,
        voice_session_id="owner-session",
        candidate=MemoryCandidate(
            subject_id=tokens.principal.user_id, domain="personal", memory_type="preference",
            memory_key="report-length", content_text="Owner likes long reports.",
            source_authority="user_asserted", confidence="high", sensitivity="normal",
            intent="create", visibility="private",
        ),
        evidence=((owner_entry.entry_id, "user_statement", "user_asserted", owner_entry.text_content),),
    )
    other_user_id, other_workspace_id = identities.create_user(
        actor=tokens.principal, username="other", password="other-password",
        display_name="Other", experience_style="strict",
    )
    other_entry = memories.append_transcript(
        user_id=other_user_id, workspace_id=other_workspace_id,
        voice_session_id="other-session", entry_index=0, role="user",
        event_type="test", text_content="Private other-user fact.",
    )
    foreign_memory = memories.reconcile_memory(
        user_id=other_user_id, workspace_id=other_workspace_id,
        voice_session_id="other-session",
        candidate=MemoryCandidate(
            subject_id=other_user_id, domain="personal", memory_type="fact",
            memory_key="private-other", content_text="Private other-user fact.",
            source_authority="user_asserted", confidence="high", sensitivity="normal",
            intent="create", visibility="private",
        ),
        evidence=((other_entry.entry_id, "user_statement", "user_asserted", other_entry.text_content),),
    )
    integrations = ExternalMemoryRepository(database_url=database_url)
    integrations.ensure_schema()

    def finalize(user_id: str, workspace_id: str, session_id: str) -> FinalizeResult:
        assert memories.transcript_entries(
            user_id=user_id, workspace_id=workspace_id, voice_session_id=session_id,
        )[0].event_type == "external_memory_proposal"
        return FinalizeResult(session_id, "reviewed", 0, 0, "test-reviewer", False)

    service = ExternalMemoryService(
        integrations=integrations, memories=memories,
        memory_service=MemoryService(repository=memories), finalize=finalize,
    )
    app = VaultLocalApiApp(
        store=Health(), token="unused", identity_service=identities,
        external_memory_integrations=integrations, external_memory=service,
    )
    headers = {
        "Cookie": f"resono_refresh={tokens.session_token}; resono_csrf={tokens.csrf_token}",
        "X-ReSono-CSRF": tokens.csrf_token,
    }
    yield app, headers, foreign_memory.memory_id, owner_memory.memory_id, memories, tokens
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")


def _post(app, path: str, payload: dict, headers: dict):
    return app.handle(
        method="POST", target=path, headers=headers,
        body=json.dumps(payload, separators=(",", ":")).encode(),
    )


def test_enrollment_returns_credential_once_and_scope_is_server_derived(external_memory_api) -> None:
    app, owner_headers, foreign_memory_id, _owner_memory_id, _memories, _tokens = external_memory_api
    enrolled = _post(app, "/external-memory/integrations", {
        "displayName": "Hermes", "adapterKind": "hermes", "grants": ["search", "propose"],
    }, owner_headers)
    assert enrolled.status_code == 201
    credential = enrolled.payload["credential"]
    listed = app.handle(method="GET", target="/external-memory/integrations", headers=owner_headers)
    assert listed.status_code == 200
    assert "credential" not in listed.payload["items"][0]

    adapter_headers = {"Authorization": f"Bearer {credential}"}
    searched = _post(app, "/external-memory/v1/search", {
        "requestId": "search-1", "query": "project",
        "userId": "attacker-selected", "workspaceId": "attacker-selected",
    }, adapter_headers)
    assert searched.status_code == 200
    startup = _post(app, "/external-memory/v1/startup", {
        "requestId": "startup-1", "limit": 8,
    }, adapter_headers)
    assert startup.status_code == 200
    assert [item["memoryId"] for item in startup.payload["items"]] == [_owner_memory_id]
    assert startup.payload["items"][0]["sensitivity"] == "normal"
    cross_scope = _post(app, "/external-memory/v1/get", {
        "requestId": "get-foreign", "memoryId": foreign_memory_id,
    }, adapter_headers)
    assert cross_scope.status_code == 403
    replay = _post(app, "/external-memory/v1/search", {
        "requestId": "search-1", "query": "project",
    }, adapter_headers)
    assert replay.status_code == 403
    assert replay.payload["error"]["code"] == "external_memory_request_replayed"


def test_local_pairing_binds_plugin_generated_credential(external_memory_api) -> None:
    app, owner_headers, _foreign_memory_id, _owner_memory_id, _memories, _tokens = external_memory_api
    runtime_credential = "plugin-generated-runtime-credential"
    started = _post(app, "/external-memory/pairing/start", {
        "displayName": "Hermes", "adapterKind": "hermes",
        "grants": ["search", "propose", "correct", "forget"],
        "pollToken": "private-poll-token", "runtimeTokenHash": hash_token(runtime_credential),
    }, {})
    assert started.status_code == 201
    pending = _post(app, "/external-memory/pairing/status", {
        "pairingId": started.payload["pairingId"], "pollToken": "private-poll-token",
    }, {})
    assert pending.payload == {"status": "pending"}
    detail = app.handle(
        method="GET",
        target=f"/external-memory/integrations/pairing/{started.payload['pairingCode']}",
        headers=owner_headers,
    )
    assert detail.status_code == 200
    approved = _post(
        app,
        f"/external-memory/integrations/pairing/{started.payload['pairingId']}/approve",
        {}, owner_headers,
    )
    assert approved.status_code == 200
    status = _post(app, "/external-memory/pairing/status", {
        "pairingId": started.payload["pairingId"], "pollToken": "private-poll-token",
    }, {})
    assert status.payload == {"status": "approved"}
    searched = _post(app, "/external-memory/v1/search", {
        "requestId": "paired-search", "query": "reports",
    }, {"Authorization": f"Bearer {runtime_credential}"})
    assert searched.status_code == 200


def test_grants_bounds_proposal_and_immediate_revocation(external_memory_api) -> None:
    app, owner_headers, _foreign_memory_id, _owner_memory_id, _memories, _tokens = external_memory_api
    enrolled = _post(app, "/external-memory/integrations", {
        "displayName": "Hermes", "adapterKind": "hermes", "grants": ["propose"],
    }, owner_headers)
    credential = enrolled.payload["credential"]
    adapter_headers = {"Authorization": f"Bearer {credential}"}

    denied = _post(app, "/external-memory/v1/search", {
        "requestId": "wrong-grant", "query": "anything",
    }, adapter_headers)
    assert denied.status_code == 403
    oversized = _post(app, "/external-memory/v1/propose", {
        "requestId": "too-large", "content": "x" * 4097,
    }, adapter_headers)
    assert oversized.status_code == 400
    proposed = _post(app, "/external-memory/v1/propose", {
        "requestId": "proposal-1", "content": "The owner prefers concise reports.",
        "evidence": "The owner explicitly stated this preference.",
    }, adapter_headers)
    assert proposed.status_code == 202
    assert proposed.payload["status"] == "reviewed"

    revoked = _post(
        app, f"/external-memory/integrations/{enrolled.payload['integrationId']}/revoke",
        {}, owner_headers,
    )
    assert revoked.payload == {"status": "revoked"}
    after_revoke = _post(app, "/external-memory/v1/propose", {
        "requestId": "proposal-2", "content": "Should not be accepted.",
    }, adapter_headers)
    assert after_revoke.status_code == 403
    removed = app.handle(
        method="DELETE",
        target=f"/external-memory/integrations/{enrolled.payload['integrationId']}",
        headers=owner_headers, body=b"{}",
    )
    assert removed.payload == {"status": "removed"}


def test_agent_disconnect_is_idempotent_and_revokes_runtime_access(external_memory_api) -> None:
    app, owner_headers, _foreign_memory_id, _owner_memory_id, _memories, _tokens = external_memory_api
    enrolled = _post(app, "/external-memory/integrations", {
        "displayName": "OpenClaw", "adapterKind": "openclaw", "grants": ["search"],
    }, owner_headers)
    adapter_headers = {"Authorization": f"Bearer {enrolled.payload['credential']}"}
    disconnected = _post(app, "/external-memory/v1/disconnect", {
        "requestId": "disconnect-1",
    }, adapter_headers)
    assert disconnected.payload["status"] == "revoked"
    repeated = _post(app, "/external-memory/v1/disconnect", {
        "requestId": "disconnect-2",
    }, adapter_headers)
    assert repeated.payload["status"] == "revoked"
    denied = _post(app, "/external-memory/v1/search", {
        "requestId": "after-disconnect", "query": "reports",
    }, adapter_headers)
    assert denied.status_code == 403


def test_granted_external_correction_and_forget_apply_without_extra_approval(external_memory_api) -> None:
    app, owner_headers, _foreign_id, owner_memory_id, memories, tokens = external_memory_api
    enrolled = _post(app, "/external-memory/integrations", {
        "displayName": "Hermes", "adapterKind": "hermes",
        "grants": ["correct", "forget"],
    }, owner_headers)
    adapter_headers = {"Authorization": f"Bearer {enrolled.payload['credential']}"}
    correction = _post(app, "/external-memory/v1/request-correction", {
        "requestId": "correct-1", "memoryId": owner_memory_id,
        "newContent": "Owner prefers concise reports.",
    }, adapter_headers)
    assert correction.status_code == 200
    assert correction.payload["status"] == "applied"
    after = memories.memory(
        user_id=tokens.principal.user_id, workspace_id=tokens.principal.workspace_id,
        memory_id=owner_memory_id,
    )
    assert after.content_text == "Owner prefers concise reports."

    forgetting = _post(app, "/external-memory/v1/request-forget", {
        "requestId": "forget-1", "memoryId": owner_memory_id,
    }, adapter_headers)
    assert forgetting.status_code == 200
    assert forgetting.payload["status"] == "applied"
    with pytest.raises(Exception) as missing:
        memories.memory(
            user_id=tokens.principal.user_id, workspace_id=tokens.principal.workspace_id,
            memory_id=owner_memory_id,
        )
    assert getattr(missing.value, "code", "") == "memory_not_found"
