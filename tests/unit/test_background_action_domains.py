from copy import deepcopy
from datetime import datetime,timedelta,timezone

import pytest


def domain():
    import importlib,importlib.util
    assert importlib.util.find_spec('app.vault_runtime.background_agent.action_domains') is not None,'Missing existing-domain adapters'
    return importlib.import_module('app.vault_runtime.background_agent.action_domains')


@pytest.mark.parametrize('source,terminal',[('calendar_pending_actions','completed'),('contacts_pending_actions','confirmed')])
def test_record_adapter_reuses_existing_pending_data_and_detects_changes(source,terminal):
    from app.vault_runtime.background_agent.coordination_contracts import OwnerScope
    module=domain()
    payload={'status':'pending','arguments':{'text':'exact'},'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()}
    class Store:
        def get_private_record(self,**kwargs):
            assert kwargs['source_table']==source
            return {'sourcePayload':deepcopy(payload)}
    effects=[]
    adapter=module.PendingRecordDomain(store=Store(),source_table=source,pending_states={'pending'},terminal_states={terminal},
        prepare=lambda scope,args:'existing',execute=lambda scope,ref,key:effects.append(ref) or {'ok':True})
    scope=OwnerScope('user','workspace')
    ref=adapter.prepare(scope,{'text':'exact'})
    version=adapter.version(scope,ref)
    adapter.validate(scope,ref,version)
    payload['arguments']['text']='changed'
    with pytest.raises(ValueError):adapter.validate(scope,ref,version)
    assert effects==[]
    payload['arguments']['text']='exact'
    assert adapter.execute(scope,ref,'operation')=={'ok':True}
    assert effects==['existing']
    assert adapter.reconcile(scope,ref,'operation')=={'state':'unknown'}
    payload['status']=terminal
    assert adapter.reconcile(scope,ref,'operation')['state']=='completed'


def test_background_commands_use_scope_without_fabricated_session():
    from app.vault_runtime.background_agent.coordination_contracts import OwnerScope,WorkScope
    from app.vault_runtime.commands.tools import register_command_tools
    from app.vault_runtime.system_agents.inventory import AgentKind
    from app.vault_runtime.tools.catalog import ToolCatalog
    from app.vault_runtime.tools.definitions import ToolInvocationContext
    class Service:
        def enabled(self):return True
        def run_background(self,*,principal,**_):
            assert isinstance(principal,OwnerScope)
            assert not hasattr(principal,'session_id')
            return {'ok':True}
    catalog=ToolCatalog(authorizer=lambda *_:True,background_authorizer=lambda *_:True)
    register_command_tools(catalog=catalog,service=Service())
    context=ToolInvocationContext(agent=AgentKind.BACKGROUND,user_id='user',workspace_id='workspace',tool_call_id='call',
        local_session_id=None,background_scope=WorkScope('user','workspace','work',1,None,None,'grant'))
    assert not catalog.invoke('command_run_read_only',{'directory':'local/Projects','command':'ls'},context=context).is_error


def test_delegated_task_prepare_uses_common_action_bridge_and_requires_it():
    from app.vault_runtime.tasks_tools import register_tasks_tools
    from app.vault_runtime.background_agent.coordination_contracts import WorkScope
    from app.vault_runtime.system_agents.inventory import AgentKind
    from app.vault_runtime.tools.catalog import ToolCatalog
    from app.vault_runtime.tools.definitions import ToolInvocationContext,ToolInvocationResult
    calls=[]
    class Bridge:
        def invoke(self,context,name,args):
            calls.append((name,args))
            return ToolInvocationResult('waiting for owner',{'status':'waiting_approval'})
    catalog=ToolCatalog(authorizer=lambda *_:True,background_authorizer=lambda *_:True)
    register_tasks_tools(catalog=catalog,repository=object(),background_actions=Bridge())
    ctx=ToolInvocationContext(agent=AgentKind.BACKGROUND,user_id='user',workspace_id='workspace',tool_call_id='call',
        local_session_id=None,background_scope=WorkScope('user','workspace','work',1,None,None,'grant'))
    result=catalog.invoke('tasks_add',{'text':'Review'},context=ctx)
    assert not result.is_error and result.structured_content=={'status':'waiting_approval'}
    assert calls==[('tasks_add',{'text':'Review'})]
    closed=ToolCatalog(authorizer=lambda *_:True,background_authorizer=lambda *_:True)
    register_tasks_tools(catalog=closed,repository=object())
    assert closed.invoke('tasks_add',{'text':'Review'},context=ctx).is_error


@pytest.mark.parametrize('family,name,args',[
    ('calendar','calendar_create',{'linkedAccountId':'calendar','title':'Review','startsAt':'2026-11-18T10:00:00Z'}),
    ('contacts','contacts_prepare_save',{'actionType':'create','firstName':'Review'}),
    ('email','email_compose',{'to':['recipient@example.com'],'subject':'Review','body':'Body'}),
    ('email','agent_mail_compose',{'to':['recipient@example.com'],'subject':'Review','body':'Body'}),
])
def test_delegated_domain_writes_require_the_common_bridge(family,name,args):
    from app.vault_runtime.background_agent.coordination_contracts import WorkScope
    from app.vault_runtime.system_agents.inventory import AgentKind
    from app.vault_runtime.tools.catalog import ToolCatalog
    from app.vault_runtime.tools.definitions import ToolInvocationContext,ToolInvocationResult
    class Bridge:
        def invoke(self,context,tool,arguments):
            assert (tool,arguments)==(name,args)
            return ToolInvocationResult('waiting',{'status':'waiting_approval'})
    def register(catalog,bridge):
        if family=='calendar':
            from app.vault_runtime.calendar.tools import register_calendar_tools
            register_calendar_tools(catalog=catalog,runtime=object(),records=object(),background_actions=bridge)
        elif family=='contacts':
            from app.vault_runtime.contacts_tools import register_contacts_tools
            register_contacts_tools(catalog=catalog,store=object(),background_actions=bridge)
        else:
            from app.vault_runtime.email.tools import register_email_tools
            register_email_tools(catalog=catalog,runtime=object(),background_actions=bridge)
    ctx=ToolInvocationContext(agent=AgentKind.BACKGROUND,user_id='user',workspace_id='workspace',tool_call_id='call',
        local_session_id=None,background_scope=WorkScope('user','workspace','work',1,None,None,'grant'))
    for bridge in (Bridge(),None):
        catalog=ToolCatalog(authorizer=lambda *_:True,background_authorizer=lambda *_:True)
        register(catalog,bridge)
        result=catalog.invoke(name,args,context=ctx)
        assert result.is_error==(bridge is None)
