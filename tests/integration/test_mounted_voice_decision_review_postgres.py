import json
import os
import time
from threading import Event
from types import SimpleNamespace

import psycopg
import pytest

from app.core.security.tokens import hash_token
from app.vault_runtime.composition import build_local_app
from app.vault_runtime.local_api.config import VaultLocalApiConfig
from app.vault_runtime.memory.openai_reviewer import OpenAIMemoryReviewer
from app.vault_runtime.decision_routing.diagnostics import LiveDiagnostics
from tests.integration.test_conversation_identity_postgres import require_test_database
from tests.unit.test_live_decision_diagnostics import Logger


@pytest.fixture
def mounted(tmp_path,monkeypatch):
    url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Exact isolated database required")
    require_test_database(url)  # Before connection/destructive fixture setup.
    with psycopg.connect(url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
    # No background network/model activity in the synthetic transport test.
    monkeypatch.setattr("app.vault_runtime.memory.service.MemoryService.ensure_vectors",lambda *a,**k:(0,0))
    monkeypatch.setattr("app.vault_runtime.background_agent.service.BackgroundAgentService.start",lambda *_:None)
    monkeypatch.setattr("app.vault_runtime.agent_network.service.A2AService.start",lambda *_:None)
    monkeypatch.setattr("app.vault_runtime.agent_network.inbound.A2AInboundHttpServer.start",lambda *_:None)
    monkeypatch.setattr("app.vault_runtime.extensions.mcp_runtime.McpRuntimeSupervisor.restore_on_boot",lambda *_:None)
    config = VaultLocalApiConfig(host="127.0.0.1",port=0,token="local-test",data_root=str(tmp_path),
        storage_status_file=str(tmp_path/"status.json"),storage_mount_point=str(tmp_path/"private"),
        database_url=url,setup_credential_hash=hash_token("setup"))
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


def test_actual_production_close_reviews_canonical_tool_call_and_replays_checkpoint(mounted):
    m = mounted
    voice = m.session()
    authority = m.app._voice_tools._authority
    authority.ensure_builtin_grants(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,
        definitions=m.app._voice_tools.definitions(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id))
    result = m.post(f"/voice/sessions/{voice}/tools/call",dict(name="contacts_search",arguments={"query":"PRIVATE CONTACT"},
        toolCallId="contacts-call",userUtterance="PRIVATE FINAL CONTACTS REQUEST",userUtteranceId=0),m.headers)
    assert result.status_code==200 and result.payload["isError"] is False
    denied = m.post(f"/voice/sessions/{voice}/close",{}, {"Cookie":m.headers["Cookie"]})
    assert denied.status_code==403 and m.calls==[]
    closed = m.post(f"/voice/sessions/{voice}/close",{},m.headers)
    assert closed.status_code==200 and closed.payload["learning"]=="queued"
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        with m.app._conversation_runtime._lock:
            pending="review:voice-review:"+voice in m.app._conversation_runtime._workers
        if not pending: break
        time.sleep(.02)
    assert not pending
    assert [c["agent_name"] for c in m.calls]==["Vault Memory Review","Vault Decisions Review"]
    data = json.loads(m.calls[1]["input_text"])
    assert data["observations"][0]["final_source_id"] is not None
    assert data["observations"][0]["execution"]=="completed" and data["observations"][0]["request_outcome"]=="unknown"
    assert data["capabilities"][0]["capability_id"]=="builtin.contacts-search.v1"
    assert any(s["kind"]=="tool_request" for s in data["sources"])
    assert all(s["kind"]!="reasoning_summary" for s in data["sources"])
    status = m.app.handle(method="GET",target=f"/voice/sessions/{voice}/decision-review",headers=m.headers)
    assert status.status_code==200 and status.payload["coverage"]=="unknown"
    assert status.payload["provider"]=="openai" and status.payload["model"]=="gpt-5.6-sol"
    assert len(status.payload["assessments"])==1 and status.payload["proposals"]==[]
    assert m.app.handle(method="GET",target=f"/voice/sessions/{voice}/decision-review",headers={}).status_code==403
    replay = m.post(f"/voice/sessions/{voice}/finalize",{},m.headers)
    assert replay.status_code==200 and replay.payload["decisionReview"]["alreadyCompleted"] is True
    assert len(m.calls)==2
    with psycopg.connect(m.url) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_decision_reviews").fetchone()[0]==1
        assert connection.execute("SELECT count(*) FROM vault_private.vault_conversation_turns").fetchone()[0]==0
        # Chat initializes shared rule schema; unqualified Voice still cannot publish.
        assert connection.execute("SELECT count(*) FROM vault_private.vault_decision_generations").fetchone()[0]==0
        connection.execute("DELETE FROM vault_private.vault_voice_sessions WHERE voice_session_id=%s",(voice,))
        assert connection.execute("SELECT count(*) FROM vault_private.vault_conversations").fetchone()[0]==0
        assert connection.execute("SELECT count(*) FROM vault_private.vault_decision_reviews").fetchone()[0]==0
    raw = json.dumps(m.logger.rows)
    assert "PRIVATE" not in raw and voice not in raw and "sk-synthetic" not in raw
    assert any(r["event"]=="review_completed" for r in m.logger.rows)


def test_independent_failures_do_not_suppress_other_review_or_repeat_completed(mounted):
    m = mounted
    voice = m.session("Memory failure final")
    m.flags["memory_fail"] = True
    m.app._voice_sessions.close_session(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,
        local_session_id=m.principal.session_id,voice_session_id=voice)
    response = m.post(f"/voice/sessions/{voice}/finalize",{},m.headers)
    assert response.status_code==502
    assert [c["agent_name"] for c in m.calls]==["Vault Memory Review","Vault Decisions Review"]
    status = m.app.handle(method="GET",target=f"/voice/sessions/{voice}/decision-review",headers=m.headers)
    assert status.payload["state"]=="completed"
    m.flags["memory_fail"]=False
    m.flags["decision_fail"]=True
    voice2 = m.session("Procedural failure final")
    m.app._voice_sessions.close_session(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,
        local_session_id=m.principal.session_id,voice_session_id=voice2)
    response = m.post(f"/voice/sessions/{voice2}/finalize",{},m.headers)
    assert response.status_code==200 and response.payload["learning"]=="completed"
    assert response.payload["decisionReview"]["state"]=="failed"
    status = m.app.handle(method="GET",target=f"/voice/sessions/{voice2}/decision-review",headers=m.headers)
    assert status.payload["state"]=="retryable" and status.payload["errorCode"]=="review_failed"
    m.flags["decision_fail"]=False
    count = len(m.calls)
    response = m.post(f"/voice/sessions/{voice2}/finalize",{},m.headers)
    assert response.status_code==200 and len(m.calls)==count+1
    assert m.calls[-1]["agent_name"]=="Vault Decisions Review"
    assert "PRIVATE" not in json.dumps(m.logger.rows)


def test_source_gate_open_scope_mutation_and_no_unknown_publication(mounted):
    from dataclasses import replace
    from app.vault_runtime.decision_learning.repository import ReviewConflictError
    from app.vault_runtime.decision_learning.rules import DecisionRuleRepository
    m = mounted
    voice = m.session()
    assert m.app._decision_review.finalize(principal=m.principal,voice_session_id=voice)["state"]=="failed"
    assert m.calls==[]
    m.app._voice_sessions.close_session(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,
        local_session_id=m.principal.session_id,voice_session_id=voice)
    source = m.app._decision_review.source.load(m.principal,voice)
    with psycopg.connect(m.url) as connection,connection.cursor() as cursor:
        assert m.app._decision_review.source.current(cursor,m.principal,source) is True
        connection.execute("UPDATE vault_private.vault_transcript_entries SET text_content='changed canonical source'")
        assert m.app._decision_review.source.current(cursor,m.principal,source) is False
    with pytest.raises(Exception):
        m.app._decision_review.source.load(replace(m.principal,user_id="foreign"),voice)
    rules = DecisionRuleRepository(database_url=m.url,source_current=m.app._decision_review.source.current)
    with pytest.raises(ReviewConflictError,match="complete capture"):
        rules.publish(m.principal,review_id="unused",snapshot=source,review=None)
    assert m.calls==[]


def test_failed_transcript_acknowledgment_blocks_both_reviewers(mounted):
    m = mounted
    voice = m.session()
    response = m.post(f"/voice/sessions/{voice}/close",{"transcriptCaptureFailures":2},m.headers)
    assert response.status_code==200
    assert response.payload["captureState"]=="incomplete"
    assert response.payload["learning"]=="deferred_incomplete_capture"
    assert m.calls==[]
    status = m.app.handle(method="GET",target=f"/voice/sessions/{voice}/decision-review",headers=m.headers)
    assert status.payload["state"]=="blocked_incomplete_capture"
    assert m.post(f"/voice/sessions/{voice}/finalize",{},m.headers).status_code==409
    with psycopg.connect(m.url) as connection:
        assert connection.execute("SELECT transcript_capture_state,transcript_capture_failures FROM vault_private.vault_voice_sessions WHERE voice_session_id=%s",(voice,)).fetchone()==("incomplete",2)
    with pytest.raises(Exception):
        m.app._decision_review.source.load(m.principal,voice)
    assert m.calls==[]


def test_capture_acknowledgment_validation_and_zero_failure_close(mounted):
    m = mounted
    voice = m.session()
    for invalid in (True,-1,"0"):
        assert m.post(f"/voice/sessions/{voice}/close",{"transcriptCaptureFailures":invalid},m.headers).status_code==400
    assert m.calls==[]
    response = m.post(f"/voice/sessions/{voice}/close",{"transcriptCaptureFailures":0},m.headers)
    assert response.status_code==200 and response.payload["captureState"]=="acknowledged"
    assert response.payload["learning"]=="queued"
    from tests.integration.test_mounted_chat_memory_learning_postgres import finish_workers
    finish_workers(m.app._conversation_runtime)
    assert len(m.calls)==2


def test_procedural_module_can_be_disabled_at_production_composition(mounted):
    from dataclasses import replace
    m = mounted
    app = build_local_app(replace(m.config,decision_review_enabled=False))
    try:
        assert app._decision_review is None
        assert app._voice_learning._decision_finalize is None
        assert app._conversation_runtime.decision_review is None
        assert app._conversation_runtime.preparation.learned_queries is None
        voice = m.session()
        assert app.handle(method="GET",target=f"/voice/sessions/{voice}/decision-review",headers=m.headers).status_code==503
        # The existing canonical memory finalizer remains installed.
        assert app._voice_learning is not None
    finally:
        app.close()


def test_original_browser_proposal_is_captured_and_linked_without_inventing_coverage(mounted):
    m = mounted
    voice = m.session()
    event = dict(type="response.function_call_arguments.done",event_id="original-call-event",
        response_id="response-1",item_id="item-1",call_id="original-call",name="contacts_search",
        arguments=json.dumps({"query":"Sarah"}))
    payload = dict(providerEventId=event["event_id"],eventType=event["type"],role="assistant",providerPayload=event)
    assert m.post(f"/voice/sessions/{voice}/events",payload,m.headers).status_code==201
    assert m.post(f"/voice/sessions/{voice}/events",payload,m.headers).status_code==200
    with psycopg.connect(m.url) as connection:
        connection.execute("UPDATE vault_private.vault_voice_provider_events SET evidence_json='{}'::jsonb WHERE provider_event_id='original-call-event'")
    assert m.post(f"/voice/sessions/{voice}/events",payload,m.headers).status_code==200
    changed = dict(payload,providerPayload=dict(event,arguments='{"query":"someone else"}'))
    rejected = m.post(f"/voice/sessions/{voice}/events",changed,m.headers)
    assert rejected.status_code==403 and rejected.payload["error"]["code"]=="voice_session_conflict"
    authority = m.app._voice_tools._authority
    authority.ensure_builtin_grants(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,
        definitions=m.app._voice_tools.definitions(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id))
    result = m.post(f"/voice/sessions/{voice}/tools/call",dict(name="contacts_search",arguments={"query":"Sarah"},
        toolCallId="original-call",userUtterance="PRIVATE FINAL CONTACTS REQUEST",userUtteranceId=0),m.headers)
    assert result.status_code==200
    response = m.post(f"/voice/sessions/{voice}/close",{"transcriptCaptureFailures":0},m.headers)
    assert response.status_code==200 and response.payload["learning"]=="queued"
    from tests.integration.test_mounted_chat_memory_learning_postgres import finish_workers
    finish_workers(m.app._conversation_runtime)
    status=m.app.handle(method="GET",target=f"/voice/sessions/{voice}/decision-review",headers=m.headers)
    assert status.payload["coverage"]=="unknown"
    data = json.loads(m.calls[-1]["input_text"])
    point = data["observations"][0]
    source = next(s for s in data["sources"] if s["source_id"]==point["proposal_source_id"])
    assert source["kind"]=="model_proposal"
    original = json.loads(source["text"])
    assert original["captured_provider"]["origin"]=="browser_provider"
    assert original["captured_provider"]["response_id"]=="response-1"
    assert original["executed_arguments"]=={"query":"Sarah"}
    assert any(s["source_id"]==original["executed_request_source_id"] and s["kind"]=="tool_request" for s in data["sources"])
    with psycopg.connect(m.url) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_transcript_entries WHERE voice_session_id=%s",(voice,)).fetchone()[0]==1
        stored = connection.execute("SELECT evidence_json FROM vault_private.vault_voice_provider_events WHERE provider_event_id='original-call-event'").fetchone()[0]
        assert stored["proposals"][0]["call_id"]=="original-call"
    assert "PRIVATE" not in json.dumps(m.logger.rows)

    # Conflicting original response identities never pick a convenient candidate.
    ambiguous = m.session()
    for number in (1,2):
        original = dict(event,response_id=f"response-{number}",event_id=f"ambiguous-{number}")
        assert m.post(f"/voice/sessions/{ambiguous}/events",dict(payload,
            providerEventId=original["event_id"],providerPayload=original),m.headers).status_code==201
    assert m.post(f"/voice/sessions/{ambiguous}/tools/call",dict(name="contacts_search",arguments={"query":"Sarah"},
        toolCallId="original-call",userUtterance="PRIVATE FINAL CONTACTS REQUEST",userUtteranceId=0),m.headers).status_code==200
    m.app._voice_sessions.close_session(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,
        local_session_id=m.principal.session_id,voice_session_id=ambiguous)
    snapshot = m.app._decision_review.source.load(m.principal,ambiguous)
    point = snapshot.observations[0]
    assert next(s for s in snapshot.sources if s.source_id==point.proposal_source_id).kind=="tool_request"
    assert len(m.calls)==2


def test_voice_failed_review_recovers_from_existing_durable_segment(mounted):
    from tests.integration.test_mounted_chat_memory_learning_postgres import finish_workers
    m=mounted
    voice=m.session('Recovery source')
    m.flags['decision_fail']=True
    assert m.post(f'/voice/sessions/{voice}/close',{},m.headers).status_code==200
    finish_workers(m.app._conversation_runtime)  # Close dispatches the review in the background.
    segment='voice-review:'+voice
    with psycopg.connect(m.url) as connection:
        assert connection.execute('SELECT review_state,memory_review_state,decision_review_state FROM vault_private.vault_conversation_segments WHERE segment_id=%s',(segment,)).fetchone()==('queued','completed','failed')
        connection.execute('UPDATE vault_private.vault_conversation_segments SET review_due_at=now() WHERE segment_id=%s',(segment,))
    calls=len(m.calls)
    m.flags['decision_fail']=False
    runtime=m.app._conversation_runtime
    runtime._start_review(m.principal,voice,segment)
    finish_workers(runtime)
    assert len(m.calls)==calls+1 and m.calls[-1]['agent_name']=='Vault Decisions Review'
    with psycopg.connect(m.url) as connection:
        assert connection.execute('SELECT review_state,review_attempts FROM vault_private.vault_conversation_segments WHERE segment_id=%s',(segment,)).fetchone()==('completed',2)
        assert connection.execute('SELECT count(*) FROM vault_private.vault_memory_ingestions').fetchone()[0]==1


def test_voice_retry_bridge_cascades_without_procedural_schema_mount(mounted):
    m=mounted
    runtime=m.app._conversation_runtime
    voice=m.session('Source owned by Voice')
    m.app._voice_sessions.close_session(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,
        local_session_id=m.principal.session_id,voice_session_id=voice)
    # Simulate the previously optional procedural bridge migration being absent.
    with psycopg.connect(m.url) as connection:
        connection.execute('ALTER TABLE vault_private.vault_conversations DROP CONSTRAINT fk_conversation_voice_review_source')
    runtime.decision_review=None
    runtime.ensure_schema()
    runtime.store.queue_voice_review(m.principal,voice)
    with psycopg.connect(m.url) as connection:
        assert connection.execute('SELECT count(*) FROM vault_private.vault_conversations WHERE conversation_id=%s',(voice,)).fetchone()[0]==1
        connection.execute('DELETE FROM vault_private.vault_voice_sessions WHERE voice_session_id=%s',(voice,))
        assert connection.execute('SELECT count(*) FROM vault_private.vault_conversations WHERE conversation_id=%s',(voice,)).fetchone()[0]==0


def test_voice_logs_use_shared_chat_publication_and_user_feedback(mounted):
    m = mounted
    voice = m.session("Find a contact")
    runtime = m.app._conversation_runtime
    voice_review = m.app._decision_review
    assert voice_review.on_completed is runtime.decision_review.on_completed
    authority = m.app._voice_tools._authority
    authority.ensure_builtin_grants(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,
        definitions=m.app._voice_tools.definitions(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id))
    called = m.post(f"/voice/sessions/{voice}/tools/call",dict(name="contacts_search",arguments={"query":"test"},
        toolCallId="lookup",userUtterance="Find a contact",userUtteranceId=0),m.headers)
    assert called.status_code == 200 and not called.payload["isError"]
    for index,role,event,text in (
        (1,"assistant","response.output_audio_transcript.done","No matching contacts"),
        (2,"user","conversation.item.input_audio_transcription.completed","Thanks, that answered my question")):
        captured = m.post(f"/voice/sessions/{voice}/events",dict(providerEventId=f"final-{index}",
            eventType=event,role=role,transcriptText=text,transcriptEntryIndex=index,
            providerPayload={"type":event,"transcript":text}),m.headers)
        assert captured.status_code == 201
    class Embedder:
        model_key = "embeddinggemma:300m"
        def embed(self,text):
            return (1.0,)+(0.0,)*767
    voice_review.on_completed.service.embedder_factory = lambda *_:Embedder()
    calls = []
    def evaluate(**kwargs):
        calls.append(kwargs["agent_name"])
        data = json.loads(kwargs["input_text"])
        if kwargs["agent_name"] == "Vault Decisions Reconciliation":
            return dict(data["analysis"],rationale="First qualified contact lookup")
        assert kwargs["agent_name"] == "Vault Decisions Review"
        assert data["coverage"] == "complete"
        point = next(p for p in data["observations"] if p["capability_id"])
        final,result,answer = point["final_source_id"],point["result_source_id"],point["answer_source_id"]
        feedback, = point["feedback_source_ids"]
        assert next(s["text"] for s in data["sources"] if s["source_id"]==feedback)=="Thanks, that answered my question"
        unknown = dict(judgment="unknown",evidence_source_ids=[],explanation="No linked outcome")
        assessments = [dict(point_id=p["point_id"],request_resolution=unknown,usefulness=unknown,
            tool_selection=unknown,context_selection=unknown,result_quality=unknown,
            user_satisfaction=unknown,tool_satisfaction=unknown,context_satisfaction=unknown,
            result_satisfaction=unknown,failure_stage="unknown") for p in data["observations"]]
        assessed = next(a for a in assessments if a["point_id"]==point["point_id"])
        correct = dict(judgment="correct",evidence_source_ids=[final,result],explanation="Actual captured lookup result")
        assessed.update(request_resolution=dict(judgment="resolved",evidence_source_ids=[final,result,answer],explanation="Answer matches lookup"),
            usefulness=dict(judgment="necessary",evidence_source_ids=[final,result],explanation="Requested lookup"),
            tool_selection=correct,context_selection=dict(judgment="not_required",evidence_source_ids=[final],explanation="Explicit lookup"),
            result_quality=correct,user_satisfaction=dict(judgment="satisfied",evidence_source_ids=[feedback],explanation="Explicit user approval"),
            failure_stage="none")
        return dict(contract_version=3,assessments=assessments,proposals=[dict(disposition="create",target_definition_id=None,
            description="Search authorized contacts",conditions=["User requests contact lookup"],required_slots=["query"],
            exclusions=["No modifications"],capability_ids=[point["capability_id"]],point_ids=[point["point_id"]],
            source_ids=[final,result,answer,feedback],examples=["Find a contact"])])
    voice_review.executor = evaluate
    m.app._voice_sessions.close_session(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,
        local_session_id=m.principal.session_id,voice_session_id=voice,transcript_capture_failures=0)
    closed = m.post(f"/voice/sessions/{voice}/finalize",{},m.headers)
    assert closed.status_code == 200
    review = closed.payload["decisionReview"]
    assert review["state"] == "completed" and review["coverage"] == "complete"
    assert review["learning"]["state"] == "generation_active_read_only"
    assert calls == ["Vault Decisions Review","Vault Decisions Reconciliation"]
    # Shared activation gates reconstruct the SAME original Voice logs.
    snapshot = runtime.decision_review.source.load_segment(m.principal,voice,"voice-review:"+voice)
    assert snapshot == voice_review.source.load(m.principal,voice)
    retry = m.post(f"/voice/sessions/{voice}/finalize",{},m.headers)
    assert retry.status_code == 200 and retry.payload["decisionReview"]["alreadyCompleted"]
    assert calls == ["Vault Decisions Review","Vault Decisions Reconciliation"]
    with psycopg.connect(m.url) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_decision_definitions WHERE status='active'").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM vault_private.vault_conversation_turns").fetchone()[0] == 0


def test_semantic_forget_resolves_existing_confirmation_history_without_retaining_a_copy(mounted):
    from app.vault_runtime.memory.pipeline import MemoryPipeline
    from tests.integration.test_memory_suppression_postgres import SemanticReviewer
    from tests.integration.test_memory_postgres import _candidate,_entry
    from dataclasses import replace
    m=mounted
    p=m.principal
    memories=m.app._voice_learning._memories
    voice=m.session('Forget my saved drink preference')
    source=_entry(memories,p,session='original-fact-source',index=0,text='I have a drink preference')
    original=memories.reconcile_memory(user_id=p.user_id,workspace_id=p.workspace_id,
        voice_session_id='original-fact-source',candidate=_candidate(content='Prefers tea'),
        evidence=((source.entry_id,'user_statement','user_asserted',source.text_content),))
    authority=m.app._voice_tools._authority
    authority.ensure_builtin_grants(user_id=p.user_id,workspace_id=p.workspace_id,
        definitions=m.app._voice_tools.definitions(user_id=p.user_id,workspace_id=p.workspace_id))
    prepared=m.post(f'/voice/sessions/{voice}/tools/call',dict(name='memory_prepare_forget',
        arguments={'memoryId':original.memory_id},toolCallId='prepare-forget',
        userUtterance='Forget my saved drink preference',userUtteranceId=0),m.headers)
    assert prepared.status_code==200 and not prepared.payload['isError']
    action=prepared.payload['structuredContent']['actionId']
    confirmation=m.post(f'/voice/sessions/{voice}/events',dict(providerEventId='confirm-forget',
        eventType='conversation.item.input_audio_transcription.completed',role='user',
        transcriptText='Yes, forget it',transcriptEntryIndex=1,
        providerPayload={'type':'conversation.item.input_audio_transcription.completed','transcript':'Yes, forget it'}),m.headers)
    assert confirmation.status_code==201
    confirmed=m.post(f'/voice/sessions/{voice}/tools/call',dict(name='memory_confirm_action',
        arguments={'actionId':action},toolCallId='confirm-forget',userUtterance='Yes, forget it',userUtteranceId=1),m.headers)
    assert confirmed.status_code==200 and not confirmed.payload['isError']
    _entry(memories,p,session='fresh-semantic-source',index=0,text='Tea is my favorite drink')
    reviewer=SemanticReviewer([replace(_candidate(content='Tea is my favorite drink'),memory_key='renamed')])
    result=MemoryPipeline(repository=memories,reviewer=reviewer).finalize(user_id=p.user_id,
        workspace_id=p.workspace_id,voice_session_id='fresh-semantic-source')
    assert result.memory_count==0
    assert reviewer.comparisons[0]['forgotten']==[dict(index=0,content='Prefers tea')]
    with psycopg.connect(m.url) as connection:
        assert connection.execute('SELECT count(*) FROM vault_private.vault_memory_records').fetchone()[0]==0
        assert 'Prefers tea' not in connection.execute('SELECT row_to_json(s)::text FROM vault_private.vault_memory_suppressions s').fetchone()[0]


def test_close_returns_while_existing_learning_worker_is_busy(mounted,monkeypatch):
    m=mounted
    voice=m.session()
    entered,release,finished=Event(),Event(),Event()
    original=m.app._voice_learning.finalize
    def busy(**kwargs):
        entered.set()
        assert release.wait(10)
        try: return original(**kwargs)
        finally: finished.set()
    monkeypatch.setattr(m.app._voice_learning,"finalize",busy)
    try:
        start=time.monotonic()
        result=m.post(f"/voice/sessions/{voice}/close",{},m.headers)
        assert result.status_code==200 and result.payload["learning"]=="queued"
        assert time.monotonic()-start<2
        assert entered.wait(2) and not finished.is_set()
        assert m.calls==[]
    finally:
        release.set()
        assert finished.wait(10)


def test_dropped_tool_request_is_recovered_by_replaying_the_same_call(mounted, monkeypatch):
    import threading
    m = mounted
    voice = m.session("Find a contact")
    authority = m.app._voice_tools._authority
    authority.ensure_builtin_grants(user_id=m.principal.user_id, workspace_id=m.principal.workspace_id,
        definitions=m.app._voice_tools.definitions(user_id=m.principal.user_id, workspace_id=m.principal.workspace_id))
    release = threading.Event()
    catalog = m.app._voice_tools._catalog
    original = catalog.invoke
    def slow(name, arguments, *, context):
        assert release.wait(5)
        return original(name, arguments, context=context)
    monkeypatch.setattr(catalog, "invoke", slow)
    body = dict(name="contacts_search", arguments={"query": "Sarah"}, toolCallId="slow-call")
    first = {}
    worker = threading.Thread(target=lambda: first.update(response=m.post(f"/voice/sessions/{voice}/tools/call", body, m.headers)))
    worker.start()  # The original request; on a phone this is the one the tunnel drops.
    deadline = time.monotonic() + 5
    with psycopg.connect(m.url, autocommit=True) as connection:
        while time.monotonic() < deadline and connection.execute(
                "SELECT count(*) FROM vault_private.vault_voice_tool_invocations WHERE tool_call_id='slow-call' AND state='invoking'").fetchone()[0] == 0:
            Event().wait(.02)
    replay = m.post(f"/voice/sessions/{voice}/tools/call", body, m.headers)
    assert replay.status_code == 202 and replay.payload == {"pending": True}
    release.set(); worker.join()
    stored = m.post(f"/voice/sessions/{voice}/tools/call", body, m.headers)
    assert stored.status_code == 200 and stored.payload == first["response"].payload
    with psycopg.connect(m.url) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_voice_tool_invocations WHERE tool_call_id='slow-call'").fetchone()[0] == 1
