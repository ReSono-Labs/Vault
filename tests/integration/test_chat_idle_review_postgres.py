"""Mounted idle checkpoint/consumer markers, exact isolated DB and synthetic models."""
import psycopg
import pytest

from app.vault_runtime.conversation.contracts import ConflictError
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.memory.contracts import MemoryReview
from tests.integration.test_mounted_voice_decision_review_postgres import mounted
from tests.integration.test_mounted_chat_memory_learning_postgres import configure,finish_workers
from tests.integration.test_mounted_conversation_runtime_postgres import wait


def age(m,conversation):
    with psycopg.connect(m.url) as c:
        c.execute("UPDATE vault_private.vault_conversations SET activity_at=now()-interval '3 minutes' WHERE conversation_id=%s",(conversation,))


def test_idle_checkpoint_independent_retry_and_continuing_same_chat(mounted):
    m=mounted
    conversation,runtime,calls,_=configure(m)
    resolve=LocalIdentityRepository(database_url=m.url).resolve_review_principal
    # Recent activity and active responses cannot trigger review.
    runtime.review_idle(resolve)
    assert not calls
    age(m,conversation)
    with psycopg.connect(m.url) as c:
        c.execute("UPDATE vault_private.vault_conversation_turns SET state='running' WHERE conversation_id=%s",(conversation,))
    runtime.review_idle(resolve)
    assert not calls
    with psycopg.connect(m.url) as c:
        c.execute("UPDATE vault_private.vault_conversation_turns SET state='completed' WHERE conversation_id=%s",(conversation,))
    # Discovery is only a hint: heartbeat cancels stale discovered idle work.
    assert runtime.store.idle_conversations(120)
    heartbeat=m.post(f"/conversations/{conversation}/activity",{},m.headers)
    assert heartbeat.status_code==200
    with pytest.raises(ConflictError):
        runtime.store.end_session(m.principal,conversation,1,request_review=True,idle_seconds=120)
    assert m.post(f"/conversations/{conversation}/activity",{},
        {"Cookie":m.headers["Cookie"]}).status_code==403
    age(m,conversation)
    m.flags['decision_fail']=True
    runtime.review_idle(resolve)
    finish_workers(runtime)
    progress=runtime.store.review_progress(m.principal,conversation)
    assert progress[0]['state']=='open'
    sealed=progress[1]
    assert (sealed['firstTurnOrdinal'],sealed['lastTurnOrdinal'])==(0,0)
    assert sealed['memoryState']=='completed' and sealed['decisionState']=='failed'
    assert len(calls)==1
    with psycopg.connect(m.url) as c:
        coverage,dispositions=c.execute("SELECT coverage_json,dispositions_json FROM vault_private.vault_chat_memory_reviews").fetchone()
        assert coverage['sourceCount']==2
        assert any(s['outcomes']==['active'] for s in coverage['sources'])
        assert any(s['outcomes']==['reviewed_no_memory_proposal'] for s in coverage['sources'])
        assert dispositions[0]['memoryId']
        c.execute("UPDATE vault_private.vault_conversation_segments SET review_due_at=now() WHERE segment_id=%s",(sealed['segmentId'],))
    m.flags['decision_fail']=False
    runtime._start_review(m.principal,conversation,sealed['segmentId'])
    finish_workers(runtime)
    assert len(calls)==1  # Completed factual consumer was not called again.
    progress=runtime.store.review_progress(m.principal,conversation)
    assert progress[1]['decisionState']==progress[1]['memoryState']=='completed'
    assert progress[1]['decisionResult']['publicationState']=='no_change'
    assert progress[1]['decisionResult']['reviewId']
    assert progress[1]['memoryResult']['storedCount']==1
    with psycopg.connect(m.url) as c:
        assert c.execute("SELECT count(*) FROM vault_private.vault_memory_records").fetchone()[0]==1
        assert c.execute("SELECT source_coverage_json FROM vault_private.vault_decision_reviews WHERE state='completed'").fetchone()[0]['sourceIds']
    status=m.app.handle(method='GET',target=f'/conversations/{conversation}/review-status',headers=m.headers)
    assert status.status_code==200 and status.payload['idleSeconds']==120
    # New turns stay in the same conversation and belong only to its new segment.
    next_turn=m.post(f'/conversations/{conversation}/turns',dict(submissionKey='continued',
        input='Thanks',expectedHistoryVersion=1),m.headers)
    assert next_turn.status_code==202
    assert wait(m,conversation,next_turn.payload['turnId'])['state']=='completed'
    with psycopg.connect(m.url) as c:
        assert c.execute("SELECT count(DISTINCT segment_id) FROM vault_private.vault_conversation_turns WHERE conversation_id=%s",(conversation,)).fetchone()[0]==2
    assert len(calls)==1


def test_empty_memory_output_has_completed_coverage_not_unreviewed(mounted):
    m=mounted
    conversation,runtime,_,_=configure(m,bad_citation=True)
    resolve=LocalIdentityRepository(database_url=m.url).resolve_review_principal
    age(m,conversation)
    runtime.review_idle(resolve)
    finish_workers(runtime)
    segment=runtime.store.review_progress(m.principal,conversation)[1]
    assert segment['memoryState']=='failed' and segment['decisionState']=='completed'
    decision_calls=len(m.calls)
    class Reviewer:
        def review(self,text):
            return MemoryReview('Nothing durable to store',(),'gpt-5.6-sol')
    runtime.memory_learning.voice_learning._reviewer_factory=lambda *_:Reviewer()
    with psycopg.connect(m.url) as c:
        c.execute("UPDATE vault_private.vault_conversation_segments SET review_due_at=now() WHERE segment_id=%s",(segment['segmentId'],))
    runtime._start_review(m.principal,conversation,segment['segmentId'])
    finish_workers(runtime)
    segment=runtime.store.review_progress(m.principal,conversation)[1]
    assert segment['memoryState']==segment['decisionState']=='completed'
    assert len(m.calls)==decision_calls  # Completed Decisions analysis/publication is not repeated.
    with psycopg.connect(m.url) as c:
        state,coverage,dispositions=c.execute("SELECT state,coverage_json,dispositions_json FROM vault_private.vault_chat_memory_reviews").fetchone()
        assert state=='completed' and dispositions==[]
        assert all(s['outcomes']==['reviewed_no_memory_proposal'] for s in coverage['sources'])
        assert c.execute("SELECT count(*) FROM vault_private.vault_memory_records").fetchone()[0]==0
