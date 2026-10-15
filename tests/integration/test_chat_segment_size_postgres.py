"""Continuous activity reuses existing seal/continuation, without an idle wait."""
import json
from types import SimpleNamespace as NS

import psycopg
import pytest

from app.vault_runtime.conversation import runtime_store
from app.vault_runtime.conversation.contracts import ConflictError

from tests.integration.test_mounted_voice_decision_review_postgres import mounted
from tests.integration.test_mounted_conversation_runtime_postgres import create,wait
from tests.integration.test_mounted_chat_memory_learning_postgres import finish_workers


@pytest.mark.parametrize('first_text,turn_limit',[('x'*49000,32),('One turn',1)])
def test_size_boundary_preserves_originals_and_continues_same_chat(mounted,monkeypatch,first_text,turn_limit):
    m=mounted
    runtime=m.app._conversation_runtime
    runtime.memory_learning=None
    runtime.decision_review=None
    conversation=create(m)
    requests=[]
    async def runner(**kwargs):
        requests.append(json.loads(kwargs['input_text']))
        kwargs['model_response_sink'](NS(response_id='response',output=[NS(type='message',id='answer',
            role='assistant',content=[NS(type='output_text',text='Understood')])]))
        return 'Understood'
    runtime.runner=runner
    turns=[]
    monkeypatch.setattr(runtime_store,'MAX_SEGMENT_TURNS',turn_limit)
    for ordinal,text in enumerate((first_text,'Continue')):
        if ordinal:
            monkeypatch.setattr(runtime_store,'MAX_SEGMENT_TURNS',32)
        response=m.post(f'/conversations/{conversation}/turns',dict(submissionKey=f'size-{ordinal}',
            input=text,expectedHistoryVersion=ordinal),m.headers)
        assert response.status_code==202,response.payload
        turns.append(response.payload['turnId'])
        assert wait(m,conversation,turns[-1])['state']=='completed'
        finish_workers(runtime)
    assert [h['turnId'] for h in requests[-1]['history']]==[turns[-1]]
    with psycopg.connect(m.url) as connection:
        assert connection.execute('SELECT state FROM vault_private.vault_conversation_segments ORDER BY ordinal').fetchall()==[('sealed',),('open',)]
        assert connection.execute('SELECT input_text FROM vault_private.vault_conversation_turns ORDER BY ordinal').fetchall()==[(first_text,),('Continue',)]
        assert connection.execute('SELECT history_version FROM vault_private.vault_conversations').fetchone()==(2,)
    # Below threshold is a no-op, not an empty extra segment or a history write.
    assert runtime.store.end_session(m.principal,conversation,None,size_only=True) is None
    runtime.store.submit_text(m.principal,conversation,'pending','Still working',2,require_idle=True)
    monkeypatch.setattr(runtime_store,'MAX_SEGMENT_TURNS',1)
    with pytest.raises(ConflictError,match='active response'):
        runtime.store.end_session(m.principal,conversation,None,size_only=True)
