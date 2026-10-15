"""Mounted long Chat review resumes validated pages against isolated PostgreSQL."""
import json
import re
from types import SimpleNamespace as NS

import psycopg
import pytest

from app.vault_runtime.memory.contracts import MemoryCandidate,MemoryReview,ReviewedMemoryCandidate
from tests.integration.test_mounted_voice_decision_review_postgres import mounted
from tests.integration.test_mounted_conversation_runtime_postgres import create,wait
from tests.integration.test_mounted_chat_memory_learning_postgres import finish_workers


def test_long_chat_pages_resume_and_publication_is_atomic(mounted,monkeypatch):
    m=mounted
    # Exercise one oversized sealed source rather than automatic size checkpoints.
    monkeypatch.setattr("app.vault_runtime.conversation.runtime_store.MAX_SEGMENT_TEXT_BYTES", 1_000_000)
    conversation=create(m)
    runtime=m.app._conversation_runtime
    runtime.decision_review=None
    learning=runtime.memory_learning
    learning.voice_learning._embedder_factory=None
    _,model=learning._model_identity(m.principal)
    calls=[]
    failed=False
    def page(text,**kwargs):
        nonlocal failed
        payload=json.loads(text)
        calls.append(payload)
        if len(calls)==2 and not failed:
            failed=True
            raise RuntimeError('Interrupted second page')
        # Dense first source plus a fact after the old 100k review boundary.
        remaining=[i for i in range(40) if f'fact-{i}' not in payload['excludedKeys']] if 'FORTY FACTS' in payload['evidence'] else []
        if 'LATE FACT' in payload['evidence'] and 'fact-40' not in payload['excludedKeys']:
            remaining.append(40)
        def citation(i):
            marker='LATE FACT' if i==40 else 'FORTY FACTS'
            return int(re.findall(r'\[entryIndex=(\d+)\]',payload['evidence'].split(marker)[0])[-1])
        candidates=tuple(ReviewedMemoryCandidate(MemoryCandidate(m.principal.user_id,'personal','fact',
            f'fact-{i}',f'User fact {i}','user_asserted','high','normal','create'),(citation(i),))
            for i in remaining[:32])
        return MemoryReview('Reviewed original evidence',candidates,model),len(remaining)>32
    reviewer=NS(review_page=page,consolidate_summary=lambda _:('Consolidated source summary',model))
    learning.voice_learning._reviewer_factory=lambda *_:reviewer
    async def runner(**kwargs):
        kwargs['model_response_sink'](NS(response_id='response',output=[NS(type='message',id='answer',
            role='assistant',content=[NS(type='output_text',text='Understood')])]))
        return 'Understood'
    runtime.runner=runner
    for ordinal in range(3):
        response=m.post(f'/conversations/{conversation}/turns',dict(submissionKey=f'long-{ordinal}',
            input=('FORTY FACTS ' if ordinal==0 else '')+'x'*44000+(' LATE FACT' if ordinal==2 else ''),expectedHistoryVersion=ordinal),m.headers)
        assert response.status_code==202,response.payload
        assert wait(m,conversation,response.payload['turnId'])['state']=='completed'
    ended=runtime.end_session(m.principal,conversation,3)
    finish_workers(runtime)
    with psycopg.connect(m.url) as connection:
        assert connection.execute('SELECT count(*) FROM vault_private.vault_chat_memory_analysis_steps').fetchone()[0]==1
        assert connection.execute('SELECT count(*) FROM vault_private.vault_memory_records').fetchone()[0]==0
    reconcile=learning.memories.reconcile_memory
    def interrupted(**kwargs):
        reconcile(**kwargs)
        raise RuntimeError('Publication interrupted after write')
    monkeypatch.setattr(learning.memories,'reconcile_memory',interrupted)
    arguments=dict(principal=m.principal,conversation_id=conversation,segment_id=ended['segmentId'])
    with pytest.raises(RuntimeError,match='Publication interrupted'):
        learning.finalize(**arguments)
    count=len(calls)
    with psycopg.connect(m.url) as connection:
        assert connection.execute('SELECT count(*) FROM vault_private.vault_memory_records').fetchone()[0]==0
        assert connection.execute('SELECT state,review_json FROM vault_private.vault_chat_memory_reviews').fetchone()==('reviewed',{'windowed':1})
    monkeypatch.setattr(learning.memories,'reconcile_memory',reconcile)
    result=learning.finalize(**arguments)
    assert result['memoryCount']==41 and len(calls)==count
    assert learning.finalize(**arguments)['alreadyCompleted'] and len(calls)==count
    with psycopg.connect(m.url) as connection:
        assert connection.execute('SELECT count(*),max(current_version) FROM vault_private.vault_memory_records').fetchone()==(41,1)
        references=connection.execute('SELECT source_ref_json FROM vault_private.vault_memory_evidence').fetchall()
        assert references and all(row[0]['sourceLength']>16384 and row[0]['end']-row[0]['start']<=12000 for row in references)
        tail=connection.execute("SELECT e.evidence_text FROM vault_private.vault_memory_evidence e JOIN vault_private.vault_memory_record_versions v USING(version_id) JOIN vault_private.vault_memory_records r USING(memory_id) WHERE r.content_text='User fact 40'").fetchone()
        assert tail and 'LATE FACT' in tail[0]
