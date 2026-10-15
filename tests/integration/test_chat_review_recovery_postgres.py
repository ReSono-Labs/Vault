"""Durable scheduling only, synthetic providers and the exact isolated DB fixture."""
import psycopg
import pytest
from threading import Event
from time import monotonic

from app.vault_runtime.conversation.contracts import ConflictError
from app.vault_runtime.conversation.runtime import ConversationRuntime
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from tests.integration.test_mounted_voice_decision_review_postgres import mounted
from tests.integration.test_mounted_chat_memory_learning_postgres import configure,finish_workers


def test_restart_discovery_lock_fencing_retry_and_authority(mounted):
    m=mounted
    conversation,runtime,calls,_=configure(m)
    runtime.decision_review=None
    # Seal without dispatch, as if the process died immediately after commit.
    for _ in range(4):
        assert runtime._slots.acquire(blocking=False)
    try:
        ended=runtime.end_session(m.principal,conversation,1)
    finally:
        for _ in range(4):
            runtime._slots.release()
    segment=ended["segmentId"]
    assert runtime.store.pending_reviews()==[(m.principal.user_id,m.principal.workspace_id,
        conversation,segment,m.principal.session_id)]
    lock=runtime.store.execution_lock("review-dispatch:"+segment)
    try:
        assert runtime.store.claim_review(m.principal,conversation,segment)
        with pytest.raises(ConflictError):
            runtime.store.execution_lock("review-dispatch:"+segment)
    finally:
        lock.close()  # A dead process releases exactly this connection-owned lock.
    resumed=ConversationRuntime(database_url=m.url,credentials=runtime.credentials,memories=runtime.memories,
        catalog=runtime.catalog,authority=runtime.authority)
    resumed.memory_learning=runtime.memory_learning
    try:
        resumed.start_review_recovery(LocalIdentityRepository(database_url=m.url).resolve_review_principal)
        deadline=monotonic()+10
        while not calls and monotonic()<deadline:
            Event().wait(.02)
        finish_workers(resumed)
    finally:
        resumed.close()
    assert len(calls)==1 and runtime.store.pending_reviews()==[]
    with psycopg.connect(m.url) as connection:
        assert connection.execute("SELECT review_state,review_attempts FROM vault_private.vault_conversation_segments WHERE segment_id=%s",
            (segment,)).fetchone()==("completed",2)
        connection.execute("UPDATE vault_private.vault_conversation_segments SET review_state='running',review_attempts=3,review_due_at=now() WHERE segment_id=%s",(segment,))
    runtime._start_review(m.principal,conversation,segment)
    assert len(calls)==1 and runtime.store.pending_reviews()==[]
    # An explicit retry can requeue exhausted work; revocation still forbids reads.
    runtime.store.end_session(m.principal,conversation,1,request_review=True)
    with psycopg.connect(m.url) as connection:
        connection.execute("UPDATE vault_private.local_sessions SET status='revoked',revoked_at=now() WHERE session_id=%s",(m.principal.session_id,))
    with pytest.raises(Exception):
        runtime.store.claim_review(m.principal,conversation,segment)
    assert len(calls)==1
