from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Event

import psycopg
import pytest

from app.vault_runtime.memory.suppression import MemorySuppressedError
from tests.integration.test_conversation_identity_postgres import require_test_database
from tests.integration.test_memory_postgres import memory_context, _candidate, _entry


@pytest.fixture(autouse=True)
def isolated_only():
    import os
    value = os.getenv("VAULT_TEST_DATABASE_URL")
    if value:
        require_test_database(value)


def remember(memories, principal, *, content="Prefers tea", key="drink", entry=None, visibility="private"):
    if entry is None:
        entry = _entry(memories,principal,session=key,index=0,text="Remember tea")
    return memories.reconcile_memory(user_id=principal.user_id,workspace_id=principal.workspace_id,
        voice_session_id=key,candidate=replace(_candidate(content=content,visibility=visibility),memory_key=key),
        evidence=((entry.entry_id,"user_statement","user_asserted",entry.text_content),))


def forget(memories,principal,memory):
    return memories.delete_memory(user_id=principal.user_id,workspace_id=principal.workspace_id,memory_id=memory.memory_id)


def test_retained_history_normalized_replay_renamed_key_and_old_source(memory_context):
    url, _, owner, _, memories = memory_context
    principal = owner.principal
    entry = _entry(memories,principal,session="old",index=0,text="Remember tea")
    record = remember(memories,principal,entry=entry)
    assert forget(memories,principal,record)
    assert memories.transcript_entries(user_id=principal.user_id,workspace_id=principal.workspace_id,voice_session_id="old")
    for content,key in (("  PREFERS   TEA ","renamed"),("Likes tea best","drink")):
        with pytest.raises(MemorySuppressedError):
            remember(memories,principal,content=content,key=key,entry=entry)
    new_entry = _entry(memories,principal,session="new",index=0,text="I now prefer coffee")
    assert remember(memories,principal,content="Prefers coffee",entry=new_entry).content_text == "Prefers coffee"
    memories.ensure_schema()
    with psycopg.connect(url) as connection:
        row = connection.execute("SELECT content_digest,source_entry_ids FROM vault_private.vault_memory_suppressions").fetchone()
        assert len(row[0]) == 64 and row[1] == [entry.entry_id]


def test_private_suppression_does_not_cross_users_or_workspaces(memory_context):
    _, _, owner, second, memories = memory_context
    record = remember(memories,owner.principal)
    forget(memories,owner.principal,record)
    assert remember(memories,second.principal).user_id == second.principal.user_id


def test_chat_original_source_paraphrase_is_suppressed_without_transcript_copy(memory_context):
    from app.vault_runtime.memory.analysis_spans import source_reference
    url, _, owner, _, memories = memory_context
    principal=owner.principal
    def save(content,source):
        text='I prefer tea'
        return memories.reconcile_memory(user_id=principal.user_id,workspace_id=principal.workspace_id,
            voice_session_id='chat-segment',candidate=_candidate(content=content),
            evidence=((None,'user_statement','user_asserted',text),),
            evidence_source_refs=(source_reference(source,'user',text),))
    record=save('Prefers tea','chat-user:original')
    forget(memories,principal,record)
    with pytest.raises(MemorySuppressedError):
        save('Likes tea best','chat-user:original')
    assert save('Prefers coffee now','chat-user:new').content_text=='Prefers coffee now'
    with psycopg.connect(url) as connection:
        ids=connection.execute('SELECT source_entry_ids FROM vault_private.vault_memory_suppressions').fetchone()[0]
        assert ids==['source-ref:chat-user:original']


def test_workspace_suppression_applies_to_current_members(memory_context):
    _, identity, owner, second, memories = memory_context
    identity.add_member(principal=owner.principal,workspace_id=owner.principal.workspace_id,username="second")
    identity.switch_workspace(principal=second.principal,workspace_id=owner.principal.workspace_id)
    member = identity.authenticate(session_token=second.session_token)
    record = remember(memories,owner.principal,visibility="workspace")
    forget(memories,owner.principal,record)
    with pytest.raises(MemorySuppressedError):
        remember(memories,member,key="different")


def test_forget_fences_reconcile_that_changes_key(memory_context):
    url, _, owner, _, memories = memory_context
    principal = owner.principal
    record = remember(memories,principal)
    # Hold the same production deletion fence, then commit deletion before a
    # renamed-key reconciliation can inspect the suppression relation.
    with psycopg.connect(url) as lock:
        lock.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,81008))",(principal.workspace_id,))
        with ThreadPoolExecutor(max_workers=1) as pool:
            started = Event()
            def replay():
                started.set()
                return remember(memories,principal,key="renamed")
            future = pool.submit(replay)
            assert started.wait(2)
            from app.vault_runtime.memory.suppression import record_suppression
            with lock.cursor() as cursor:
                record_suppression(cursor,record)
                cursor.execute("DELETE FROM vault_private.vault_memory_records WHERE memory_id=%s",(record.memory_id,))
            lock.commit()
            with pytest.raises(MemorySuppressedError):
                future.result(timeout=5)


def test_explicit_new_remember_event_is_required_for_same_fact_reintroduction(memory_context):
    _, _, owner, _, memories = memory_context
    principal = owner.principal
    record = remember(memories,principal)
    forget(memories,principal,record)
    ordinary = _entry(memories,principal,session="new-user",index=0,text="I prefer tea")
    with pytest.raises(MemorySuppressedError):
        remember(memories,principal,entry=ordinary)
    explicit = memories.append_transcript_next(user_id=principal.user_id,workspace_id=principal.workspace_id,
        voice_session_id="new-user",role="user",event_type="memory.intent.remember",text_content="Remember I prefer tea")
    restored=remember(memories,principal,entry=explicit)
    assert restored.content_text == "Prefers tea"
    forget(memories,principal,restored)
    # A second forget of the SAME digest must renew the timestamp: old consent
    # cannot restore the fact again through an upserted suppression row.
    with pytest.raises(MemorySuppressedError):
        remember(memories,principal,entry=explicit)


def test_pipeline_skips_suppressed_fact_and_completes_other_candidates(memory_context):
    from app.vault_runtime.memory.pipeline import MemoryPipeline
    _, _, owner, _, memories = memory_context
    principal = owner.principal
    record = reviewed_original(memories,principal)
    forget(memories,principal,record)
    _entry(memories,principal,session="replay",index=0,text="Historical tea preference; new coffee fact")
    reviewer=SemanticReviewer([_candidate(content="Prefers tea"),
        replace(_candidate(content="Has coffee maker"),memory_key="device")])
    result = MemoryPipeline(repository=memories,reviewer=reviewer).finalize(user_id=principal.user_id,
        workspace_id=principal.workspace_id,voice_session_id="replay")
    assert result.memory_count == 1


def test_later_explicit_chat_remember_uses_original_turn_without_voice_copy(memory_context):
    from app.vault_runtime.conversation.repository import ConversationRepository
    from app.vault_runtime.memory.analysis_spans import source_reference
    url,_,owner,_,memories=memory_context
    principal=owner.principal
    record=remember(memories,principal)
    forget(memories,principal,record)
    conversations=ConversationRepository(database_url=url)
    conversations.ensure_schema()
    conversation=conversations.create(principal,'explicit-remember')
    turn=conversations.submit_text(principal,conversation.conversation_id,'remember','Remember I prefer tea',0)
    with psycopg.connect(url) as connection:
        connection.execute("UPDATE vault_private.vault_conversation_turns SET state='completed' WHERE turn_id=%s",(turn.turn_id,))
    def save():
        return memories.reconcile_memory(user_id=principal.user_id,workspace_id=principal.workspace_id,
            voice_session_id=turn.segment_id,candidate=_candidate(content='Prefers tea'),
            evidence=((None,'explicit_memory_intent','user_asserted',turn.input_text),),
            evidence_source_refs=(source_reference('chat-final:'+turn.turn_id,'user',turn.input_text),))
    with pytest.raises(MemorySuppressedError):
        save()
    with psycopg.connect(url) as connection:
        connection.execute('UPDATE vault_private.vault_conversation_turns SET explicit_remember=true WHERE turn_id=%s',(turn.turn_id,))
    assert save().content_text=='Prefers tea'
    with psycopg.connect(url) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_transcript_entries WHERE event_type='memory.intent.remember'").fetchone()[0]==0


class SemanticReviewer:
    def __init__(self, candidates, *, judgment=None, hook=None):
        self.candidates=candidates
        self.judgment=judgment
        self.hook=hook
        self.comparisons=[]
    def review(self, _):
        from app.vault_runtime.memory.contracts import MemoryReview,ReviewedMemoryCandidate
        return MemoryReview('Scoped factual review',tuple(ReviewedMemoryCandidate(c,(0,)) for c in self.candidates),'synthetic')
    def review_structured(self, **kwargs):
        import json
        payload=json.loads(kwargs['input_text'])
        self.comparisons.append(payload)
        if self.hook: self.hook()
        pairs=[]
        for candidate in payload['candidates']:
            for forgotten in payload['forgotten']:
                same=candidate['content'] in {'Tea is my favorite drink','Prefers tea and owns a kettle'}
                pairs.append(dict(candidate_index=candidate['index'],forgotten_index=forgotten['index'],
                    judgment=self.judgment or ('same_fact' if same else 'different_fact')))
        return dict(comparisons=pairs),'synthetic'


def reviewed_original(memories,principal,*,content='Prefers tea',session='original',visibility='private'):
    from app.vault_runtime.memory.pipeline import MemoryPipeline
    _entry(memories,principal,session=session,index=0,text='User said: '+content)
    reviewer=SemanticReviewer([_candidate(content=content,visibility=visibility)])
    MemoryPipeline(repository=memories,reviewer=reviewer).finalize(user_id=principal.user_id,
        workspace_id=principal.workspace_id,voice_session_id=session)
    return memories.profile_memories(user_id=principal.user_id,workspace_id=principal.workspace_id)[0]


def test_semantic_replay_changed_identity_new_source_and_unrelated_fact(memory_context):
    from app.vault_runtime.memory.pipeline import MemoryPipeline
    url,_,owner,_,memories=memory_context
    p=owner.principal
    original=reviewed_original(memories,p)
    forget(memories,p,original)
    memories.require_semantic_suppression=True
    _entry(memories,p,session='fresh',index=0,text='Tea is my favorite drink. I own a coffee maker.')
    reviewer=SemanticReviewer([
        replace(_candidate(content='Tea is my favorite drink'),subject_id='renamed-subject',domain='identity',
            memory_type='fact',memory_key='new-identity'),
        replace(_candidate(content='Has a coffee maker'),memory_key='device',domain='device'),
        replace(_candidate(content='Prefers tea and owns a kettle'),memory_key='combined')])
    result=MemoryPipeline(repository=memories,reviewer=reviewer).finalize(user_id=p.user_id,
        workspace_id=p.workspace_id,voice_session_id='fresh')
    assert result.memory_count==1
    assert len(reviewer.comparisons)==1
    assert reviewer.comparisons[0]['forgotten']==[dict(index=0,content='Prefers tea')]
    stored=memories.profile_memories(user_id=p.user_id,workspace_id=p.workspace_id)
    assert [m.content_text for m in stored]==['Has a coffee maker']
    with psycopg.connect(url) as connection:
        assert connection.execute('SELECT count(*) FROM vault_private.vault_transcript_entries').fetchone()[0]==2
        serialized=str(connection.execute('SELECT row_to_json(s)::text FROM vault_private.vault_memory_suppressions s').fetchone()[0])
        assert 'Prefers tea' not in serialized and 'Tea is my favorite' not in serialized
    retry=MemoryPipeline(repository=memories,reviewer=reviewer).finalize(user_id=p.user_id,
        workspace_id=p.workspace_id,voice_session_id='fresh')
    assert retry.already_completed and len(reviewer.comparisons)==1


@pytest.mark.parametrize('judgment',['unknown','omitted','failure'])
def test_uncertain_or_invalid_semantic_review_never_publishes_a_prefix(memory_context,judgment):
    from app.vault_runtime.memory.pipeline import MemoryPipeline
    from app.vault_runtime.memory.suppression import MemorySuppressionReviewRequired
    _,_,owner,_,memories=memory_context
    p=owner.principal
    forget(memories,p,reviewed_original(memories,p))
    _entry(memories,p,session='uncertain',index=0,text='A coffee maker and a tea preference')
    reviewer=SemanticReviewer([replace(_candidate(content='Has a coffee maker'),memory_key='device'),
        replace(_candidate(content='Tea is my favorite drink'),memory_key='renamed')],judgment='unknown')
    if judgment!='unknown':
        def invalid(**kwargs):
            if judgment=='failure': raise RuntimeError('Synthetic provider unavailable')
            return dict(comparisons=[]),'synthetic'
        reviewer.review_structured=invalid
    with pytest.raises((MemorySuppressionReviewRequired,RuntimeError)):
        MemoryPipeline(repository=memories,reviewer=reviewer).finalize(user_id=p.user_id,
            workspace_id=p.workspace_id,voice_session_id='uncertain')
    assert memories.profile_memories(user_id=p.user_id,workspace_id=p.workspace_id)==()


def test_semantic_proof_cannot_cross_scope_or_survive_another_forget(memory_context):
    from app.vault_runtime.memory.suppression import MemorySuppressionReviewRequired
    _,_,owner,second,memories=memory_context
    p=owner.principal
    first=reviewed_original(memories,p)
    second_fact=remember(memories,p,content='Has a bicycle',key='bicycle')
    forget(memories,p,first)
    candidate=replace(_candidate(content='Tea is my favorite drink'),memory_key='renamed')
    entry=_entry(memories,p,session='new-proof',index=0,text=candidate.content_text)
    reviewer=SemanticReviewer([candidate])
    proof=memories.prepare_suppression_reviews(user_id=p.user_id,workspace_id=p.workspace_id,
        candidates=[candidate],reviewer=reviewer,model='synthetic')[0]
    with pytest.raises(MemorySuppressionReviewRequired):
        memories.reconcile_memory(user_id=second.principal.user_id,workspace_id=second.principal.workspace_id,
            voice_session_id='wrong-scope',candidate=candidate,evidence=((None,'user_statement','user_asserted','Tea'),),semantic_proof=proof)
    forget(memories,p,second_fact)
    with pytest.raises(MemorySuppressionReviewRequired):
        memories.reconcile_memory(user_id=p.user_id,workspace_id=p.workspace_id,voice_session_id='new-proof',
            candidate=candidate,evidence=((entry.entry_id,'user_statement','user_asserted',entry.text_content),),semantic_proof=proof)


def test_explicit_remember_bypasses_semantics_but_a_second_forget_revokes_it(memory_context):
    from app.vault_runtime.memory.pipeline import MemoryPipeline
    _,_,owner,_,memories=memory_context
    p=owner.principal
    forget(memories,p,reviewed_original(memories,p))
    memories.append_transcript_next(user_id=p.user_id,workspace_id=p.workspace_id,voice_session_id='restored',
        role='user',event_type='memory.intent.remember',text_content='Remember that tea is my favorite drink')
    reviewer=SemanticReviewer([replace(_candidate(content='Tea is my favorite drink'),memory_key='renamed')])
    result=MemoryPipeline(repository=memories,reviewer=reviewer).finalize(user_id=p.user_id,
        workspace_id=p.workspace_id,voice_session_id='restored')
    assert result.memory_count==1 and reviewer.comparisons==[]
    restored=memories.profile_memories(user_id=p.user_id,workspace_id=p.workspace_id)[0]
    forget(memories,p,restored)
    candidate=reviewer.candidates[0]
    entries=memories.transcript_entries(user_id=p.user_id,workspace_id=p.workspace_id,voice_session_id='restored')
    proof=memories.prepare_suppression_reviews(user_id=p.user_id,workspace_id=p.workspace_id,
        candidates=[candidate],reviewer=reviewer,model='synthetic',
        evidence=[((entries[0].entry_id,'user_statement','user_asserted',entries[0].text_content),)])[0]
    with pytest.raises(MemorySuppressedError):
        memories.reconcile_memory(user_id=p.user_id,workspace_id=p.workspace_id,voice_session_id='restored',
            candidate=candidate,evidence=((entries[0].entry_id,'user_statement','user_asserted',entries[0].text_content),),semantic_proof=proof)


def test_missing_retained_meaning_fails_closed_without_copying_forgotten_text(memory_context):
    from app.vault_runtime.memory.pipeline import MemoryPipeline
    from app.vault_runtime.memory.suppression import MemorySuppressionReviewRequired
    url,_,owner,_,memories=memory_context
    p=owner.principal
    forget(memories,p,reviewed_original(memories,p))
    with psycopg.connect(url) as connection:
        connection.execute("DELETE FROM vault_private.vault_memory_ingestions WHERE voice_session_id='original'")
    _entry(memories,p,session='missing',index=0,text='Tea is my favorite drink')
    reviewer=SemanticReviewer([replace(_candidate(content='Tea is my favorite drink'),memory_key='different')])
    with pytest.raises(MemorySuppressionReviewRequired,match='unavailable'):
        MemoryPipeline(repository=memories,reviewer=reviewer).finalize(user_id=p.user_id,
            workspace_id=p.workspace_id,voice_session_id='missing')
    assert memories.profile_memories(user_id=p.user_id,workspace_id=p.workspace_id)==()
    assert reviewer.comparisons==[]
    # Existing explicit user intent can restore it even when old review history
    # was removed. No forgotten plaintext needs to be added to the tombstone.
    memories.append_transcript_next(user_id=p.user_id,workspace_id=p.workspace_id,voice_session_id='allowed',
        role='user',event_type='memory.intent.remember',text_content='Remember tea is my favorite drink')
    restored=MemoryPipeline(repository=memories,reviewer=reviewer).finalize(user_id=p.user_id,
        workspace_id=p.workspace_id,voice_session_id='allowed')
    assert restored.memory_count==1 and reviewer.comparisons==[]


def test_concurrent_forget_during_semantic_review_rolls_back_and_retries_existing_review(memory_context):
    from app.vault_runtime.memory.pipeline import MemoryPipeline
    from app.vault_runtime.memory.suppression import MemorySuppressionReviewRequired
    url,_,owner,_,memories=memory_context
    p=owner.principal
    original=reviewed_original(memories,p)
    bicycle_entry=_entry(memories,p,session='bicycle',index=0,text='Has a bicycle')
    bicycle=remember(memories,p,content='Has a bicycle',key='bicycle',entry=bicycle_entry)
    forget(memories,p,original)
    _entry(memories,p,session='race',index=0,text='Tea is my favorite drink and I have a coffee maker')
    def concurrent_forget():
        forget(memories,p,bicycle)
    reviewer=SemanticReviewer([replace(_candidate(content='Has a coffee maker'),memory_key='device'),
        replace(_candidate(content='Tea is my favorite drink'),memory_key='new-name')],hook=concurrent_forget)
    pipeline=MemoryPipeline(repository=memories,reviewer=reviewer)
    with pytest.raises(MemorySuppressionReviewRequired,match='changed'):
        pipeline.finalize(user_id=p.user_id,workspace_id=p.workspace_id,voice_session_id='race')
    assert memories.profile_memories(user_id=p.user_id,workspace_id=p.workspace_id)==()
    reviewer.hook=None
    reviewer.review=lambda _: (_ for _ in ()).throw(AssertionError('Original factual analysis must not repeat'))
    retried=pipeline.finalize(user_id=p.user_id,workspace_id=p.workspace_id,voice_session_id='race')
    assert retried.memory_count==1
    assert len(reviewer.comparisons)==2
    assert {r['content'] for r in reviewer.comparisons[-1]['forgotten']}=={'Prefers tea','Has a bicycle'}
    with psycopg.connect(url) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_memory_ingestions WHERE voice_session_id='race'").fetchone()[0]==1


def test_confirmed_correction_uses_same_guard_and_rolls_back_consumed_action(memory_context):
    from app.vault_runtime.memory.service import MemoryService
    url,_,owner,_,memories=memory_context
    p=owner.principal
    forget(memories,p,reviewed_original(memories,p))
    current=remember(memories,p,content='Has a bicycle',key='vehicle')
    _entry(memories,p,session='correction',index=0,text='Change this memory')
    reviewer=SemanticReviewer([])
    reviewer.model_identity=lambda:('custom','synthetic')
    service=MemoryService(repository=memories,reviewer_factory=lambda *_:reviewer)
    action=memories.prepare_action(user_id=p.user_id,workspace_id=p.workspace_id,voice_session_id='correction',
        prepared_entry_index=0,action_kind='correct',memory_id=current.memory_id,proposed_content='Tea is my favorite drink')
    _entry(memories,p,session='correction',index=1,text='Yes, confirm that change')
    with pytest.raises(MemorySuppressedError):
        service.confirm_action(user_id=p.user_id,workspace_id=p.workspace_id,voice_session_id='correction',
            action_id=action,confirmation_entry_index=1)
    assert memories.memory(user_id=p.user_id,workspace_id=p.workspace_id,memory_id=current.memory_id).content_text=='Has a bicycle'
    with psycopg.connect(url) as connection:
        assert connection.execute('SELECT status FROM vault_private.vault_memory_pending_actions WHERE action_id=%s',(action,)).fetchone()[0]=='pending'
    distinct=memories.prepare_action(user_id=p.user_id,workspace_id=p.workspace_id,voice_session_id='correction',
        prepared_entry_index=1,action_kind='correct',memory_id=current.memory_id,proposed_content='Has a coffee maker')
    _entry(memories,p,session='correction',index=2,text='Yes, confirm the coffee maker')
    confirmed=service.confirm_action(user_id=p.user_id,workspace_id=p.workspace_id,voice_session_id='correction',
        action_id=distinct,confirmation_entry_index=2)
    assert confirmed.memory.content_text=='Has a coffee maker'
