"""Chat reuses bounded Voice session handoff without replaying old transcripts."""
import json
from types import SimpleNamespace as NS

import psycopg

from app.vault_runtime.memory.contracts import MemoryReview
from tests.integration.test_mounted_voice_decision_review_postgres import mounted
from tests.integration.test_mounted_conversation_runtime_postgres import create,wait
from tests.integration.test_mounted_chat_memory_learning_postgres import finish_workers


def test_chat_continues_across_large_retained_history_with_original_summary(mounted):
    m=mounted
    conversation=create(m)
    runtime=m.app._conversation_runtime
    source=runtime.decision_review.source
    runtime.decision_review=None
    learning=runtime.memory_learning
    learning.voice_learning._embedder_factory=None
    _,model=learning._model_identity(m.principal)
    reviews=[]
    def review(text):
        reviews.append(text)
        return MemoryReview('Original completed handoff',(),model)
    reviewer=NS(review=review,review_page=lambda text:(review(text),False),
        consolidate_summary=lambda _:('Original completed handoff',model))
    learning.voice_learning._reviewer_factory=lambda *_:reviewer
    runs=[]
    async def runner(**kwargs):
        runs.append(kwargs)
        kwargs['model_response_sink'](NS(response_id='response',output=[NS(type='message',id='answer',
            role='assistant',content=[NS(type='output_text',text='Understood')])]))
        return 'Understood'
    runtime.runner=runner
    prior_segments=[]
    for ordinal in range(6):
        response=m.post(f'/conversations/{conversation}/turns',dict(submissionKey=f'context-{ordinal}',
            input='x'*55000 if ordinal<5 else 'Continue with the context we discussed',
            expectedHistoryVersion=ordinal),m.headers)
        assert response.status_code==202,response.payload
        turn=response.payload['turnId']
        assert wait(m,conversation,turn)['state']=='completed'
        supplied=json.loads(runs[-1]['input_text'])
        assert [h['turnId'] for h in supplied['history']]==[turn]
        captured=next(e['payload'] for e in runtime.store.events(m.principal,conversation,turn) if e['kind']=='context')
        assert captured['historySegmentId']==runtime.store.turn(m.principal,conversation,turn).segment_id
        if ordinal:
            assert captured['previousSummary']['segmentId']==prior_segments[-1]
            assert captured['previousSummary']['text']=='Original completed handoff'
            assert 'untrusted recalled context' in runs[-1]['instructions']
        else:
            assert captured['previousSummary'] is None
        ended=runtime.end_session(m.principal,conversation,ordinal+1)
        finish_workers(runtime)
        prior_segments.append(ended['segmentId'])
    snapshot=source.load_segment(m.principal,conversation,prior_segments[-1])
    assert snapshot.coverage=='complete'
    assert {p.final_source_id for p in snapshot.observations}=={'chat-final:'+turn}
    before=len(reviews)
    assert learning.previous_summary(m.principal,conversation,prior_segments[-1])['segmentId']==prior_segments[-2]
    assert len(reviews)==before and len(runs)==6
    with psycopg.connect(m.url) as connection:
        assert connection.execute('SELECT count(*),sum(octet_length(input_text)) FROM vault_private.vault_conversation_turns').fetchone()==(6,275000+len('Continue with the context we discussed'))
        connection.execute("UPDATE vault_private.vault_conversation_events SET payload=jsonb_set(payload,'{previousSummary,text}','\"Fabricated success\"'::jsonb) WHERE turn_id=%s AND kind='context'",(turn,))
    assert source.load_segment(m.principal,conversation,prior_segments[-1]).coverage=='unknown'
