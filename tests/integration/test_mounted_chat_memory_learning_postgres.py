"""Actual ended Chat factual mount; isolated database and synthetic providers only."""
from threading import Event
from time import monotonic
from types import SimpleNamespace as NS

import psycopg
import pytest

from app.vault_runtime.memory.openai_reviewer import OpenAIMemoryReviewer
from tests.integration.test_mounted_voice_decision_review_postgres import mounted
from tests.integration.test_mounted_conversation_runtime_postgres import create, wait


def finish_workers(runtime):
    deadline=monotonic()+10
    while monotonic()<deadline:
        with runtime._lock:
            if not runtime._workers:
                return
        Event().wait(.02)
    raise AssertionError("Bounded review worker did not finish")


def configure(m,*,bad_citation=False):
    conversation=create(m)
    runtime=m.app._conversation_runtime
    calls=[]
    def evaluate(**kwargs):
        calls.append(kwargs)
        assert "morning appointments" in kwargs["input_text"]
        return dict(contractVersion=2,summary="Appointment preference captured",candidates=[dict(
            domain="personal",memoryType="preference",stableKey="appointment-time",
            content="User prefers morning appointments",sourceEntryIndexes=[999 if bad_citation else 0],
            sourceAuthority="user_asserted",confidence="high",sensitivity="normal",
            reconciliationIntent="create",shouldStore=True)])
    runtime.memory_learning.voice_learning._reviewer_factory=lambda u,w:OpenAIMemoryReviewer(
        credentials=m.app._voice_provider_credentials,user_id=u,workspace_id=w,executor=evaluate)
    embedded=[]
    class Embedder:
        model_key="text-embedding-3-small"
        def embed(self,text):
            embedded.append(text)
            return [1.]+[0.]*1535
    runtime.memory_learning.voice_learning._embedder_factory=lambda *_:Embedder()
    async def runner(**kwargs):
        kwargs["model_response_sink"](NS(response_id="response",output=[NS(type="message",id="answer",
            role="assistant",content=[NS(type="output_text",text="Understood")])]))
        return "Understood"
    runtime.runner=runner
    result=m.post(f"/conversations/{conversation}/turns",dict(submissionKey="fact",input="I prefer morning appointments",
        expectedHistoryVersion=0),m.headers)
    assert result.status_code==202
    assert wait(m,conversation,result.payload["turnId"])["state"]=="completed"
    finish_workers(runtime)  # Terminal DB state precedes worker slot release.
    return conversation,runtime,calls,embedded


def test_ended_chat_saves_canonical_fact_real_vector_and_retries_without_relearning(mounted):
    m=mounted
    conversation,runtime,calls,embedded=configure(m)
    # Factual learning is independent of the procedural feature/module.
    runtime.decision_review=None
    ended=runtime.end_session(m.principal,conversation,1)
    assert ended["reviewState"]=="pending"
    finish_workers(runtime)
    assert len(calls)==len(embedded)==1
    with psycopg.connect(m.url) as connection:
        assert connection.execute("SELECT content_text,current_version FROM vault_private.vault_memory_records").fetchall()==[
            ("User prefers morning appointments",1)]
        assert connection.execute("SELECT count(*) FROM vault_private.vault_transcript_entries").fetchone()[0]==0
        assert connection.execute("SELECT vector_dims(embedding) FROM vault_private.vault_memory_embeddings").fetchone()[0]==1536
        assert connection.execute("SELECT dispositions_json FROM vault_private.vault_chat_memory_reviews").fetchone()[0][0]["sourceIds"][0].startswith("chat-final:")
        reference,excerpt=connection.execute("SELECT source_ref_json,evidence_text FROM vault_private.vault_memory_evidence").fetchone()
        assert reference["sourceId"].startswith("chat-final:")
        assert reference["start"]==0 and reference["end"]==reference["sourceLength"]==len(excerpt)
        from hashlib import sha256
        assert reference["sourceFingerprint"]==sha256(excerpt.encode()).hexdigest()
    retry=runtime.memory_learning.finalize(principal=m.principal,conversation_id=conversation,segment_id=ended["segmentId"])
    assert retry["alreadyCompleted"] and len(calls)==1
    matches=runtime.memories.search(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,
        query="morning appointments",limit=8)
    assert any("morning appointments" in match.memory.content_text for match in matches)


@pytest.mark.parametrize("failure",["citation","publication"])
def test_factual_failure_publishes_nothing_and_does_not_suppress_decisions(mounted,monkeypatch,failure):
    m=mounted
    conversation,runtime,calls,embedded=configure(m,bad_citation=failure=="citation")
    if failure=="publication":
        repository=runtime.memory_learning.memories
        reconcile=repository.reconcile_memory
        def failed(**kwargs):
            reconcile(**kwargs)
            raise RuntimeError("Synthetic failure after canonical write before checkpoint")
        monkeypatch.setattr(repository,"reconcile_memory",failed)
    ended=runtime.end_session(m.principal,conversation,1)
    finish_workers(runtime)
    assert len(calls)==1 and not embedded
    with psycopg.connect(m.url) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_memory_records").fetchone()[0]==0
        assert connection.execute("SELECT count(*) FROM vault_private.vault_chat_memory_reviews WHERE state='completed'").fetchone()[0]==0
        assert connection.execute("SELECT count(*) FROM vault_private.vault_chat_memory_reviews WHERE state='reviewed'").fetchone()[0]==(1 if failure=="publication" else 0)
    source=runtime.decision_review.source.load_segment(m.principal,conversation,ended["segmentId"])
    assert runtime.decision_review.repository.for_source(m.principal,source)[1]=="completed"
    if failure=="publication":
        monkeypatch.setattr(repository,"reconcile_memory",reconcile)
        result=runtime.memory_learning.finalize(principal=m.principal,conversation_id=conversation,segment_id=ended["segmentId"])
        assert result["state"]=="completed" and len(calls)==1 and len(embedded)==1
        with psycopg.connect(m.url) as connection:
            assert connection.execute("SELECT count(*) FROM vault_private.vault_memory_records").fetchone()[0]==1
            assert connection.execute("SELECT state FROM vault_private.vault_chat_memory_reviews").fetchone()[0]=="completed"


def test_revoked_session_during_model_work_cannot_publish(mounted):
    m=mounted
    conversation,runtime,calls,embedded=configure(m)
    learning=runtime.memory_learning.voice_learning
    factory=learning._reviewer_factory
    def reviewer_factory(u,w):
        reviewer=factory(u,w)
        original=reviewer.review
        def review(text):
            result=original(text)
            with psycopg.connect(m.url) as connection:
                connection.execute("UPDATE vault_private.local_sessions SET status='revoked',revoked_at=now() WHERE session_id=%s",
                    (m.principal.session_id,))
            return result
        reviewer.review=review
        return reviewer
    learning._reviewer_factory=reviewer_factory
    runtime.end_session(m.principal,conversation,1)
    finish_workers(runtime)
    assert len(calls)==1 and not embedded
    with psycopg.connect(m.url) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_memory_records").fetchone()[0]==0
        assert connection.execute("SELECT count(*) FROM vault_private.vault_chat_memory_reviews").fetchone()[0]==0


@pytest.mark.parametrize('explicit_remember',[False,True])
def test_chat_semantic_forgetting_uses_original_reviews_and_existing_remember_authority(mounted,explicit_remember):
    import json
    m=mounted
    conversation,runtime,_,_=configure(m)
    runtime.decision_review=None
    runtime.end_session(m.principal,conversation,1)
    finish_workers(runtime)
    repository=runtime.memory_learning.memories
    original,=repository.profile_memories(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id)
    repository.delete_memory(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,memory_id=original.memory_id)
    created=m.post('/conversations',dict(createKey='semantic-fresh'),m.headers)
    fresh=created.payload['conversationId']
    submitted=m.post(f'/conversations/{fresh}/turns',dict(submissionKey='fresh',
        input='Early appointments suit me, and I own a bicycle',expectedHistoryVersion=0),m.headers)
    assert submitted.status_code==202
    turn=submitted.payload['turnId']
    assert wait(m,fresh,turn)['state']=='completed'
    finish_workers(runtime)
    calls=[]
    def evaluate(**kwargs):
        calls.append(kwargs['agent_name'])
        if kwargs['agent_name']=='Vault Memory Forget Review':
            payload=json.loads(kwargs['input_text'])
            assert payload['forgotten']==[dict(index=0,content='User prefers morning appointments')]
            return dict(comparisons=[dict(candidate_index=c['index'],forgotten_index=0,
                judgment='same_fact' if 'Appointments' in c['content'] else 'different_fact') for c in payload['candidates']])
        assert kwargs['agent_name']=='Vault Memory Review'
        def candidate(key,content,domain):
            return dict(domain=domain,memoryType='fact',stableKey=key,content=content,sourceEntryIndexes=[0],
                sourceAuthority='user_asserted',confidence='high',sensitivity='normal',reconciliationIntent='create',shouldStore=True)
        return dict(contractVersion=2,summary='New submitted facts',candidates=[
            candidate('schedule','Appointments early in the day suit the user','environment'),
            candidate('vehicle','User owns a bicycle','device')])
    runtime.memory_learning.voice_learning._reviewer_factory=lambda u,w:OpenAIMemoryReviewer(
        credentials=m.app._voice_provider_credentials,user_id=u,workspace_id=w,executor=evaluate)
    if explicit_remember:
        with psycopg.connect(m.url) as connection:
            connection.execute('UPDATE vault_private.vault_conversation_turns SET explicit_remember=true WHERE turn_id=%s',(turn,))
    ended=runtime.end_session(m.principal,fresh,1)
    finish_workers(runtime)
    facts=repository.profile_memories(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id)
    assert sorted(r.content_text for r in facts)==sorted(['User owns a bicycle']+
        (['Appointments early in the day suit the user'] if explicit_remember else []))
    assert calls==['Vault Memory Review']+([] if explicit_remember else ['Vault Memory Forget Review'])
    retried=runtime.memory_learning.finalize(principal=m.principal,conversation_id=fresh,segment_id=ended['segmentId'])
    assert retried['alreadyCompleted']
    assert len(calls)==(1 if explicit_remember else 2)
    with psycopg.connect(m.url) as connection:
        assert connection.execute('SELECT count(*) FROM vault_private.vault_transcript_entries').fetchone()[0]==0
        dispositions=connection.execute('SELECT dispositions_json FROM vault_private.vault_chat_memory_reviews WHERE conversation_id=%s',(fresh,)).fetchone()[0]
        assert [r['state'] for r in dispositions]==(['active','active'] if explicit_remember else ['suppressed','active'])
