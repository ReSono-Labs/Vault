"""Shared integration fixtures moved out of test modules (TST-01)."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import psycopg
import pytest

from app.core.security.tokens import hash_token
from app.vault_runtime.background_agent.repository import BackgroundRunRepository
from app.vault_runtime.composition import build_local_app
from app.vault_runtime.decision_routing.diagnostics import LiveDiagnostics
from app.vault_runtime.local_api.config import VaultLocalApiConfig
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.local_identity.service import LocalIdentityService
from app.vault_runtime.memory.openai_reviewer import OpenAIMemoryReviewer
from app.vault_runtime.memory.repository import MemoryRepository
from app.vault_runtime.voice.repository import VoiceSessionRepository
from tests.support.conversation_identity import require_test_database
from tests.support.live_decision_diagnostics import Logger


@pytest.fixture()
def context():
    url = os.environ.get("VAULT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Isolated PostgreSQL required")
    assert psycopg.conninfo.conninfo_to_dict(url)["dbname"] == "resono_vault_test"
    with psycopg.connect(url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
        connection.execute("DROP SCHEMA IF EXISTS vault_background_queue CASCADE")
    identities = LocalIdentityService(
        repository=LocalIdentityRepository(database_url=url), setup_credential_hash=hash_token("setup"),
    )
    identities.ensure_schema()
    owner = identities.bootstrap_owner(setup_credential="setup", username="owner", password="owner-password",
                                       display_name="Owner", experience_style="strict").principal
    identities.create_user(actor=owner, username="second", password="second-password",
                           display_name="Second", experience_style="strict")
    other = identities.login(username="second", password="second-password").principal
    runs = BackgroundRunRepository(database_url=url)
    runs.ensure_schema()
    yield url, owner, other, runs
    with psycopg.connect(url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
        connection.execute("DROP SCHEMA IF EXISTS vault_background_queue CASCADE")


@pytest.fixture()
def memory_context():
    database_url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("VAULT_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
    identities = LocalIdentityRepository(database_url=database_url)
    service = LocalIdentityService(
        repository=identities, setup_credential_hash=hash_token("setup")
    )
    service.ensure_schema()
    owner = service.bootstrap_owner(
        setup_credential="setup", username="owner", password="owner-password",
        display_name="Owner", experience_style="strict",
    )
    service.create_user(
        actor=owner.principal, username="second", password="second-password",
        display_name="Second", experience_style="funny",
    )
    second = service.login(username="second", password="second-password")
    memories = MemoryRepository(database_url=database_url)
    memories.ensure_schema()
    yield database_url, service, owner, second, memories
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")


@pytest.fixture
def mounted(tmp_path,monkeypatch,request):
    url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Exact isolated database required")
    require_test_database(url)  # Before connection/destructive fixture setup.
    production = request.node.get_closest_marker("flags_off") is None
    with psycopg.connect(url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
    # No background network/model activity in the synthetic transport test.
    monkeypatch.setattr("app.vault_runtime.memory.service.MemoryService.ensure_vectors",lambda *a,**k:(0,0))
    # The durable worker stays off in this synthetic transport fixture.
    monkeypatch.setattr("app.vault_runtime.background_agent.jobs.BackgroundJobs.start",lambda *_:None)
    monkeypatch.setattr("app.vault_runtime.agent_network.service.A2AService.start",lambda *_:None)
    monkeypatch.setattr("app.vault_runtime.agent_network.inbound.A2AInboundHttpServer.start",lambda *_:None)
    monkeypatch.setattr("app.vault_runtime.extensions.mcp_runtime.McpRuntimeSupervisor.restore_on_boot",lambda *_:None)
    config = VaultLocalApiConfig(host="127.0.0.1",port=0,token="local-test",data_root=str(tmp_path),
        storage_status_file=str(tmp_path/"status.json"),storage_mount_point=str(tmp_path/"private"),
        database_url=url,setup_credential_hash=hash_token("setup"),
        # Production composition (TST-02): from_env turns these on in every install. A test that
        # builds its own coordinator or needs the old composition says so with @pytest.mark.flags_off.
        background_coordination_enabled=production,owner_approvals_enabled=production)
        # genui_presentation_hints stays off: it calls the OpenAI Decisions API with the configured key.
    app = build_local_app(config)  # Actual production composition, not manual optional mount.
    assert app._decision_review is not None and app._voice_learning._decision_finalize is not None
    def post(path,payload,headers):
        return app.handle(method="POST",target=path,headers=headers,body=json.dumps(payload).encode())
    onboard = post("/identity/onboard",dict(setupCredential="setup",displayName="Owner",experienceStyle="strict"),{})
    assert onboard.status_code==201
    cookies = "; ".join(v.split(";",1)[0] for k,v in onboard.headers if k=="Set-Cookie")
    csrf = next(v.split("=",1)[1] for v in cookies.split("; ") if v.startswith("resono_csrf="))
    headers = {"Cookie":cookies,"X-ReSono-CSRF":csrf}
    configured = post("/providers/openai",dict(apiKey="sk-synthetic-test-only",modelKey="gpt-realtime",
        backgroundModelKey="gpt-5.6-sol",voice="alloy"),headers)
    assert configured.status_code==200
    from app.vault_runtime.local_api.app import _session_token
    principal = app._identity_service.authenticate(session_token=_session_token(headers))
    calls,logger = [],Logger()
    flags = {"memory_fail":False,"decision_fail":False}
    def execute(**kwargs):
        calls.append(kwargs)
        assert kwargs["api_key"]=="sk-synthetic-test-only" and kwargs["model"]=="gpt-5.6-sol"
        if kwargs["agent_name"]=="Vault Memory Review":
            if flags["memory_fail"]:
                raise RuntimeError("PRIVATE MEMORY PROVIDER FAILURE")
            return dict(contractVersion=2,summary="Captured synthetic session",candidates=[])
        assert kwargs["agent_name"]=="Vault Decisions Review"
        if flags["decision_fail"]:
            raise RuntimeError("PRIVATE DECISION PROVIDER FAILURE")
        data = json.loads(kwargs["input_text"])
        assert data["coverage"] in {"unknown","complete"}
        dimension = lambda:dict(judgment="unknown",evidence_source_ids=[],explanation="Original context/causality or feedback unavailable")
        return dict(contract_version=3,proposals=[],assessments=[dict(point_id=p["point_id"],
            request_resolution=dimension(),usefulness=dimension(),
            tool_selection=dimension(),context_selection=dimension(),result_quality=dimension(),
            user_satisfaction=dimension(),tool_satisfaction=dimension(),context_satisfaction=dimension(),
            result_satisfaction=dimension(),failure_stage="unknown") for p in data["observations"]])
    app._decision_review.executor=execute
    app._conversation_runtime.decision_review.executor=execute
    app._conversation_runtime.title_runner=None  # No real model call for Chat titles in tests.
    app._decision_review.diagnostics=LiveDiagnostics(logger=logger)
    app._voice_learning._reviewer_factory=lambda u,w:OpenAIMemoryReviewer(credentials=app._voice_provider_credentials,
        user_id=u,workspace_id=w,executor=execute)
    def session(text="PRIVATE FINAL CONTACTS REQUEST"):
        voice = app._voice_sessions.create_session(user_id=principal.user_id,workspace_id=principal.workspace_id,
            local_session_id=principal.session_id,provider_key="openai",model_key="gpt-realtime",connection_mode="webrtc")
        response = post(f"/voice/sessions/{voice.voice_session_id}/events",dict(providerEventId="user-final",
            eventType="conversation.item.input_audio_transcription.completed",role="user",transcriptText=text,
            transcriptEntryIndex=0,providerPayload={"type":"conversation.item.input_audio_transcription.completed","transcript":text}),headers)
        assert response.status_code==201
        return voice.voice_session_id
    try:
        yield SimpleNamespace(app=app,config=config,url=url,principal=principal,headers=headers,post=post,session=session,
            calls=calls,logger=logger,flags=flags)
    finally:
        app.close()
        with psycopg.connect(require_test_database(url)) as connection:
            connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")


@pytest.fixture()
def voice_context():
    database_url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("VAULT_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
    identities = LocalIdentityRepository(database_url=database_url)
    identity = LocalIdentityService(
        repository=identities, setup_credential_hash=hash_token("setup")
    )
    identity.ensure_schema()
    owner = identity.bootstrap_owner(
        setup_credential="setup", username="owner", password="owner-password",
        display_name="Christian", experience_style="funny",
    )
    identity.create_user(
        actor=owner.principal, username="second", password="second-password",
        display_name="Second", experience_style="strict",
    )
    second = identity.login(username="second", password="second-password")
    memories = MemoryRepository(database_url=database_url)
    memories.ensure_schema()
    voices = VoiceSessionRepository(database_url=database_url)
    voices.ensure_schema()
    yield database_url, identity, owner, second, memories, voices
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
