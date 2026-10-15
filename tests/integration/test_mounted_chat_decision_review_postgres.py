"""Actual composition/worker/review checkpoint, no provider network calls."""
import json
from threading import Event
from time import monotonic
from types import SimpleNamespace as NS
import psycopg

from tests.integration.test_mounted_voice_decision_review_postgres import mounted
from tests.integration.test_mounted_conversation_runtime_postgres import create, submit, wait


def test_completed_chat_worker_runs_shared_review_once_with_real_source_links(mounted):
    m = mounted
    conversation = create(m)
    runtime = m.app._conversation_runtime
    reviewer = runtime.decision_review
    reviews = []
    original = reviewer.executor
    def execute(**kwargs):
        reviews.append(json.loads(kwargs["input_text"]))
        return original(**kwargs)
    reviewer.executor = execute
    async def runner(**kwargs):
        kwargs["model_response_sink"](NS(response_id="r",output=[NS(type="message",id="a",
            role="assistant",content=[NS(type="output_text",text="A direct answer")])]))
        return "A direct answer"
    runtime.runner = runner
    turn = submit(m, conversation)
    assert wait(m, conversation, turn)["state"] == "completed"
    context = next(e["payload"] for e in runtime.store.events(m.principal,conversation,turn) if e["kind"]=="context")
    assert context["captureVersion"] == 3 and context["historyTurnIds"] == [turn]
    assert len(context["historyFingerprint"]) == 64 and isinstance(context["suppliedTools"],list)
    assert not reviews  # No repeated growing-prefix model review per turn.
    ended = m.post(f"/conversations/{conversation}/end-session",{"expectedHistoryVersion":1},m.headers)
    assert ended.status_code == 202, ended.payload
    segment_id = ended.payload["segmentId"]
    deadline = monotonic()+10
    result = None
    while monotonic()<deadline:
        snapshot = reviewer.source.load_segment(m.principal, conversation, segment_id)
        result = reviewer.repository.for_source(m.principal, snapshot)
        if result and result[1] == "completed":
            break
        Event().wait(.02)
    assert result and result[1] == "completed"
    assert len(reviews) == 1 and reviews[0]["coverage"] == "complete"
    point, = reviews[0]["observations"]
    assert point["final_source_id"] == "chat-final:"+turn
    assert point["answer_source_id"] and point["context_source_ids"]
    assert point["request_outcome"] == "unknown"
    retry = reviewer.finalize_source(principal=m.principal,session_id=conversation,snapshot=snapshot)
    assert retry["alreadyCompleted"] is True and len(reviews) == 1
    assert submit(m, conversation) == turn and len(reviews) == 1
    retried = m.post(f"/conversations/{conversation}/end-session",{"expectedHistoryVersion":1},m.headers)
    assert retried.status_code == 202 and retried.payload["segmentId"] == segment_id
    assert retried.payload["alreadyEnded"] is True
    second = submit(m,conversation,key="second",version=1)
    assert wait(m,conversation,second)["state"] == "completed"
    first_turn = runtime.store.turn(m.principal,conversation,turn)
    second_turn = runtime.store.turn(m.principal,conversation,second)
    assert first_turn.segment_id != second_turn.segment_id
    with reviewer.repository._connect() as connection,connection.cursor() as cursor:
        assert reviewer.source.current(cursor,m.principal,snapshot) is True
    assert len(reviews) == 1
    # The next ended contribution sees previous canonical context, but does not
    # count old decision points again as new observations.
    next_end = m.post(f"/conversations/{conversation}/end-session",{"expectedHistoryVersion":2},m.headers)
    assert next_end.status_code == 202
    next_snapshot = reviewer.source.load_segment(m.principal,conversation,next_end.payload["segmentId"])
    assert next_snapshot.coverage == "complete"
    assert {p.final_source_id for p in next_snapshot.observations} == {"chat-final:"+second}


def test_forgotten_context_invalidates_qualified_chat_source_without_erasing_history(mounted):
    from tests.integration.test_memory_postgres import _candidate, _entry
    m = mounted
    conversation = create(m)
    runtime = m.app._conversation_runtime
    memories = runtime.memories._repository
    entry = _entry(memories,m.principal,session="contact-fact",index=0,text="Contacts directory includes Sarah")
    memory = memories.reconcile_memory(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,
        voice_session_id="contact-fact",candidate=_candidate(content="Contacts directory includes Sarah"),
        evidence=((entry.entry_id,"user_statement","user_asserted",entry.text_content),))
    async def runner(**kwargs):
        kwargs["model_response_sink"](NS(response_id="r",output=[NS(type="message",id="a",
            role="assistant",content=[NS(type="output_text",text="Your contacts include Sarah")])]))
        return "Your contacts include Sarah"
    runtime.runner = runner
    turn = submit(m,conversation)
    assert wait(m,conversation,turn)["state"] == "completed"
    captured = next(e["payload"] for e in runtime.store.events(m.principal,conversation,turn) if e["kind"]=="context")
    assert any(item["memoryId"]==memory.memory_id for item in captured["memories"])
    ended = runtime.end_session(m.principal,conversation,1)
    source = runtime.decision_review.source
    snapshot = source.load_segment(m.principal,conversation,ended["segmentId"])
    assert snapshot.coverage == "complete"
    memories.delete_memory(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,memory_id=memory.memory_id)
    with source._connect() as connection,connection.cursor() as cursor:
        assert source.current(cursor,m.principal,snapshot) is False
    assert source.load_segment(m.principal,conversation,ended["segmentId"]).coverage == "unknown"
    assert runtime.store.history(m.principal,conversation)[0]["answer"] == "Your contacts include Sarah"


def test_qualified_chat_publishes_real_indexed_examples_without_repeating_review(mounted):
    m = mounted
    conversation = create(m)
    runtime = m.app._conversation_runtime
    runtime.authority.ensure_builtin_grants(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,
        definitions=m.app._voice_tools.definitions(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id))
    reviewer = runtime.decision_review
    calls, embedded = [], []
    class Embedder:
        model_key = "embeddinggemma:300m"
        def embed(self,text):
            embedded.append(text)
            return [1.0]+[0.0]*767
    reviewer.on_completed.service.embedder_factory = lambda *args:Embedder()
    def evaluate(**kwargs):
        calls.append(kwargs)
        data = json.loads(kwargs["input_text"])
        if kwargs["agent_name"]=="Vault Decisions Reconciliation":
            result = data["analysis"]
            if data["candidates"]:
                candidate = data["candidates"][0]
                behavior = json.loads(candidate["description"])
                proposal = result["proposals"][0]
                proposal.update(disposition="add_example",target_definition_id=candidate["definition_id"],
                    description=behavior["description"],conditions=behavior["conditions"]["all"],
                    required_slots=behavior["required_slots"],capability_ids=behavior["capabilities"],
                    exclusions=behavior["exclusions"])
            return dict(result,rationale="Same contact-search behavior; retain ID and add new evidence examples")
        assert data["coverage"]=="complete"
        point, = data["observations"]
        final,result,answer = point["final_source_id"],point["result_source_id"],point["answer_source_id"]
        unknown = dict(judgment="unknown",evidence_source_ids=[],explanation="No user feedback")
        correct = dict(judgment="correct",evidence_source_ids=[final,result],explanation="Requested lookup returned captured result")
        return dict(contract_version=3,assessments=[dict(point_id=point["point_id"],
            request_resolution=dict(judgment="resolved",evidence_source_ids=[final,result,answer],explanation="Answer reflects result"),
            usefulness=dict(judgment="necessary",evidence_source_ids=[final,result],explanation="Lookup needed for contacts"),
            tool_selection=correct,context_selection=dict(judgment="not_required",evidence_source_ids=[final],explanation="Explicit lookup"),
            result_quality=correct,user_satisfaction=unknown,tool_satisfaction=unknown,
            context_satisfaction=unknown,result_satisfaction=unknown,failure_stage="none")],
            proposals=[dict(disposition="create",target_definition_id=None,
                description="Locate matching contacts" if data["existing_decisions"] else "Search authorized contacts",
                conditions=["User requests contact lookup"],required_slots=["query"],exclusions=["No modifications"],
                capability_ids=[point["capability_id"]],point_ids=[point["point_id"]],
                source_ids=[final,result,answer],examples=["Find a contact"] )])
    reviewer.executor = evaluate
    async def runner(**kwargs):
        kwargs["model_response_sink"](NS(response_id="r1",output=[NS(type="function_call",id="i",
            call_id="call",name="contacts_search",arguments='{"query":"test"}')]))
        tool = next(t for t in kwargs["function_tools"] if t.name=="contacts_search")
        await tool.on_invoke_tool(NS(tool_call_id="call"),'{"query":"test"}')
        kwargs["model_response_sink"](NS(response_id="r2",output=[NS(type="message",id="a",
            role="assistant",content=[NS(type="output_text",text="No matching contacts")])]))
        return "No matching contacts"
    runtime.runner = runner
    turn = submit(m,conversation)
    assert wait(m,conversation,turn)["state"]=="completed"
    ended = runtime.end_session(m.principal,conversation,1)
    deadline = monotonic()+10
    rows = []
    while monotonic()<deadline:
        with psycopg.connect(m.url) as connection:
            rows = connection.execute("SELECT example_kind,vector_dims(embedding) FROM vault_private.vault_decision_examples").fetchall()
        if rows and all(r[1]==768 for r in rows):
            break
        Event().wait(.02)
    assert sorted(rows)==[("observed",768),("synthetic",768)]
    assert len(calls)==2 and len(embedded)==2
    snapshot = reviewer.source.load_segment(m.principal,conversation,ended["segmentId"])
    retry = reviewer.finalize_source(principal=m.principal,session_id=conversation,snapshot=snapshot)
    assert retry["alreadyCompleted"] and retry["learning"]["state"]=="generation_active_read_only"
    assert len(calls)==2 and len(embedded)==2
    from app.vault_runtime.decision_routing.example_index import ActiveDecisionQueries
    from app.vault_runtime.memory_search.postgres import QueryOptions
    activator = reviewer.on_completed.activator
    queries = ActiveDecisionQueries(activator=activator,
        options=QueryOptions(timeout_ms=1500,ef_search=100,max_scan_tuples=20000))
    candidates = queries.retrieve(m.principal,vector=Embedder().embed("Find a contact"),
        example_limit=20,decision_limit=5)
    assert len(candidates.choices)==1
    assert candidates.generation_id==retry["learning"]["generation_id"]
    live = runtime.preparation
    assert live.maintenance.ready.wait(10)
    runtime.memories._embedder_factory = lambda *_:Embedder()
    selections = []
    class Transport:
        def __init__(self,**kwargs):
            pass
        def evaluate(self,payload,**kwargs):
            selections.append(payload)
            choices = payload["questions"][0]["choices"]
            chosen = next(c["value"] for c in choices if "Search authorized contacts" in c["description"])
            return {"answers":[{"type":"choice","name":"workflow","choice":chosen,
                "confidence":.9,"probabilities":[{"value":c["value"],
                    "probability":1. if c["value"]==chosen else 0.} for c in choices]}]}
    live.transport_factory = Transport
    path = f"/conversations/{conversation}/preparation"
    assert m.post(path,dict(utteranceId="learned",revision=1,text="Find my contacts",composing=False),m.headers).status_code==202
    deadline = monotonic()+10
    preview = None
    while monotonic()<deadline:
        preview = m.app.handle(method="GET",target=path+"?utteranceId=learned&revision=1",headers=m.headers).payload
        if preview["state"]=="ready":
            break
        Event().wait(.03)
    assert preview["state"]=="ready",preview
    assert preview["tools"][0]["kind"]=="learned_rule"
    assert selections and "required_slots" in selections[0]["questions"][0]["choices"][0]["description"]
    second = submit(m,conversation,key="learned-second",version=1)
    assert wait(m,conversation,second)["state"]=="completed"
    final_context = next(e["payload"] for e in runtime.store.events(m.principal,conversation,second) if e["kind"]=="context")
    assert final_context["finalPreparation"]["memoryReused"] is True
    assert final_context["finalPreparation"]["toolProposals"]
    second_end = runtime.end_session(m.principal,conversation,2)
    second_snapshot = reviewer.source.load_segment(m.principal,conversation,second_end["segmentId"])
    assert len(second_snapshot.existing_decisions)==1
    deadline = monotonic()+10
    while monotonic()<deadline:
        active = activator.current(m.principal)
        if active.generation_id!=candidates.generation_id:
            break
        Event().wait(.04)
    assert active.generation_id and active.generation_id!=candidates.generation_id
    with psycopg.connect(m.url) as connection:
        assert connection.execute("SELECT version FROM vault_private.vault_decision_definitions WHERE generation_id=%s",
            (active.generation_id,)).fetchall()==[(2,)]
        with connection.cursor() as cursor:
            assert reviewer.source.current(cursor,m.principal,snapshot) is True
    assert len(calls)==4
    from tests.integration.test_mounted_chat_memory_learning_postgres import finish_workers
    finish_workers(runtime)
    # Rebuild the full retained catalog through the mounted owner route. Failure
    # after one successful prefix must roll back the entire derived replacement.
    previous=activator.current(m.principal)
    original_gate=activator.qualify_rule
    def fail_second(cursor,principal,rule):
        if rule.version==2:
            raise RuntimeError('Injected rebuild failure after first compiled review')
        return original_gate(cursor,principal,rule)
    activator.qualify_rule=fail_second
    args=dict(expectedEpoch=previous.epoch,requestKey='rebuild-contact-catalog')
    failed=m.post('/conversations/decisions/rebuild',args,m.headers)
    assert failed.status_code==503
    assert activator.current(m.principal)==previous
    activator.qualify_rule=original_gate
    rebuilt=m.post('/conversations/decisions/rebuild',args,m.headers)
    assert rebuilt.status_code==200,rebuilt.payload
    assert rebuilt.payload['reviewCount']==2 and rebuilt.payload['unqualifiedReviewIds']==[]
    assert rebuilt.payload['generationId']!=previous.generation_id
    assert len(calls)==4  # No repeated successful analysis or reconciliation.
    repeated=m.post('/conversations/decisions/rebuild',args,m.headers)
    assert repeated.status_code==200 and repeated.payload['alreadyCompleted']
    assert repeated.payload['generationId']==rebuilt.payload['generationId']
    with psycopg.connect(m.url) as connection:
        assert connection.execute('SELECT count(*) FROM vault_private.vault_decision_reviews').fetchone()[0]==2
        assert connection.execute("SELECT count(*) FROM vault_private.vault_decision_definitions WHERE status='active'").fetchone()[0]==1
        assert connection.execute('SELECT version FROM vault_private.vault_decision_definitions WHERE generation_id=%s',
            (rebuilt.payload['generationId'],)).fetchall()==[(2,)]
        assert connection.execute('SELECT count(*) FROM vault_private.vault_conversation_turns').fetchone()[0]==2
    assert queries.retrieve(m.principal,vector=[1.0]+[0.0]*767,example_limit=20,decision_limit=5).choices
    # New draft in the continued segment is invalidated immediately by revocation.
    assert m.post(path,dict(utteranceId="after",revision=1,text="Find my contacts",composing=False),m.headers).status_code==202
    runtime.authority.revoke_grant(actor_user_id=m.principal.user_id,
        workspace_id=m.principal.workspace_id,user_id=m.principal.user_id,tool_name="contacts_search")
    assert not queries.retrieve(m.principal,vector=[1.0]+[0.0]*767,
        example_limit=20,decision_limit=5).choices
    revoked_pointer=activator.current(m.principal)
    revoked_rebuild=m.post('/conversations/decisions/rebuild',
        dict(expectedEpoch=revoked_pointer.epoch,requestKey='rebuild-after-revocation'),m.headers)
    assert revoked_rebuild.status_code==200,revoked_rebuild.payload
    assert revoked_rebuild.payload['generationId'] is None
    assert len(calls)==4
    invalid = m.app.handle(method="GET",target=path+"?utteranceId=after&revision=1",headers=m.headers).payload
    assert invalid["tools"]==[]
    assert m.post(path,dict(utteranceId="after",revision=2,text="",composing=False),m.headers).status_code==202
    assert m.app.handle(method="GET",target=path+"?utteranceId=after&revision=1",headers=m.headers).payload["state"]=="stale"
    with psycopg.connect(m.url) as connection:
        connection.execute("DELETE FROM vault_private.vault_decision_reviews WHERE review_id=%s",
            (retry["learning"]["review_id"],))
    assert activator.current(m.principal).generation_id is None


def test_historical_qualification_pages_original_chat_and_unbridged_voice_without_side_effects(mounted):
    m=mounted
    runtime=m.app._conversation_runtime
    runtime.memory_learning=None
    conversation=create(m)
    async def runner(**kwargs):
        kwargs['model_response_sink'](NS(response_id='audit-answer',output=[NS(type='message',id='audit-item',role='assistant',
            content=[NS(type='output_text',text='Private historical answer')])]))
        return 'Private historical answer'
    runtime.runner=runner
    turn=submit(m,conversation)
    assert wait(m,conversation,turn)['state']=='completed'
    runtime.store.end_session(m.principal,conversation,1,request_review=False)
    voice=m.session('Private historical spoken request')
    m.app._voice_sessions.close_session(user_id=m.principal.user_id,workspace_id=m.principal.workspace_id,
        local_session_id=m.principal.session_id,voice_session_id=voice,transcript_capture_failures=0)
    def counts():
        with psycopg.connect(m.url) as connection:
            return tuple(connection.execute('SELECT count(*) FROM vault_private.'+table).fetchone()[0] for table in
                ('vault_conversations','vault_conversation_turns','vault_decision_reviews','vault_decision_generations',
                 'vault_memory_records','vault_transcript_entries'))
    before=counts()
    page=m.app.handle(method='GET',target='/conversations/decisions/qualification?limit=1',headers=m.headers)
    assert page.status_code==200,page.payload
    assert page.payload['readOnly'] and page.payload['nextAfter']
    second=m.app.handle(method='GET',target='/conversations/decisions/qualification?limit=1&after='+page.payload['nextAfter'],headers=m.headers)
    assert second.status_code==200 and second.payload['nextAfter'] is None
    items=page.payload['items']+second.payload['items']
    assert {i['channel'] for i in items}=={'voice','chat'}
    assert all(i['classification']=='transcript_only_tentative' and not i['publicationEligible'] for i in items)
    assert all(i['capturedBindings'] for i in items)
    assert 'Private historical' not in json.dumps(items)
    assert before==counts() and not m.calls
    denied=m.app.handle(method='GET',target='/conversations/decisions/qualification',headers={})
    assert denied.status_code==403
    assert m.app.handle(method='GET',target='/conversations/decisions/qualification?limit=11',headers=m.headers).status_code==400
