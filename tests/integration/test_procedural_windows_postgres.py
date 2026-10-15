"""Actual captured tool decisions, same reviewer/lease/stage/publication owners."""
import json
from types import SimpleNamespace as NS

import psycopg

from tests.integration.test_mounted_voice_decision_review_postgres import mounted
from tests.integration.test_mounted_conversation_runtime_postgres import create,submit,wait
from tests.integration.test_mounted_chat_memory_learning_postgres import finish_workers


def test_mounted_procedural_window_retry_reuses_page_and_never_publishes_prefix(mounted):
    m=mounted
    conversation=create(m)
    runtime=m.app._conversation_runtime
    runtime.memory_learning=None
    runtime.authority.ensure_builtin_grants(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,
        definitions=m.app._voice_tools.definitions(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id))
    async def run(**kwargs):
        tool=next(t for t in kwargs['function_tools'] if t.name=='contacts_search')
        kwargs['model_response_sink'](NS(response_id='calls',output=[NS(type='function_call',id=f'item-{i}',
            call_id=f'call-{i}',name='contacts_search',arguments='{"query":"test"}') for i in range(18)]))
        # One executed call and17 abandoned original proposals exercise both
        # paths without spending this plumbing check on repeated DB tool work.
        for i in range(1):
            result=json.loads(await tool.on_invoke_tool(NS(tool_call_id=f'call-{i}'),'{"query":"test"}'))
            assert not result.get('isError',False)
        kwargs['model_response_sink'](NS(response_id='answer',output=[NS(type='message',id='answer',role='assistant',
            content=[NS(type='output_text',text='One lookup completed; other proposals were not executed')])]))
        return 'One lookup completed; other proposals were not executed'
    runtime.runner=run
    reviewer=runtime.decision_review
    base=reviewer.executor
    calls=[]
    publications=[]
    publish=reviewer.on_completed
    def completed(**kwargs):
        publications.append(len(kwargs['review'].output.assessments))
        return publish(**kwargs)
    reviewer.on_completed=completed
    def execute(**kwargs):
        assert kwargs['agent_name']=='Vault Decisions Window Review'
        payload=json.loads(kwargs['input_text']);calls.append(payload)
        if len(calls)==2:
            raise RuntimeError('Interrupted second assessment window')
        return dict(base(**dict(kwargs,agent_name='Vault Decisions Review',input_text=json.dumps(payload['evidence']))),has_more=False)
    reviewer.executor=execute
    turn=submit(m,conversation)
    assert wait(m,conversation,turn)['state']=='completed'
    ended=runtime.end_session(m.principal,conversation,1)
    finish_workers(runtime)
    assert publications==[]
    with psycopg.connect(m.url) as connection:
        row=connection.execute('SELECT state,source_coverage_json FROM vault_private.vault_decision_reviews').fetchone()
        assert row[0]=='retryable' and 'analysis_window_0_page_0' in row[1] and 'analysis' not in row[1]
        assert connection.execute('SELECT count(*) FROM vault_private.vault_decision_generations').fetchone()[0]==0
    runtime.end_session(m.principal,conversation,1)
    finish_workers(runtime)
    assert len(calls)==3 and len(calls[0]['evidence']['observations'])==16 and len(calls[2]['evidence']['observations'])==2
    assert calls[0]['evidence']['sources']==calls[2]['evidence']['sources']
    assert publications==[18]
    points=calls[0]['evidence']['observations']+calls[2]['evidence']['observations']
    assert sum(p['execution']=='completed' for p in points)==1
    assert sum(p['execution']=='not_requested' for p in points)==17
    with psycopg.connect(m.url) as connection:
        row=connection.execute('SELECT state,assessments_json FROM vault_private.vault_decision_reviews').fetchone()
        assert row[0]=='completed' and len(row[1])==18
        assert connection.execute('SELECT decision_review_state FROM vault_private.vault_conversation_segments WHERE segment_id=%s',(ended['segmentId'],)).fetchone()[0]=='completed'
        assert connection.execute('SELECT count(*) FROM vault_private.vault_decision_generations').fetchone()[0]==0


def test_mounted_oversized_procedural_input_resumes_original_source_windows(mounted,monkeypatch):
    m=mounted
    monkeypatch.setattr('app.vault_runtime.conversation.runtime_store.MAX_SEGMENT_TEXT_BYTES',1000000)
    runtime=m.app._conversation_runtime
    runtime.memory_learning=None
    conversation=create(m)
    answer='Original captured answer. '+('x'*28000)
    async def run(**kwargs):
        kwargs['model_response_sink'](NS(response_id='answer',output=[NS(type='message',id='answer',role='assistant',
            content=[NS(type='output_text',text=answer)])]))
        return answer
    runtime.runner=run
    for i in range(4):
        turn=submit(m,conversation,key=f'source-{i}',version=i)
        assert wait(m,conversation,turn)['state']=='completed'
    reviewer=runtime.decision_review
    base=reviewer.executor
    calls=[]
    fail=[True]
    def execute(**kwargs):
        payload=json.loads(kwargs['input_text'])
        calls.append((kwargs['agent_name'],payload))
        if kwargs['agent_name']=='Vault Decisions Source Review':
            if len(calls)==2 and fail[0]:
                fail[0]=False
                raise RuntimeError('Interrupted original source scan')
            return dict(reviewed_span_indexes=[s['span_index'] for s in payload['sources']],has_more=False,
                excerpts=[dict(span_index=s['span_index'],start=s['start'],end=s['start']+min(80,len(s['text'])),
                    text=s['text'][:80]) for s in payload['sources']])
        assert kwargs['agent_name']=='Vault Decisions Window Review'
        assert all('reviewed_excerpts' in s for s in payload['evidence']['sources'])
        return dict(base(**dict(kwargs,agent_name='Vault Decisions Review',input_text=json.dumps(payload['evidence']))),has_more=False)
    reviewer.executor=execute
    ended=runtime.end_session(m.principal,conversation,4)
    finish_workers(runtime)
    with psycopg.connect(m.url) as connection:
        row=connection.execute('SELECT state,source_coverage_json FROM vault_private.vault_decision_reviews').fetchone()
        assert row[0]=='retryable' and 'analysis_source_0_page_0' in row[1] and 'analysis' not in row[1]
        assert connection.execute('SELECT count(*) FROM vault_private.vault_decision_generations').fetchone()[0]==0
    first=calls[0][1]
    runtime.end_session(m.principal,conversation,4)
    finish_workers(runtime)
    assert sum(payload==first for _,payload in calls)==1
    with psycopg.connect(m.url) as connection:
        row=connection.execute('SELECT state,source_coverage_json,assessments_json FROM vault_private.vault_decision_reviews').fetchone()
        assert row[0]=='completed' and len(row[2])==4 and 'analysis_source_view' in row[1]
        assert connection.execute('SELECT decision_review_state FROM vault_private.vault_conversation_segments WHERE segment_id=%s',
            (ended['segmentId'],)).fetchone()[0]=='completed'
