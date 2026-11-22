"""Durable scheduling only, synthetic providers and the exact isolated DB fixture."""
import psycopg
import pytest
from threading import Event
from time import monotonic

from app.vault_runtime.conversation.contracts import ConflictError
from app.vault_runtime.conversation.runtime import REVIEW_WORKERS, ConversationRuntime
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from tests.support.mounted_chat_memory_learning import configure, finish_workers


def test_restart_discovery_lock_fencing_retry_and_authority(mounted):
    m=mounted
    conversation,runtime,calls,_=configure(m)
    runtime.decision_review=None
    # Seal without dispatch, as if the process died immediately after commit (reviews have their own pool).
    for _ in range(REVIEW_WORKERS):
        assert runtime._review_slots.acquire(blocking=False)
    try:
        ended=runtime.end_session(m.principal,conversation,1)
    finally:
        for _ in range(REVIEW_WORKERS):
            runtime._review_slots.release()
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



def test_reviews_never_take_the_owners_chat_slots_and_run_one_per_conversation(mounted):
    """2026-11-22: after a restart four reviews of one chat filled every slot and a Link message
    was refused as busy. Reviews use their own pool; a second review of the same chat waits."""
    m=mounted
    conversation,runtime,_calls,_=configure(m)
    for _ in range(REVIEW_WORKERS):
        assert runtime._review_slots.acquire(blocking=False)
    try:
        # Every review slot is busy, yet all four chat slots are still free for the owner.
        for _ in range(4):
            assert runtime._slots.acquire(blocking=False)
        for _ in range(4):
            runtime._slots.release()
    finally:
        for _ in range(REVIEW_WORKERS):
            runtime._review_slots.release()
    runtime._reviewing.add(conversation)
    try:
        before=runtime._review_slots._value
        runtime._start_review(m.principal,conversation,"segment-not-started")
        assert runtime._review_slots._value==before and "review:segment-not-started" not in runtime._workers
    finally:
        runtime._reviewing.discard(conversation)


def test_an_exhausted_review_stays_failed_and_retries_back_off(mounted):
    """2026-11-22: 118 segments kept failing because each chat turn re-armed them with fresh attempts."""
    m=mounted
    conversation,runtime,_calls,_=configure(m)
    runtime.decision_review=None
    for _ in range(REVIEW_WORKERS):
        assert runtime._review_slots.acquire(blocking=False)
    try:
        segment=runtime.end_session(m.principal,conversation,1)["segmentId"]
    finally:
        for _ in range(REVIEW_WORKERS):
            runtime._review_slots.release()
    scope=(m.principal.user_id,m.principal.workspace_id,conversation,segment)
    def row():
        with psycopg.connect(m.url) as c:
            return c.execute("""SELECT review_state,review_attempts,extract(epoch FROM review_due_at-now())
              FROM vault_private.vault_conversation_segments
              WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s""",scope).fetchone()
    # Backoff: the second failed attempt waits minutes, not 30 seconds.
    for attempt in (1,2):
        with psycopg.connect(m.url) as c:
            c.execute("""UPDATE vault_private.vault_conversation_segments SET review_state='running',
              review_attempts=%s WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s""",
              (attempt,*scope))
        assert runtime.store.finish_review(m.principal,conversation,segment,completed=False)[0]=="queued"
    assert row()[2]>200
    # Exhausted: re-queuing (what every chat turn does for the latest sealed segment) leaves it failed.
    with psycopg.connect(m.url) as c:
        c.execute("""UPDATE vault_private.vault_conversation_segments SET review_state='failed',review_attempts=3
          WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND segment_id=%s""",scope)
    with runtime.store._connect() as c,c.cursor() as cursor:
        runtime.store._queue_review(cursor,m.principal,conversation,segment)
    assert row()[:2]==("failed",3)
