"""Actual mounted submitted-text boundary; synthetic provider, isolated real DB."""
import asyncio
import json
from threading import Event
from time import monotonic
from types import SimpleNamespace as NS

import pytest
import psycopg

from tests.integration.test_mounted_voice_decision_review_postgres import mounted


def create(m):
    m.app._conversation_runtime.memories._embedder_factory = None
    response = m.post('/conversations', {'createKey':'chat-test'}, m.headers)
    assert response.status_code == 201, response.payload
    return response.payload['conversationId']


def submit(m, conversation, key='send-one', version=0):
    response = m.post(f'/conversations/{conversation}/turns',
        {'submissionKey':key,'input':'Find my contacts','expectedHistoryVersion':version},m.headers)
    assert response.status_code == 202, response.payload
    return response.payload['turnId']


def wait(m, conversation, turn):
    deadline = monotonic()+10
    while monotonic()<deadline:
        response = m.app.handle(method='GET',target=f'/conversations/{conversation}/turns/{turn}',headers=m.headers)
        assert response.status_code == 200, response.payload
        if response.payload['state'] not in {'submitted','running'}:
            return response.payload
        Event().wait(.02)
    raise AssertionError('Bounded test turn did not finish')


def test_mounted_text_original_source_tool_stream_and_idempotent_send(mounted):
    m = mounted
    conversation = create(m)
    runtime = m.app._conversation_runtime
    runtime.authority.ensure_builtin_grants(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,
        definitions=m.app._voice_tools.definitions(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id))
    calls = []
    async def runner(**kwargs):
        calls.append(kwargs)
        assert kwargs['model']=='gpt-5.6-sol' and kwargs['agent_name']=='ReSono Voice Agent'
        kwargs['model_response_sink'](NS(response_id='response-one',output=[
            NS(type='reasoning',id='reason-one',summary=[NS(text='r'*17000)],encrypted_content='NEVER CAPTURE'),
            NS(type='function_call',id='item-one',call_id='call-one',name='contacts_search',arguments='{"query":"test"}')]))
        tool = next(t for t in kwargs['function_tools'] if t.name=='contacts_search')
        result = json.loads(await tool.on_invoke_tool(NS(tool_call_id='call-one'),' {"query":"test"}'))
        assert result.get('isError',False) is False
        kwargs['model_response_sink'](NS(response_id='response-two',output=[NS(type='message',id='answer',role='assistant',
            content=[NS(type='output_text',text='Done')])]))
        kwargs['text_delta_sink']('Done')
        return 'Done'
    runtime.runner = runner
    turn = submit(m,conversation)
    status = wait(m,conversation,turn)
    assert status['state']=='completed' and status['coverage']=='complete', status
    assert submit(m,conversation)==turn and len(calls)==1
    changed = m.post(f'/conversations/{conversation}/turns',
        {'submissionKey':'send-one','input':'Changed text','expectedHistoryVersion':0},m.headers)
    assert changed.status_code==409
    invalid = m.post(f'/conversations/{conversation}/turns',
        {'submissionKey':'send-one','input':'Find my contacts','expectedHistoryVersion':True},m.headers)
    assert invalid.status_code==400
    history = runtime.store.history(m.principal,conversation)
    assert history[0]['toolResults'][0]['callId']=='call-one'
    assert history[0]['toolResults'][0]['result']['isError'] is False
    assert history[0]['originalSources'][0]['kind']=='model_response'
    events = runtime.store.events(m.principal,conversation,turn)
    source = next(e for e in events if e['kind']=='model_response')['payload']
    assert source['output'][0]['summary']==['r'*17000]
    assert 'NEVER CAPTURE' not in json.dumps(events)
    assert any(e['kind']=='tool_status' and e['payload']['state']=='succeeded' for e in events)
    stream = m.app.handle(method='GET',target=f'/conversations/{conversation}/turns/{turn}/events?after=1',headers=m.headers)
    assert stream.status_code==200 and stream.stream is not None
    wire = b''.join(stream.stream).decode()
    assert 'id: 1\n' not in wire and 'assistant_final' in wire and 'terminal' in wire
    assert m.app.handle(method='GET',target=f'/conversations/{conversation}/turns/{turn}/events?after=-1',headers=m.headers).status_code==400
    replay_headers = dict(m.headers,**{'last-event-id':str(status['lastSequence'])})
    resumed = m.app.handle(method='GET',target=f'/conversations/{conversation}/turns/{turn}/events',headers=replay_headers)
    assert b''.join(resumed.stream)==b''
    with psycopg.connect(m.url) as connection:
        row = connection.execute('SELECT voice_session_id,conversation_id,turn_id,state FROM vault_private.vault_voice_tool_invocations').fetchone()
        assert row==(None,conversation,turn,'succeeded')
        assert connection.execute('SELECT count(*) FROM vault_private.vault_conversation_turns').fetchone()[0]==1
    denied = m.post(f'/conversations/{conversation}/turns',{}, {'Cookie':m.headers['Cookie']})
    assert denied.status_code==403
    assert m.app.handle(method='GET',target=f'/conversations/{conversation}',headers={}).status_code==403
    # Exercise the actual HTTP SSE emitter, not only a Python generator.
    from http.client import HTTPConnection
    from app.vault_runtime.local_api.server import VaultLocalServer
    server = VaultLocalServer(config=m.config,app=m.app)
    host,port = server.start()
    client = HTTPConnection(host,port,timeout=5)
    try:
        client.request('GET',f'/conversations/{conversation}/turns/{turn}/events',headers=m.headers)
        response = client.getresponse()
        assert response.status==200 and response.getheader('Content-Type').startswith('text/event-stream')
        assert response.getheader('Content-Length') is None
        assert b'terminal' in response.read()
    finally:
        client.close()
        server.stop()


def test_stop_and_missing_original_source_fail_closed(mounted,monkeypatch):
    m = mounted
    conversation = create(m)
    runtime = m.app._conversation_runtime
    entered = Event()
    async def waiting(**kwargs):
        entered.set()
        while not kwargs['cancel_requested']():
            await asyncio.sleep(.02)
        raise asyncio.CancelledError()
    runtime.runner = waiting
    turn = submit(m,conversation)
    assert entered.wait(5)
    # An active turn owns the conversation and execution lock; another startup
    # cannot interrupt it, nor can another Send bypass the idle guard.
    runtime.store.recover_orphans()
    competing = m.post(f'/conversations/{conversation}/turns',
        {'submissionKey':'competing','input':'Other request','expectedHistoryVersion':1},m.headers)
    assert competing.status_code==409
    assert submit(m,conversation)==turn
    stop = m.post(f'/conversations/{conversation}/turns/{turn}/stop',{},m.headers)
    assert stop.status_code==200
    assert wait(m,conversation,turn)['state']=='interrupted'
    async def unlinked(**kwargs):
        tool = next(t for t in kwargs['function_tools'] if t.name=='contacts_search')
        await tool.on_invoke_tool(NS(tool_call_id='uncaptured'),' {"query":"test"}')
        return 'Cannot reach this'
    runtime.runner = unlinked
    turn2 = submit(m,conversation,key='send-two',version=1)
    status = wait(m,conversation,turn2)
    assert status['state']=='failed' and status['coverage']=='incomplete'
    with psycopg.connect(m.url) as connection:
        assert connection.execute('SELECT count(*) FROM vault_private.vault_voice_tool_invocations').fetchone()[0]==0
    # Failure to start a worker releases capacity and terminates its owned claim.
    from app.vault_runtime.conversation import runtime as runtime_module
    def failed_start(_):
        raise RuntimeError('Synthetic worker start failure')
    with monkeypatch.context() as patch:
        patch.setattr(runtime_module.Thread,'start',failed_start)
        failed = m.post(f'/conversations/{conversation}/turns',
            {'submissionKey':'start-failure','input':'Not executed','expectedHistoryVersion':2},m.headers)
        assert failed.status_code==503
    replay = m.post(f'/conversations/{conversation}/turns',
        {'submissionKey':'start-failure','input':'Not executed','expectedHistoryVersion':2},m.headers)
    assert replay.status_code==202 and replay.payload['state']=='failed'
    # A stale source with no executing owner is marked interrupted, never rerun.
    orphan = runtime.store.submit_text(m.principal,conversation,'orphan','Old request',3)
    with psycopg.connect(m.url) as connection:
        connection.execute("UPDATE vault_private.vault_conversation_turns SET updated_at=now()-interval '11 minutes' WHERE turn_id=%s",(orphan.turn_id,))
    runtime.store.recover_orphans()
    assert runtime.store.status(m.principal,conversation,orphan.turn_id)['state']=='interrupted'


def test_real_write_capture_failure_is_not_reexecuted_and_denial_has_no_claim(mounted):
    m = mounted
    conversation = create(m)
    runtime = m.app._conversation_runtime
    runtime.authority.ensure_builtin_grants(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,
        definitions=m.app._voice_tools.definitions(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id))
    original_append = runtime.store.append
    def capture_failure(principal,turn,owner,kind,payload):
        if kind=='tool_status' and payload['state']=='succeeded':
            raise ValueError('Synthetic capture failure after actual effect')
        return original_append(principal,turn,owner,kind,payload)
    runtime.store.append = capture_failure
    calls = []
    async def runner(**kwargs):
        calls.append(True)
        args = {'fileKey':'conversation-proof.txt','content':'actual scoped text write'}
        raw = json.dumps(args)
        kwargs['model_response_sink'](NS(output=[NS(type='function_call',name='workspace_write_file',
            call_id='write-one',arguments=raw)]))
        tool = next(t for t in kwargs['function_tools'] if t.name=='workspace_write_file')
        await tool.on_invoke_tool(NS(tool_call_id='write-one'),raw)
        return 'unreachable'
    runtime.runner = runner
    turn = submit(m,conversation)
    status = wait(m,conversation,turn)
    assert status['state']=='failed' and status['coverage']=='incomplete'
    with psycopg.connect(m.url) as connection:
        assert connection.execute("SELECT state FROM vault_private.vault_voice_tool_invocations WHERE tool_call_id='write-one'").fetchone()==('succeeded',)
        result = connection.execute('SELECT result_json FROM vault_private.vault_voice_tool_results').fetchone()[0]
        assert result['isError'] is False
    assert submit(m,conversation)==turn and len(calls)==1
    runtime.store.append = original_append
    with psycopg.connect(m.url) as connection:
        connection.execute("UPDATE vault_private.vault_voice_tool_grants SET status='revoked' WHERE tool_name='contacts_search'")
    async def denied(**kwargs):
        kwargs['model_response_sink'](NS(output=[NS(type='function_call',name='contacts_search',call_id='denied',arguments='{"query":"test"}')]))
        tool = next(t for t in kwargs['function_tools'] if t.name=='contacts_search')
        result = json.loads(await tool.on_invoke_tool(NS(tool_call_id='denied'),'{"query":"test"}'))
        assert result['isError'] is True
        return 'Tool access is not granted.'
    runtime.runner = denied
    next_turn = submit(m,conversation,key='denial',version=1)
    assert wait(m,conversation,next_turn)['state']=='completed'
    with psycopg.connect(m.url) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_voice_tool_invocations WHERE tool_call_id='denied'").fetchone()[0]==0


def test_display_history_pages_large_retained_chat_without_model_or_tools(mounted):
    m = mounted
    conversation = create(m)
    runtime = m.app._conversation_runtime
    # Canonical rows simulate retained history independently of provider work.
    with psycopg.connect(m.url) as connection:
        segment = connection.execute("SELECT segment_id FROM vault_private.vault_conversation_segments").fetchone()[0]
        for ordinal in range(1, 302):
            connection.execute("""INSERT INTO vault_private.vault_conversation_turns
                (turn_id,conversation_id,segment_id,user_id,workspace_id,ordinal,
                 submission_key,input_text,input_fingerprint,submitted_history_version,state)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'completed')""",
                (f'page-{ordinal}',conversation,segment,m.principal.user_id,m.principal.workspace_id,
                 ordinal,f'page-{ordinal}','x'*1000,'a'*64,ordinal-1))
    pages = []
    target = f'/conversations/{conversation}'
    while True:
        response = m.app.handle(method='GET',target=target,headers=m.headers)
        assert response.status_code == 200, response.payload
        page = response.payload
        assert 0 < len(page['turns']) <= 40
        pages = page['turns'] + pages
        if page['nextBefore'] is None:
            break
        target = f"/conversations/{conversation}?before={page['nextBefore']}"
    assert [t['turnId'] for t in pages] == [f'page-{i}' for i in range(1,302)]
    for query in ('before=-1','before=nope','before=1&before=2','unknown=1'):
        assert m.app.handle(method='GET',target=f'/conversations/{conversation}?{query}',headers=m.headers).status_code == 400
    assert m.app.handle(method='GET',target=f'/conversations/{conversation}',headers={}).status_code == 403
    with psycopg.connect(m.url) as connection:
        assert connection.execute('SELECT count(*) FROM vault_private.vault_conversation_events').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM vault_private.vault_voice_tool_invocations').fetchone()[0] == 0


def test_chat_memory_confirmations_use_original_later_turn_and_atomic_pending_action(mounted,monkeypatch):
    from app.vault_runtime.memory.repository import MemoryConfirmationError
    from tests.integration.test_memory_postgres import _candidate
    from app.vault_runtime.memory.analysis_spans import source_reference
    import pytest
    m=mounted
    conversation=create(m)
    runtime=m.app._conversation_runtime
    repo=runtime.memory_learning.memories
    turn=runtime.store.submit_text(m.principal,conversation,'prepare','Change my preference',0)
    with psycopg.connect(m.url) as c:
        c.execute("UPDATE vault_private.vault_conversation_turns SET state='completed' WHERE turn_id=%s",(turn.turn_id,))
    fact=repo.reconcile_memory(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,
        voice_session_id=conversation,candidate=_candidate(content='Prefers tea'),
        evidence=((None,'chat_user_statement','user_asserted',turn.input_text),),
        evidence_source_refs=(source_reference('chat-final:'+turn.turn_id,'user',turn.input_text),))
    scope=dict(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,
        conversation_id=conversation,local_session_id=m.principal.session_id)
    action=repo.prepare_action(**scope,turn_id=turn.turn_id,action_kind='correct',memory_id=fact.memory_id,proposed_content='Prefers coffee')
    with pytest.raises(MemoryConfirmationError):
        runtime.memories.confirm_action(**scope,turn_id=turn.turn_id,action_id=action)
    confirmation=runtime.store.submit_text(m.principal,conversation,'confirm','Yes, make that exact correction',1)
    with psycopg.connect(m.url) as c:
        c.execute("UPDATE vault_private.vault_conversation_turns SET state='completed' WHERE turn_id=%s",(confirmation.turn_id,))
    reconcile=repo.reconcile_memory
    def fail(**kwargs):
        reconcile(**kwargs)
        raise RuntimeError('publication failure')
    monkeypatch.setattr(repo,'reconcile_memory',fail)
    with pytest.raises(RuntimeError):
        runtime.memories.confirm_action(**scope,turn_id=confirmation.turn_id,action_id=action)
    with psycopg.connect(m.url) as c:
        assert c.execute('SELECT status FROM vault_private.vault_memory_pending_actions WHERE action_id=%s',(action,)).fetchone()[0]=='pending'
        assert c.execute('SELECT content_text FROM vault_private.vault_memory_records WHERE memory_id=%s',(fact.memory_id,)).fetchone()[0]=='Prefers tea'
    monkeypatch.setattr(repo,'reconcile_memory',reconcile)
    result=runtime.memories.confirm_action(**scope,turn_id=confirmation.turn_id,action_id=action)
    assert result.memory.content_text=='Prefers coffee'
    with pytest.raises(MemoryConfirmationError):
        runtime.memories.confirm_action(**scope,turn_id=confirmation.turn_id,action_id=action)
    with psycopg.connect(m.url) as c:
        assert c.execute('SELECT count(*) FROM vault_private.vault_transcript_entries').fetchone()[0]==0
        assert c.execute('SELECT source_ref_json FROM vault_private.vault_memory_evidence ORDER BY created_at DESC LIMIT 1').fetchone()[0]['sourceId']=='chat-final:'+confirmation.turn_id


def test_private_attachments_reach_model_and_freeze_on_idempotent_send(mounted):
    import base64
    m=mounted
    conversation=create(m)
    runtime=m.app._conversation_runtime
    factual_learning=runtime.memory_learning
    runtime.memory_learning=None
    runtime.decision_review=None
    calls=[]
    async def runner(**kwargs):
        calls.append(kwargs)
        content=kwargs['input_text'][0]['content']
        assert any(part['type']=='input_text' and 'Private attachment body' in part['text'] for part in content)
        kwargs['model_response_sink'](NS(response_id='attached',output=[NS(type='message',id='answer',role='assistant',
            content=[NS(type='output_text',text='Read the attached text')])]))
        return 'Read the attached text'
    runtime.runner=runner
    body=dict(uploadKey='upload-one',name='private.txt',dataBase64=base64.b64encode(b'Private attachment body').decode())
    staged=m.post(f'/conversations/{conversation}/attachments',body,m.headers)
    assert staged.status_code==201,staged.payload
    attachment=staged.payload['id']
    assert m.post(f'/conversations/{conversation}/attachments',body,m.headers).payload==staged.payload
    changed=dict(body,dataBase64=base64.b64encode(b'Changed').decode())
    assert m.post(f'/conversations/{conversation}/attachments',changed,m.headers).status_code==409
    wrong=m.post(f'/conversations/{conversation}/turns',dict(submissionKey='bad-file',input='Read it',expectedHistoryVersion=0,
        attachmentIds=['missing']),m.headers)
    assert wrong.status_code==400
    with psycopg.connect(m.url) as c:
        assert c.execute('SELECT count(*) FROM vault_private.vault_conversation_turns').fetchone()[0]==0
    request=dict(submissionKey='attached',input='Read it',expectedHistoryVersion=0,attachmentIds=[attachment])
    sent=m.post(f'/conversations/{conversation}/turns',request,m.headers)
    assert sent.status_code==202,sent.payload
    assert wait(m,conversation,sent.payload['turnId'])['state']=='completed'
    assert m.post(f'/conversations/{conversation}/turns',request,m.headers).payload['turnId']==sent.payload['turnId']
    assert len(calls)==1
    assert m.post(f'/conversations/{conversation}/turns',dict(request,attachmentIds=[]),m.headers).status_code==409
    removed=m.app.handle(method='DELETE',target=f'/conversations/{conversation}/attachments/{attachment}',headers=m.headers,body=b'{}')
    assert removed.status_code==400
    files=list(runtime.attachments.storage.user_root(m.principal.user_id).rglob(attachment))
    assert len(files)==1 and 'conversation-inputs' in str(files[0])
    assert not list(runtime.attachments.storage.workspace_files_root(m.principal.workspace_id).rglob(attachment))
    loaded=m.app.handle(method='GET',target=f'/conversations/{conversation}',headers=m.headers)
    assert loaded.payload['turns'][0]['attachments'][0]['id']==attachment
    again=m.post(f'/conversations/{conversation}/turns',dict(submissionKey='followup',input='Use the same document',expectedHistoryVersion=1),m.headers)
    assert again.status_code==202
    assert wait(m,conversation,again.payload['turnId'])['state']=='completed'
    assert len(calls)==2
    assert any('Private attachment body' in part.get('text','') for part in calls[-1]['input_text'][0]['content'])

    ended=runtime.store.end_session(m.principal,conversation,2,request_review=False)
    result=factual_learning.finalize(principal=m.principal,conversation_id=conversation,segment_id=ended['segmentId'])
    assert result['state']=='completed'
    assert len(m.calls)==1 and 'document:' in m.calls[0]['input_text']
    assert 'Private attachment body' in m.calls[0]['input_text']


def test_attachment_http_budget_expiry_and_private_scope(mounted):
    import base64
    import io
    from PIL import Image
    from dataclasses import replace
    m=mounted
    conversation=create(m)
    image=Image.effect_noise((1024,1024),100).convert('RGB')
    buffer=io.BytesIO()
    image.save(buffer,format='PNG',compress_level=0)
    raw=buffer.getvalue()
    assert len(raw)>1_048_576
    staged=m.post(f'/conversations/{conversation}/attachments',dict(uploadKey='large-image',name='input.png',
        dataBase64=base64.b64encode(raw).decode()),m.headers)
    assert staged.status_code==201,staged.payload
    identity=staged.payload['id']
    attachments=m.app._conversation_runtime.attachments
    with pytest.raises(Exception):
        attachments.metadata(replace(m.principal,user_id='foreign'),conversation,[] or ['missing'])
    with psycopg.connect(m.url) as connection:
        connection.execute("UPDATE vault_private.vault_conversation_attachments SET created_at=now()-interval '25 hours' WHERE attachment_id=%s",(identity,))
    assert attachments.cleanup_expired()==1
    with psycopg.connect(m.url) as connection:
        assert connection.execute('SELECT count(*) FROM vault_private.vault_conversation_attachments').fetchone()[0]==0
    assert not list(attachments.storage.user_root(m.principal.user_id).rglob(identity))


def test_original_image_is_read_by_both_learners_with_private_document_provenance(mounted):
    import base64
    import re
    from io import BytesIO
    from PIL import Image
    from app.vault_runtime.memory.openai_reviewer import OpenAIMemoryReviewer
    m=mounted
    runtime=m.app._conversation_runtime
    factual=runtime.memory_learning
    runtime.memory_learning=None
    conversation=create(m)
    image=BytesIO()
    Image.new('RGB',(24,24),'blue').save(image,format='PNG')
    encoded=base64.b64encode(image.getvalue()).decode()
    staged=m.post(f'/conversations/{conversation}/attachments',dict(uploadKey='learn-image',name='mascot.png',dataBase64=encoded),m.headers)
    assert staged.status_code==201
    async def run(**kwargs):
        assert any(p['type']=='input_image' for p in kwargs['input_text'][0]['content'])
        kwargs['model_response_sink'](NS(response_id='answer',output=[NS(type='message',id='answer',role='assistant',
            content=[NS(type='output_text',text='The project mascot is a blue square.')])]))
        return 'The project mascot is a blue square.'
    runtime.runner=run
    sent=m.post(f'/conversations/{conversation}/turns',dict(submissionKey='image-turn',
        input='Remember the project mascot shown in this image.',expectedHistoryVersion=0,
        attachmentIds=[staged.payload['id']]),m.headers)
    assert sent.status_code==202
    assert wait(m,conversation,sent.payload['turnId'])['state']=='completed'
    ended=runtime.store.end_session(m.principal,conversation,1,request_review=False)
    calls=[]
    base=runtime.decision_review.executor
    def execute(**kwargs):
        content=kwargs['input_text'][0]['content']
        assert next(p['image_url'] for p in content if p['type']=='input_image')=='data:image/png;base64,'+encoded
        text=content[0]['text']
        calls.append(kwargs['agent_name'])
        if kwargs['agent_name']=='Vault Memory Review':
            index=int(re.search(r'\[entryIndex=(\d+)\] \[attachment:',text).group(1))
            return dict(contractVersion=2,summary='Original image reviewed',candidates=[dict(domain='project',
                memoryType='fact',stableKey='project.mascot',content='The project mascot is a blue square.',
                sourceEntryIndexes=[index],sourceAuthority='model_derived',confidence='medium',sensitivity='normal',
                reconciliationIntent='create',shouldStore=True)])
        return base(**dict(kwargs,input_text=text))
    m.app._voice_learning._reviewer_factory=lambda u,w:OpenAIMemoryReviewer(credentials=m.app._voice_provider_credentials,
        user_id=u,workspace_id=w,executor=execute)
    runtime.decision_review.executor=execute
    result=factual.finalize(principal=m.principal,conversation_id=conversation,segment_id=ended['segmentId'])
    assert result['state']=='completed' and result['memoryCount']==1
    snapshot=runtime.decision_review.source.load_segment(m.principal,conversation,ended['segmentId'])
    assert snapshot.coverage=='complete'
    result=runtime.decision_review.finalize_source(principal=m.principal,session_id=conversation,snapshot=snapshot)
    assert result['state']=='completed' and result['coverage']=='complete'
    assert calls==['Vault Memory Review','Vault Decisions Review']
    with psycopg.connect(m.url) as connection:
        evidence=connection.execute("SELECT evidence_kind,source_authority,source_ref_json FROM vault_private.vault_memory_evidence").fetchone()
        assert evidence[0]=='chat_document_observation' and evidence[1]=='model_derived'
        assert evidence[2]['role']=='document' and evidence[2]['sourceId'].startswith('attachment:'+staged.payload['id']+':')
    # Changed original bytes invalidate qualification rather than trusting metadata.
    path=next(runtime.attachments.storage.user_root(m.principal.user_id).rglob(staged.payload['id']))
    path.write_bytes(b'changed original image')
    from app.vault_runtime.conversation.contracts import ConflictError
    with pytest.raises(ConflictError):
        runtime.decision_review.source.load_segment(m.principal,conversation,ended['segmentId'])
