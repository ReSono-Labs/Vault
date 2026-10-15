"""Actual Voice API joins the existing Chat-mounted preparation engine; no paid calls."""
from threading import Event
from time import monotonic
from types import SimpleNamespace

import psycopg
import pytest

from app.vault_runtime.voice.openai_realtime import build_openai_realtime_session_object
from app.vault_runtime.voice.provider import RealtimeSessionResult,ProviderCredential
from tests.integration.test_mounted_voice_decision_review_postgres import mounted
from tests.integration.test_indexed_memory_postgres import _memory,_install


def test_voice_live_uses_shared_engine_final_capture_and_scoped_fallback(mounted,monkeypatch):
    m=mounted
    runtime=m.app._conversation_runtime
    live=runtime.preparation
    assert live.maintenance.ready.wait(10)
    runtime.memories._embedder_factory=None
    requests=[]
    def start(request,**kwargs):
        requests.append(request)
        return RealtimeSessionResult(provider_key="openai",model_key=request.model_key,
            connection_mode="webrtc",provider_session_id="synthetic",client_secret="ephemeral-test-only",
            session_update_event={"type":"session.update","session":build_openai_realtime_session_object(request)})
    monkeypatch.setattr(m.app._voice_coordinator._providers.require("openai"),"create_realtime_session",start)
    started=m.post("/voice/sessions",dict(providerKey="openai",modelKey="gpt-realtime",connectionMode="webrtc"),m.headers)
    assert started.status_code==201,started.payload
    assert started.payload["liveTranscription"] is True
    assert requests[0].turn_detection_create_response is True  # the Voice agent always owns its response
    session=started.payload["voiceRealtimeSessionId"]
    path=f"/voice/sessions/{session}/preparation"
    transcribed=m.post(path+"/transcription",{},m.headers)
    assert transcribed.status_code==201 and transcribed.payload=={"clientSecret":"ephemeral-test-only"}
    assert requests[-1].session_type=="transcription"
    session_object=build_openai_realtime_session_object(requests[-1])
    assert session_object=={"type":"transcription","audio":{"input":{
        "transcription":{"model":"gpt-live-transcribe","delay":"low"},"turn_detection":None}}}
    vector=[1.]+[0.]*767
    fact=_memory(runtime.memories._repository,m.principal,"contacts",vector=vector)
    _install(m.url)
    class Embedder:
        model_key="embeddinggemma:300m"
        def embed(self,text):
            assert text in {"Find my contacts", "Find my calendar", "Find my contacts for Sarah"}
            return vector
    runtime.memories._embedder_factory=lambda *_:Embedder()
    class Transport:
        def __init__(self,**kwargs):pass
        def evaluate(self,*args,**kwargs):raise RuntimeError("Synthetic unavailable selector")
    live.transport_factory=Transport
    monkeypatch.setattr(runtime.catalog,"invoke",lambda *a,**kw:(_ for _ in ()).throw(AssertionError("Partial tool execution")))
    assert m.post(path,dict(utteranceId="speech-one",revision=1,text="Find my contacts",composing=False),m.headers).status_code==202
    identity="voice-live:"+session
    deadline=monotonic()+10
    while monotonic()<deadline:
        status=live.status(m.principal,identity,"speech-one",1)
        if status["state"]=="ready":break
        Event().wait(.03)
    assert status["state"]=="ready",status
    response=m.app.handle(method="GET",target=path+"?utteranceId=speech-one&revision=1",headers=m.headers,body=b"")
    assert response.status_code==200,response.payload
    assert response.payload==status
    assert fact.memory_id in [x["id"] for x in status["memories"]]
    # Continuity: a newer revision of the same utterance keeps the last good memory while it works.
    assert m.post(path,dict(utteranceId="speech-one",revision=2,text="Find my contacts for Sarah",composing=False),m.headers).status_code==202
    sticky=live.status(m.principal,identity,"speech-one",2)
    assert sticky["state"]!="stale" and fact.memory_id in [x["id"] for x in sticky["memories"]]
    assert live.status(m.principal,identity,"speech-one",1)["state"]=="stale"  # superseded revision only
    assert m.post(path+"/delivered",dict(utteranceId="speech-one",memoryCount=1),m.headers).status_code==200
    # Capturing transcript rows (the user's final, the agent's reply) must not stale live preparation.
    before=live.status(m.principal,identity,"speech-one",2)
    for index,role in ((0,"user"),(1,"assistant")):
        assert m.post(f"/voice/sessions/{session}/events",dict(providerEventId=f"turn-{index}",
            eventType="conversation.item.input_audio_transcription.completed" if role=="user" else "response.output_audio_transcript.done",
            role=role,transcriptText="Find my contacts for Sarah",transcriptEntryIndex=index,providerPayload={}),m.headers).status_code==201
    after=live.status(m.principal,identity,"speech-one",2)
    assert after["state"]!="stale" and after["memories"]==before["memories"] and after["memories"]
    assert m.post(path+"/delivered",dict(utteranceId="speech-one",memoryCount=-1),m.headers).status_code==400
    # Hybrid: the conversation runs on ChatGPT OAuth while transcription uses the retained API key.
    asked=[]
    def hybrid(principal,provider,capability=None):
        asked.append(capability)
        if capability in {"live_transcription","web_search"}:
            return ProviderCredential("sk-transcription",auth_method="api_key")
        return ProviderCredential("oauth-conversation",auth_method="chatgpt_oauth")
    with monkeypatch.context() as hybrid_patch:
        hybrid_patch.setattr(m.app,"_provider_credential_resolver",hybrid)
        mixed=m.post("/voice/sessions",dict(providerKey="openai",modelKey="gpt-realtime",connectionMode="webrtc"),m.headers)
        assert mixed.status_code==201,mixed.payload
        assert mixed.payload["liveTranscription"] is True
        assert requests[-1].turn_detection_create_response is True
        mixed_id=mixed.payload["voiceRealtimeSessionId"]
        mixed_transcription=m.post(f"/voice/sessions/{mixed_id}/preparation/transcription",{},m.headers)
        assert mixed_transcription.status_code==201 and mixed_transcription.payload=={"clientSecret":"ephemeral-test-only"}
        assert asked==[None,"live_transcription"]
    with pytest.raises(ValueError):
        m.app._voice_coordinator.start_transcription(principal=m.principal,voice_session_id=session,
            credential=ProviderCredential("synthetic-oauth",auth_method="chatgpt_oauth"))
    assert m.post(path,dict(utteranceId="speech-two",revision=1,text="Find my contacts",composing=False),m.headers).status_code==202
    off=m.post("/live-memory",dict(enabled=False,expectedEpoch=0),m.headers)
    assert off.status_code==200,off.payload
    disabled=m.post(path,dict(utteranceId="speech-two",revision=2,text="Find my calendar",composing=False),m.headers)
    assert disabled.status_code==202 and disabled.payload["enabled"] is False
    assert m.post(path+"/final",dict(utteranceId="speech-two",userUtteranceId=1),m.headers).status_code==404
    ordinary=m.post("/voice/sessions",dict(providerKey="openai",modelKey="gpt-realtime",connectionMode="webrtc"),m.headers)
    assert ordinary.status_code==201 and ordinary.payload["liveTranscription"] is False
    assert requests[-1].turn_detection_create_response is True
    with psycopg.connect(m.url) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_conversations").fetchone()[0]==0
        assert connection.execute("SELECT count(*) FROM vault_private.vault_transcript_entries WHERE voice_session_id=%s",(session,)).fetchone()[0]==2
    assert m.post(path,dict(utteranceId="speech-two",revision=1,text="Find my contacts",composing=False),
        {"Cookie":m.headers["Cookie"]}).status_code==403
    with psycopg.connect(m.url) as connection:
        connection.execute("UPDATE vault_private.local_sessions SET status='revoked',revoked_at=now() WHERE session_id=%s",(m.principal.session_id,))
    assert m.post(path,dict(utteranceId="speech-three",revision=1,text="Find my contacts",composing=False),m.headers).status_code==403


def test_voice_tool_route_survives_concurrent_session_touches(mounted,monkeypatch):
    import threading
    m=mounted
    runtime=m.app._conversation_runtime
    live=runtime.preparation
    assert live.maintenance.ready.wait(10)
    runtime.memories._embedder_factory=None
    monkeypatch.setattr(m.app._voice_coordinator._providers.require("openai"),"create_realtime_session",
        lambda request,**_:RealtimeSessionResult(provider_key="openai",model_key=request.model_key,connection_mode="webrtc",
            provider_session_id="synthetic",client_secret="ephemeral-test-only",
            session_update_event={"type":"session.update","session":build_openai_realtime_session_object(request)}))
    session=m.post("/voice/sessions",dict(providerKey="openai",modelKey="gpt-realtime",connectionMode="webrtc"),m.headers).payload["voiceRealtimeSessionId"]
    m.app._conversation_runtime.authority.ensure_builtin_grants(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,
        definitions=m.app._voice_tools.definitions(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id))
    class Transport:
        def __init__(self,**_):pass
        def evaluate(self,payload,**_):
            choices=payload["questions"][0]["choices"]
            chosen=next(c["value"] for c in choices if c["value"]=="contacts_search")
            return {"answers":[{"type":"choice","name":"workflow","choice":chosen,"confidence":.9,
                "probabilities":[{"value":c["value"],"probability":1. if c["value"]==chosen else 0.} for c in choices]}]}
    live.transport_factory=Transport
    monkeypatch.setattr(runtime.catalog,"invoke",lambda *a,**kw:(_ for _ in ()).throw(AssertionError("Partial tool execution")))
    stop=threading.Event()
    def touch():  # what every authenticated poll does to the session row
        with psycopg.connect(m.url,autocommit=True) as connection:
            while not stop.is_set():
                connection.execute("UPDATE vault_private.local_sessions SET last_seen_at=now() WHERE session_id=%s",(m.principal.session_id,))
    toucher=threading.Thread(target=touch); toucher.start()
    try:
        path=f"/voice/sessions/{session}/preparation"
        assert m.post(path,dict(utteranceId="speech",revision=1,text="Find Sarah in my contacts",composing=False),m.headers).status_code==202
        identity="voice-live:"+session
        deadline=monotonic()+10
        while monotonic()<deadline:
            status=live.status(m.principal,identity,"speech",1)
            if status["tools"]: break
            Event().wait(.05)
        assert status["state"]!="stale" and [t["name"] for t in status["tools"]]==["contacts_search"], status
        assert m.post(path+"/delivered",dict(utteranceId="speech",memoryCount=0,toolCount=1),m.headers).status_code==200
    finally:
        stop.set(); toucher.join()
