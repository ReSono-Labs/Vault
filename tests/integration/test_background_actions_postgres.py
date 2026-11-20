"""Trusted decisions are serialized against current scope and exact prepared state."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import importlib
import importlib.util

import psycopg
import pytest

from tests.support.background_authority import standing_work
from app.vault_runtime.background_agent.coordination_contracts import ApprovalDecision, OwnerScope
from app.vault_runtime.background_agent.errors import BackgroundRunAuthorizationError,BackgroundRunConflictError


class FakeDomain:
    def __init__(self):
        self.version='v1'
        self.effects=[]
    def validate(self,scope,domain_ref,action_hash):
        if domain_ref!='existing-pending' or self.version!='v1':
            raise BackgroundRunConflictError('Prepared domain state changed')
    def execute(self,scope,domain_ref,operation_key):
        self.effects.append(operation_key)
        return {'receipt':'provider-receipt'}
    def reconcile(self,scope,domain_ref,operation_key):
        return {'state':'completed','receipt':'provider-receipt'} if operation_key in self.effects else {'state':'unknown'}


@pytest.fixture
def actions(context):
    assert importlib.util.find_spec('app.vault_runtime.background_agent.actions') is not None, 'Missing trusted action service'
    _m,_repo,_owner,scope,_authority,_workers=standing_work(context)
    domain=FakeDomain()
    cls=importlib.import_module('app.vault_runtime.background_agent.actions').BackgroundActions
    # Only fake/in-process domain effects are authorized by this fixture.
    service=cls(database_url=context[0],domains={'proof':domain},authorizer=lambda *_:True)
    prepared=service.prepare(scope,'proof',{'summary':'Reviewed exact change'},'v1','existing-pending')
    return service,scope,prepared,domain


def decision(context,prepared,choice='allow_once',identifier='decision'):
    principal=context[1]
    return ApprovalDecision(prepared.action_id,prepared.action_hash,choice,principal.user_id,principal.workspace_id,
                            'browser',principal.session_id,identifier)


def test_model_claims_are_not_decisions_and_approval_is_one_use(context,actions):
    service,scope,prepared,_domain=actions
    with pytest.raises(BackgroundRunAuthorizationError): service.claim(scope,prepared.action_id,prepared.action_hash)
    receipt=service.decide(context[1],decision(context,prepared))
    assert service.decide(context[1],decision(context,prepared))==receipt
    claimed=service.claim(scope,prepared.action_id,prepared.action_hash)
    assert claimed['domain_ref']=='existing-pending'
    with pytest.raises(BackgroundRunConflictError): service.claim(scope,prepared.action_id,prepared.action_hash)
    service.record_outcome(scope,prepared.action_id,{'state':'completed','receipt':'checked'})


@pytest.mark.parametrize('change',[
    "UPDATE vault_private.vault_background_actions SET expires_at=now()-interval '1 second'",
    "UPDATE vault_private.vault_background_work SET intent_version=intent_version+1",
    "UPDATE vault_private.vault_background_execution_grants SET status='revoked'",
])
def test_current_authority_and_exact_action_are_rechecked(context,actions,change):
    service,scope,prepared,_domain=actions
    service.decide(context[1],decision(context,prepared))
    with psycopg.connect(context[0]) as connection: connection.execute(change)
    with pytest.raises((BackgroundRunAuthorizationError,BackgroundRunConflictError)):
        service.claim(scope,prepared.action_id,prepared.action_hash)


def test_changed_resource_wrong_hash_and_foreign_owner_are_denied(context,actions):
    service,scope,prepared,domain=actions
    with pytest.raises(BackgroundRunAuthorizationError):
        service.decide(context[2],decision(context,prepared))
    with pytest.raises(BackgroundRunAuthorizationError):
        service.decide(context[1],replace(decision(context,prepared),action_hash='0'*64))
    service.decide(context[1],decision(context,prepared))
    domain.version='v2'
    with pytest.raises(BackgroundRunConflictError): service.claim(scope,prepared.action_id,prepared.action_hash)


def test_conflicting_decisions_have_one_winner_and_denial_cannot_retry(context,actions):
    service,scope,prepared,_domain=actions
    def choose(choice):
        try:
            service.decide(context[1],decision(context,prepared,choice,choice))
            return choice
        except BackgroundRunConflictError:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(choose,['allow_once','deny']))
    assert outcomes.count('conflict')==1
    if 'deny' in outcomes:
        with pytest.raises(BackgroundRunAuthorizationError): service.claim(scope,prepared.action_id,prepared.action_hash)
    with pytest.raises(BackgroundRunConflictError):
        service.decide(context[1],decision(context,prepared,'allow_once','new-decision'))


def test_worker_proposal_uses_the_same_trusted_decision_service(context,actions):
    from app.vault_runtime.background_agent.worker_repository import WorkerRepository
    from app.vault_runtime.background_agent.coordination_contracts import WorkerSpec
    service,_scope,_prepared,_domain=actions
    workers=WorkerRepository(database_url=context[0])
    principal=context[1]
    owner=OwnerScope(principal.user_id,principal.workspace_id)
    spec=WorkerSpec('research','Research','Check sources',(),{})
    proposal=workers.propose(owner,spec)
    assert workers.propose(owner,spec).action_id==proposal.action_id
    service.decide(principal,decision(context,proposal,'deny','deny-worker'))
    with pytest.raises(BackgroundRunConflictError):
        workers.propose(owner,spec)
    reopened=service.reopen(principal,proposal.action_id,channel='browser',channel_generation=principal.session_id)
    assert workers.propose(owner,spec).action_id==reopened.action_id
    service.decide(principal,decision(context,reopened,identifier='allow-worker'))
    worker=workers.create_from_approval(decision(context,reopened,identifier='allow-worker'))
    assert workers.get(owner,worker).role_key=='research'
    with pytest.raises(BackgroundRunConflictError):
        workers.propose(owner,spec)


def test_approval_channel_revocation_prevents_claim(context,actions):
    service,scope,prepared,_domain=actions
    service.decide(context[1],decision(context,prepared))
    with psycopg.connect(context[0]) as connection:
        connection.execute("UPDATE vault_private.local_sessions SET status='revoked' WHERE session_id=%s",(context[1].session_id,))
    with pytest.raises(BackgroundRunAuthorizationError):
        service.claim(scope,prepared.action_id,prepared.action_hash)


@pytest.mark.parametrize('kind',['tasks','calendar','mail','contacts','commands'])
def test_lost_effect_receipt_reconciles_without_resending(context,actions,kind):
    service,scope,_prepared,domain=actions
    service._domains[kind]=domain
    prepared=service.prepare(scope,kind,{'summary':'Exact scoped change'},'v1','existing-pending')
    service.decide(context[1],decision(context,prepared))
    original=service.record_outcome
    def lost(*_args,**_kwargs):
        raise RuntimeError('simulated crash before receipt save')
    service.record_outcome=lost
    with pytest.raises(RuntimeError):service.execute(scope,prepared.action_id,prepared.action_hash)
    service.record_outcome=original
    assert service.execute(scope,prepared.action_id,prepared.action_hash)=={'state':'unknown'}
    assert len(domain.effects)==1
    assert service.reconcile(scope,prepared.action_id)['state']=='completed'
    assert len(domain.effects)==1


def test_absent_provider_evidence_stays_unknown(context,actions):
    service,scope,prepared,domain=actions
    service.decide(context[1],decision(context,prepared))
    service.claim(scope,prepared.action_id,prepared.action_hash)
    assert service.reconcile(scope,prepared.action_id)=={'state':'unknown'}
    assert service.execute(scope,prepared.action_id,prepared.action_hash)=={'state':'unknown'}
    assert domain.effects==[]


def test_tasks_adapter_uses_existing_task_pending_record(context,actions):
    from app.vault_runtime.tasks.repository import TaskRepository
    module=importlib.import_module('app.vault_runtime.background_agent.action_domains')
    service,scope,_prepared,_domain=actions
    repository=TaskRepository(database_url=context[0])
    repository.ensure_schema()
    adapter=module.TaskActionDomain(repository=repository)
    reference=adapter.prepare(scope,{'operation':'add','payload':{'text':'Approved task'}})
    version=adapter.version(scope,reference)
    service._domains['tasks']=adapter
    prepared=service.prepare(scope,'tasks',{'summary':'Add Approved task'},version,reference)
    service.decide(context[1],decision(context,prepared))
    assert service.execute(scope,prepared.action_id,prepared.action_hash)['state']=='completed'
    assert service.execute(scope,prepared.action_id,prepared.action_hash)['state']=='completed'
    tasks=repository.list(user_id=scope.user_id,workspace_id=scope.workspace_id)
    assert [task.task_text for task in tasks]==['Approved task']
    with psycopg.connect(context[0]) as connection:
        assert connection.execute('SELECT count(*) FROM vault_private.vault_task_pending_actions').fetchone()[0]==1


def test_missing_current_tool_authorizer_fails_closed(context,actions):
    service,scope,_prepared,domain=actions
    cls=type(service)
    unconfigured=cls(database_url=context[0],domains={'proof':domain})
    with pytest.raises(BackgroundRunAuthorizationError):
        unconfigured.prepare(scope,'proof',{'summary':'Change'},'v1','existing-pending')
    assert domain.effects==[]


def test_contacts_adapter_executes_existing_broker_after_trusted_decision(context,actions):
    from app.vault_runtime.personal_data import PersonalDataRepository
    from app.vault_runtime.tools.definitions import ToolInvocationContext
    from app.vault_runtime.system_agents.inventory import AgentKind
    module=importlib.import_module('app.vault_runtime.background_agent.action_domains')
    service,scope,_prepared,_domain=actions
    records=PersonalDataRepository(database_url=context[0])
    records.ensure_schema()
    def invocation(current,name):
        return ToolInvocationContext(agent=AgentKind.BACKGROUND,user_id=current.user_id,workspace_id=current.workspace_id,
            tool_call_id='contact-prepare',local_session_id=None,background_scope=current)
    adapter=module.contacts_domain(records=records,context_factory=invocation)
    reference=adapter.prepare(scope,{'actionType':'create','firstName':'Approved contact'})
    service._domains['contacts']=adapter
    prepared=service.prepare(scope,'contacts',{'summary':'Create Approved contact'},adapter.version(scope,reference),reference)
    service.decide(context[1],decision(context,prepared))
    result=service.execute(scope,prepared.action_id,prepared.action_hash)
    assert result['state']=='completed'
    assert records.list_private_records(account_id=scope.user_id,workspace_id=scope.workspace_id,source_table='contacts_entries',limit=10)


@pytest.mark.parametrize('mutate_before_effect',[False,True])
def test_calendar_adapter_uses_existing_pending_record_and_fake_provider(context,actions,mutate_before_effect):
    from app.vault_runtime.personal_data import PersonalDataRepository
    from app.vault_runtime.tools.definitions import ToolInvocationContext
    from app.vault_runtime.system_agents.inventory import AgentKind
    module=importlib.import_module('app.vault_runtime.background_agent.action_domains')
    service,scope,_prepared,_domain=actions
    records=PersonalDataRepository(database_url=context[0])
    records.ensure_schema()
    effects=[]
    class Calendar:
        def create_event(self,principal,linked,arguments):
            effects.append((principal.user_id,linked,arguments))
            return {'id':'fake-event'}
    def invocation(current,name):
        return ToolInvocationContext(agent=AgentKind.BACKGROUND,user_id=current.user_id,workspace_id=current.workspace_id,
            tool_call_id='calendar-prepare',local_session_id=None,background_scope=current)
    adapter=module.calendar_domain(records=records,runtime=Calendar(),context_factory=invocation)
    reference=adapter.prepare(scope,{'linkedAccountId':'calendar','title':'Approved event','startsAt':'2026-11-18T10:00:00Z'})
    service._domains['calendar']=adapter
    prepared=service.prepare(scope,'calendar',{'summary':'Create Approved event'},adapter.version(scope,reference),reference)
    service.decide(context[1],decision(context,prepared))
    if mutate_before_effect:
        original=adapter._execute
        def changed(current,ref,key):
            with psycopg.connect(context[0]) as connection:
                connection.execute("UPDATE vault_private.vault_personal_records SET source_payload=jsonb_set(source_payload,'{arguments,title}',to_jsonb('Changed after claim'::text)) WHERE source_id=%s",(ref,))
            return original(current,ref,key)
        adapter._execute=changed
    outcome=service.execute(scope,prepared.action_id,prepared.action_hash)
    # A draft changed after the claim is caught before the provider call: a confirmed no-effect failure.
    assert outcome['state']==('failed' if mutate_before_effect else 'completed')
    if mutate_before_effect:
        assert outcome=={'state':'failed','effect':'none','code':'draft_changed'}
    assert len(effects)==(0 if mutate_before_effect else 1)


def test_mail_adapter_reuses_canonical_send_request_and_sends_once(context,actions,tmp_path):
    from app.vault_runtime.email.runtime import LocalEmailRuntime
    from app.vault_runtime.email.schema import ensure_email_schema
    from app.vault_runtime.extensions.secrets import LocalMasterKey
    from tests.support.local_email_runtime import _credentials
    from app.vault_runtime.tools.definitions import ToolInvocationContext
    from app.vault_runtime.system_agents.inventory import AgentKind
    module=importlib.import_module('app.vault_runtime.background_agent.action_domains')
    service,scope,_prepared,_domain=actions
    with psycopg.connect(context[0]) as connection:
        with connection.cursor() as cursor:ensure_email_schema(cursor)
    sent=[]
    class Provider:
        def send_message(self,**kwargs):sent.append(kwargs['subject'])
    runtime=LocalEmailRuntime(database_url=context[0],master_key=LocalMasterKey(tmp_path/'mail.key'),provider=Provider())
    with runtime.service(context[1]) as mail:
        mailbox=mail.connect_mailbox(account_id=scope.user_id,workspace_id=scope.workspace_id,mailbox_role='normal_email',
            credentials_payload=_credentials('owner@example.com','fixture'),display_name='Fixture',validate_connection=False)
    def invocation(current,name):
        return ToolInvocationContext(agent=AgentKind.BACKGROUND,user_id=current.user_id,workspace_id=current.workspace_id,
            tool_call_id='mail-prepare',local_session_id=None,background_scope=current)
    adapter=module.MailSendDomain(runtime=runtime,context_factory=invocation)
    reference=adapter.prepare(scope,{'mailboxAccountId':mailbox['mailboxAccountId'],'to':['recipient@example.com'],'subject':'Approved subject','body':'Reviewed body'})
    service._domains['mail']=adapter
    prepared=service.prepare(scope,'mail',{'summary':'Send Approved subject'},adapter.version(scope,reference),reference)
    service.decide(context[1],decision(context,prepared))
    assert service.execute(scope,prepared.action_id,prepared.action_hash)['state']=='completed'
    assert service.execute(scope,prepared.action_id,prepared.action_hash)['state']=='completed'
    assert sent==['Approved subject']
    with psycopg.connect(context[0]) as connection:
        assert connection.execute('SELECT count(*) FROM vault_private.vault_email_send_requests').fetchone()[0]==1


# --- Handoff review fixes (2026-11-17): re-prepare/reopen, no-effect failures, scoped lookups ---

def _state(context,action_id):
    with psycopg.connect(context[0]) as connection:
        return connection.execute('SELECT state,receipt_json FROM vault_private.vault_background_actions WHERE action_id=%s',
                                  (action_id,)).fetchone()


def test_identical_prepare_returns_the_open_action_but_never_revives_a_denial(context,actions):
    service,scope,prepared,_domain=actions
    assert service.prepare(scope,'proof',{'summary':'Reviewed exact change'},'v1','existing-pending').action_id==prepared.action_id
    service.decide(context[1],decision(context,prepared,'deny','denied'))
    with pytest.raises(BackgroundRunConflictError):
        service.prepare(scope,'proof',{'summary':'Reviewed exact change'},'v1','existing-pending')
    assert _state(context,prepared.action_id)[0]=='denied'


def test_identical_prepare_after_expiry_needs_an_owner_reopen(context,actions):
    service,scope,prepared,_domain=actions
    with psycopg.connect(context[0]) as connection:
        connection.execute("UPDATE vault_private.vault_background_actions SET expires_at=now()-interval '1 second' WHERE action_id=%s",(prepared.action_id,))
    with pytest.raises(BackgroundRunConflictError):
        service.prepare(scope,'proof',{'summary':'Reviewed exact change'},'v1','existing-pending')
    principal=context[1]
    reopened=service.reopen(principal,prepared.action_id,channel='browser',channel_generation=principal.session_id)
    assert reopened.action_id!=prepared.action_id and reopened.action_hash==prepared.action_hash
    assert reopened.expires_at>datetime.now(timezone.utc)
    # The reopened action is the one an identical prepare now returns, and it needs its own decision.
    assert service.prepare(scope,'proof',{'summary':'Reviewed exact change'},'v1','existing-pending').action_id==reopened.action_id
    with pytest.raises(BackgroundRunAuthorizationError): service.claim(scope,reopened.action_id,reopened.action_hash)
    service.decide(principal,decision(context,reopened,identifier='after-reopen'))
    assert service.claim(scope,reopened.action_id,reopened.action_hash)['state']=='executing'


def test_owner_reopen_of_a_denial_is_explicit_one_at_a_time_and_rechecks_the_draft(context,actions):
    service,scope,prepared,domain=actions
    principal=context[1]
    service.decide(principal,decision(context,prepared,'deny','denied'))
    with pytest.raises(BackgroundRunAuthorizationError):
        service.reopen(context[2],prepared.action_id,channel='browser',channel_generation=context[2].session_id)
    with pytest.raises(BackgroundRunAuthorizationError):
        service.reopen(principal,prepared.action_id,channel='voice',channel_generation=principal.session_id)
    domain.version='v2'
    with pytest.raises(BackgroundRunConflictError):
        service.reopen(principal,prepared.action_id,channel='browser',channel_generation=principal.session_id)
    domain.version='v1'
    def reopen():
        try:
            return service.reopen(principal,prepared.action_id,channel='browser',channel_generation=principal.session_id).action_id
        except BackgroundRunConflictError:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(lambda _:reopen(),range(2)))
    assert outcomes.count('conflict')==1
    assert _state(context,prepared.action_id)[0]=='denied', 'the denial itself is never revived'


def test_reopen_refuses_actions_that_ran_or_may_have_run(context,actions):
    service,scope,prepared,domain=actions
    principal=context[1]
    service.decide(principal,decision(context,prepared))
    assert service.execute(scope,prepared.action_id,prepared.action_hash)['state']=='completed'
    with pytest.raises(BackgroundRunConflictError):
        service.reopen(principal,prepared.action_id,channel='browser',channel_generation=principal.session_id)
    with pytest.raises(BackgroundRunConflictError):
        service.prepare(scope,'proof',{'summary':'Reviewed exact change'},'v1','existing-pending')
    assert len(domain.effects)==1


def test_reopen_after_changed_intent_is_refused(context,actions):
    service,scope,prepared,_domain=actions
    principal=context[1]
    service.decide(principal,decision(context,prepared,'deny','denied'))
    with psycopg.connect(context[0]) as connection:
        connection.execute('UPDATE vault_private.vault_background_work SET intent_version=intent_version+1')
    with pytest.raises((BackgroundRunAuthorizationError,BackgroundRunConflictError)):
        service.reopen(principal,prepared.action_id,channel='browser',channel_generation=principal.session_id)


def test_confirmed_no_effect_failure_is_failed_not_unknown_and_can_be_reopened(context,actions):
    from app.vault_runtime.background_agent.action_domains import NoEffectError
    service,scope,prepared,domain=actions
    principal=context[1]
    def refuse(*_args):
        raise NoEffectError('draft_changed')
    domain.execute=refuse
    service.decide(principal,decision(context,prepared))
    outcome=service.execute(scope,prepared.action_id,prepared.action_hash)
    assert outcome=={'state':'failed','effect':'none','code':'draft_changed'}
    assert _state(context,prepared.action_id)[0]=='failed'
    reopened=service.reopen(principal,prepared.action_id,channel='browser',channel_generation=principal.session_id)
    assert reopened.action_id!=prepared.action_id


def test_an_unclassified_execution_error_stays_unknown_and_cannot_be_reopened(context,actions):
    service,scope,prepared,domain=actions
    principal=context[1]
    def lost(*_args):
        raise ConnectionError('provider connection dropped')
    domain.execute=lost
    service.decide(principal,decision(context,prepared))
    assert service.execute(scope,prepared.action_id,prepared.action_hash)=={'state':'unknown'}
    with pytest.raises(BackgroundRunConflictError):
        service.reopen(principal,prepared.action_id,channel='browser',channel_generation=principal.session_id)


def test_task_changed_after_claim_fails_with_no_effect(context,actions):
    from app.vault_runtime.tasks.repository import TaskRepository
    from app.vault_runtime.background_agent.action_domains import TaskActionDomain
    service,scope,_prepared,_domain=actions
    tasks=TaskRepository(database_url=context[0])
    tasks.ensure_schema()
    principal=context[1]
    domain=TaskActionDomain(repository=tasks)
    service._domains['tasks']=domain
    added=domain.prepare(scope,{'operation':'add','payload':{'text':'Original'}})
    add=service.prepare(scope,'tasks',{'summary':'Add task'},domain.version(scope,added),added)
    service.decide(principal,decision(context,add,identifier='add'))
    task_id=service.execute(scope,add.action_id,add.action_hash)['result']['taskId']
    reference=domain.prepare(scope,{'operation':'edit','taskId':task_id,'payload':{'text':'Edited'}})
    prepared=service.prepare(scope,'tasks',{'summary':'Edit task'},domain.version(scope,reference),reference)
    service.decide(principal,decision(context,prepared))
    with psycopg.connect(context[0]) as connection:
        connection.execute("UPDATE vault_private.vault_tasks SET updated_at=now()+interval '1 second' WHERE task_id=%s",(task_id,))
    # validate() in claim would also catch this; bypass it to reach the effect transaction's own check.
    original=domain.validate
    domain.validate=lambda *_a:None
    try:
        outcome=service.execute(scope,prepared.action_id,prepared.action_hash)
    finally:
        domain.validate=original
    assert outcome['state']=='failed' and outcome['effect']=='none'
    with psycopg.connect(context[0]) as connection:
        text=connection.execute('SELECT task_text FROM vault_private.vault_tasks WHERE task_id=%s',(task_id,)).fetchone()[0]
    assert text=='Original'


def test_a_decision_id_reused_for_another_action_is_a_conflict_not_a_database_error(context,actions):
    service,scope,prepared,_domain=actions
    principal=context[1]
    service.decide(principal,decision(context,prepared,identifier='same-id'))
    other=service.prepare(scope,'proof',{'summary':'A different change'},'v1','existing-pending')
    with pytest.raises(BackgroundRunConflictError):
        service.decide(principal,decision(context,other,identifier='same-id'))
    assert _state(context,other.action_id)[0]=='pending'
    # The original decision is untouched and still replays idempotently.
    assert service.decide(principal,decision(context,prepared,identifier='same-id'))=='same-id'


def test_a_removed_task_with_a_lost_receipt_reconciles_as_completed(context,actions):
    from app.vault_runtime.tasks.repository import TaskRepository
    from app.vault_runtime.background_agent.action_domains import TaskActionDomain
    service,scope,_prepared,_domain=actions
    principal=context[1]
    tasks=TaskRepository(database_url=context[0])
    tasks.ensure_schema()
    domain=TaskActionDomain(repository=tasks)
    service._domains['tasks']=domain
    added=domain.prepare(scope,{'operation':'add','payload':{'text':'Remove me'}})
    add=service.prepare(scope,'tasks',{'summary':'Add task'},domain.version(scope,added),added)
    service.decide(principal,decision(context,add,identifier='add'))
    task_id=service.execute(scope,add.action_id,add.action_hash)['result']['taskId']
    reference=domain.prepare(scope,{'operation':'remove','taskId':task_id,'payload':{}})
    remove=service.prepare(scope,'tasks',{'summary':'Remove task'},domain.version(scope,reference),reference)
    service.decide(principal,decision(context,remove,identifier='remove'))
    original=service.record_outcome
    def lost(*_args,**_kwargs):
        raise RuntimeError('simulated crash before receipt save')
    service.record_outcome=lost
    with pytest.raises(RuntimeError):
        service.execute(scope,remove.action_id,remove.action_hash)
    service.record_outcome=original
    assert tasks.list(user_id=scope.user_id,workspace_id=scope.workspace_id,include_completed=True)==[]
    assert service.reconcile(scope,remove.action_id)['state']=='completed'
    assert service.execute(scope,remove.action_id,remove.action_hash)['state']=='completed'


def test_a_pending_task_change_still_needs_its_target(context,actions):
    from app.vault_runtime.tasks.repository import TaskRepository
    from app.vault_runtime.background_agent.action_domains import TaskActionDomain
    service,scope,_prepared,_domain=actions
    tasks=TaskRepository(database_url=context[0])
    tasks.ensure_schema()
    domain=TaskActionDomain(repository=tasks)
    service._domains['tasks']=domain
    added=domain.prepare(scope,{'operation':'add','payload':{'text':'Edit me'}})
    add=service.prepare(scope,'tasks',{'summary':'Add task'},domain.version(scope,added),added)
    service.decide(context[1],decision(context,add,identifier='add'))
    task_id=service.execute(scope,add.action_id,add.action_hash)['result']['taskId']
    reference=domain.prepare(scope,{'operation':'edit','taskId':task_id,'payload':{'text':'Edited'}})
    version=domain.version(scope,reference)
    with psycopg.connect(context[0]) as connection:
        connection.execute('DELETE FROM vault_private.vault_tasks WHERE task_id=%s',(task_id,))
    with pytest.raises((ValueError,BackgroundRunConflictError)):
        domain.validate(scope,reference,version)


@pytest.mark.parametrize('bypass_claim_check',[False,True])
def test_a_contact_changed_after_preparation_is_not_overwritten(context,actions,bypass_claim_check):
    from app.vault_runtime.personal_data import PersonalDataRepository
    from app.vault_runtime.tools.definitions import ToolInvocationContext
    from app.vault_runtime.system_agents.inventory import AgentKind
    module=importlib.import_module('app.vault_runtime.background_agent.action_domains')
    service,scope,_prepared,_domain=actions
    principal=context[1]
    records=PersonalDataRepository(database_url=context[0])
    records.ensure_schema()
    def invocation(current,name):
        return ToolInvocationContext(agent=AgentKind.BACKGROUND,user_id=current.user_id,workspace_id=current.workspace_id,
            tool_call_id=f'contact-{name}',local_session_id=None,background_scope=current)
    adapter=module.contacts_domain(records=records,context_factory=invocation)
    service._domains['contacts']=adapter
    created=adapter.prepare(scope,{'actionType':'create','firstName':'Ada','phoneNumber':'111'})
    first=service.prepare(scope,'contacts',{'summary':'Create Ada'},adapter.version(scope,created),created)
    service.decide(principal,decision(context,first,identifier='create'))
    assert service.execute(scope,first.action_id,first.action_hash)['state']=='completed'
    (entry,)=records.list_private_records(account_id=scope.user_id,workspace_id=scope.workspace_id,source_table='contacts_entries',limit=10)
    contact_id=entry['sourceId']
    update=adapter.prepare(scope,{'actionType':'update','contactId':contact_id,'notes':'Met at the conference'})
    prepared=service.prepare(scope,'contacts',{'summary':'Add a note to Ada'},adapter.version(scope,update),update)
    service.decide(principal,decision(context,prepared,identifier='update'))
    # The owner edits the contact themselves before the background change runs.
    with psycopg.connect(context[0]) as connection:
        connection.execute("""UPDATE vault_private.vault_personal_records
            SET source_payload=jsonb_set(source_payload,'{phone_number}',to_jsonb('222'::text))
            WHERE source_table='contacts_entries' AND source_id=%s""",(contact_id,))
    if bypass_claim_check:
        original=adapter.validate
        adapter.validate=lambda *_a:None
        try:
            outcome=service.execute(scope,prepared.action_id,prepared.action_hash)
        finally:
            adapter.validate=original
        assert outcome=={'state':'failed','effect':'none','code':'target_changed'}
    else:
        with pytest.raises(ValueError):
            service.execute(scope,prepared.action_id,prepared.action_hash)
        assert _state(context,prepared.action_id)[0]=='approved'
    (after,)=records.list_private_records(account_id=scope.user_id,workspace_id=scope.workspace_id,source_table='contacts_entries',limit=10)
    assert after['sourcePayload']['phone_number']=='222', "the owner's own edit survives"
    assert not after['sourcePayload'].get('notes')


def _link_session(context):
    """A second owner session bound as the current Link companion pairing."""
    from app.vault_runtime.local_identity.repository import LocalIdentityRepository
    from app.vault_runtime.local_identity.service import LocalIdentityService
    from app.core.security.tokens import hash_token
    from app.vault_runtime.link_companion.schema import ensure_link_companion_schema
    service=LocalIdentityService(repository=LocalIdentityRepository(database_url=context[0]),setup_credential_hash=hash_token('setup'))
    link=service.login(username='owner',password='owner-password').principal
    with psycopg.connect(context[0]) as connection:
        with connection.cursor() as cursor:
            ensure_link_companion_schema(cursor)
            cursor.execute('''INSERT INTO vault_private.link_companion_link (id,display_name,pairing_id,session_id)
                VALUES (1,'Phone','pairing-1',%s) ON CONFLICT (id) DO UPDATE SET session_id=EXCLUDED.session_id''',(link.session_id,))
    return link


def _channel_decision(principal,prepared,choice,channel,identifier):
    return ApprovalDecision(prepared.action_id,prepared.action_hash,choice,principal.user_id,principal.workspace_id,
                            channel,principal.session_id,identifier)


def test_simultaneous_browser_and_link_decisions_have_one_winner(context,actions):
    service,scope,prepared,domain=actions
    browser=context[1]
    link=_link_session(context)
    def choose(args):
        principal,choice,channel=args
        try:
            service.decide(principal,_channel_decision(principal,prepared,choice,channel,f'{channel}-{choice}'))
            return (channel,choice)
        except BackgroundRunConflictError:
            return 'conflict'
    for _round in range(3):
        pass
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes=list(pool.map(choose,[(browser,'allow_once','browser'),(link,'deny','link')]))
    assert outcomes.count('conflict')==1
    (winner,)=[o for o in outcomes if o!='conflict']
    state,_receipt=_state(context,prepared.action_id)
    assert state==('approved' if winner[1]=='allow_once' else 'denied')
    if state=='approved':
        assert service.execute(scope,prepared.action_id,prepared.action_hash)['state']=='completed'
    else:
        with pytest.raises(BackgroundRunAuthorizationError): service.claim(scope,prepared.action_id,prepared.action_hash)
    assert len(domain.effects)==(1 if state=='approved' else 0)


def test_a_link_decision_needs_the_current_pairing_and_unpairing_stops_its_claim(context,actions):
    service,scope,prepared,domain=actions
    link=_link_session(context)
    browser=context[1]
    # The browser session is not the paired Link session: it cannot decide as Link.
    with pytest.raises(BackgroundRunAuthorizationError):
        service.decide(browser,_channel_decision(browser,prepared,'allow_once','link','browser-as-link'))
    service.decide(link,_channel_decision(link,prepared,'allow_once','link','link-allow'))
    with psycopg.connect(context[0]) as connection:
        connection.execute('DELETE FROM vault_private.link_companion_link WHERE id=1')
    with pytest.raises(BackgroundRunAuthorizationError):
        service.claim(scope,prepared.action_id,prepared.action_hash)
    assert domain.effects==[] and _state(context,prepared.action_id)[0]=='approved'


def test_a_worker_reset_invalidates_its_prepared_and_approved_actions(context):
    from dataclasses import replace as _replace
    from app.vault_runtime.background_agent.actions import BackgroundActions
    from tests.support.background_authority import components, approve_fixture
    m, repo, owner, request, _authority, workers = components(context)
    proposal = workers.propose(owner, m.WorkerSpec('research', 'Research', 'Check sources', ('proof_read',), {}))
    worker_id = workers.create_from_approval(approve_fixture(context, proposal))
    work_id = repo.create_work(owner, request, 'assigned-work')
    unassigned = m.WorkScope(owner.user_id, owner.workspace_id, work_id, 1, None, None, None)
    repo.assign(unassigned, worker_id)
    scope = _replace(unassigned, worker_id=worker_id, worker_generation=1)
    domain = FakeDomain()
    service = BackgroundActions(database_url=context[0], domains={'proof': domain}, authorizer=lambda *_: True)
    approved = service.prepare(scope, 'proof', {'summary': 'Approved before reset'}, 'v1', 'existing-pending')
    pending = service.prepare(scope, 'proof', {'summary': 'Still pending at reset'}, 'v1', 'existing-pending')
    service.decide(context[1], decision(context, approved, identifier='before-reset'))
    assert workers.set_state(owner, worker_id, 1, 'reset') == 2
    # The old generation's scope is refused outright, and the new generation does not inherit them.
    with pytest.raises(BackgroundRunAuthorizationError):
        service.claim(scope, approved.action_id, approved.action_hash)
    with pytest.raises((BackgroundRunAuthorizationError, BackgroundRunConflictError)):
        service.decide(context[1], decision(context, pending, identifier='after-reset'))
    for action in (approved, pending):
        assert _state(context, action.action_id)[0] == 'expired'
    assert domain.effects == []


def test_mail_changed_after_approval_is_never_sent(context,actions,tmp_path):
    """Contacts/Mail no-effect regression: a send request edited after the owner approved it is
    refused before the provider call, as a confirmed no-effect failure."""
    from app.vault_runtime.email.runtime import LocalEmailRuntime
    from app.vault_runtime.email.schema import ensure_email_schema
    from app.vault_runtime.extensions.secrets import LocalMasterKey
    from tests.support.local_email_runtime import _credentials
    from app.vault_runtime.tools.definitions import ToolInvocationContext
    from app.vault_runtime.system_agents.inventory import AgentKind
    module=importlib.import_module('app.vault_runtime.background_agent.action_domains')
    service,scope,_prepared,_domain=actions
    with psycopg.connect(context[0]) as connection:
        with connection.cursor() as cursor:ensure_email_schema(cursor)
    sent=[]
    class Provider:
        def send_message(self,**kwargs):sent.append(kwargs['subject'])
    runtime=LocalEmailRuntime(database_url=context[0],master_key=LocalMasterKey(tmp_path/'mail.key'),provider=Provider())
    with runtime.service(context[1]) as mail:
        mailbox=mail.connect_mailbox(account_id=scope.user_id,workspace_id=scope.workspace_id,mailbox_role='normal_email',
            credentials_payload=_credentials('owner@example.com','fixture'),display_name='Fixture',validate_connection=False)
    def invocation(current,name):
        return ToolInvocationContext(agent=AgentKind.BACKGROUND,user_id=current.user_id,workspace_id=current.workspace_id,
            tool_call_id='mail-prepare-2',local_session_id=None,background_scope=current)
    adapter=module.MailSendDomain(runtime=runtime,context_factory=invocation)
    reference=adapter.prepare(scope,{'mailboxAccountId':mailbox['mailboxAccountId'],'to':['recipient@example.com'],'subject':'Approved','body':'Reviewed body'})
    service._domains['mail']=adapter
    prepared=service.prepare(scope,'mail',{'summary':'Send Approved'},adapter.version(scope,reference),reference)
    service.decide(context[1],decision(context,prepared))
    with psycopg.connect(context[0]) as connection:
        connection.execute("UPDATE vault_private.vault_email_send_requests SET body_text='Changed after approval'")
    original=adapter.validate
    adapter.validate=lambda *_a:None   # reach the effect's own pre-send check
    try:
        outcome=service.execute(scope,prepared.action_id,prepared.action_hash)
    finally:
        adapter.validate=original
    assert outcome=={'state':'failed','effect':'none','code':'draft_changed'}
    assert sent==[]
