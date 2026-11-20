"""Adapters retain canonical domain drafts and effect receipts, not parallel payload stores."""
from datetime import datetime,timezone
from hashlib import sha256
import json
from typing import Protocol


class NoEffectError(Exception):
    """Raised by a domain's execute() only when it is certain nothing was done: a check before any
    effect failed, or the effect's own database transaction rolled back. Anything else stays unknown."""
    def __init__(self,code):
        super().__init__(code)
        self.code=str(code)[:64]


def resource_version(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


class ActionDomain(Protocol):
    def prepare(self,scope,arguments)->str: ...
    def version(self,scope,domain_ref)->str: ...
    def validate(self,scope,domain_ref,resource_version)->None: ...
    def execute(self,scope,domain_ref,operation_key)->dict: ...
    def reconcile(self,scope,domain_ref,operation_key)->dict: ...


class PendingRecordDomain:
    """Calendar/Contacts use their existing scoped personal-data pending record."""
    def __init__(self,*,store,source_table,prepare,execute,pending_states,terminal_states,target=None):
        self._store=store
        self._table=source_table
        self._prepare=prepare
        self._execute=execute
        self._pending=frozenset(pending_states)
        self._terminal=frozenset(terminal_states)
        # target(scope, pending_payload) -> the existing record the change applies to, or None.
        # Its content is part of the approved version: a target changed after preparation is
        # never overwritten with the stale draft.
        self._target=target

    def _bound(self,scope,payload):
        """The approved version: the pending record's hash, plus its target's hash when the change
        applies to an existing record (``<pending>.<target>``)."""
        pending=resource_version(payload)
        if self._target is None:
            return pending
        target=self._target(scope,payload)
        return f"{pending}.{'none' if target is None else resource_version(target)}"

    def _read(self,scope,reference):
        row=self._store.get_private_record(account_id=scope.user_id,workspace_id=scope.workspace_id,
                                          source_table=self._table,source_id=reference)
        if row is None or not isinstance(row.get('sourcePayload'),dict):
            raise ValueError('Prepared domain record is unavailable')
        return row['sourcePayload']

    def prepare(self,scope,arguments):
        return self._prepare(scope,arguments)

    def version(self,scope,domain_ref):
        return self._bound(scope,self._read(scope,domain_ref))

    def validate(self,scope,domain_ref,version):
        payload=self._read(scope,domain_ref)
        if payload.get('status') not in self._pending or self._bound(scope,payload)!=version:
            raise ValueError('Prepared domain record changed or was already used')
        expires=payload.get('expires_at') or payload.get('expiresAt')
        if not isinstance(expires,str):
            raise ValueError('Prepared domain record has no expiry')
        deadline=datetime.fromisoformat(expires)
        if deadline.tzinfo is None or deadline<=datetime.now(timezone.utc):
            raise ValueError('Prepared domain record expired')

    def execute(self,scope,domain_ref,operation_key):
        return self._execute(scope,domain_ref,operation_key)

    def pre_effect(self,scope,domain_ref,version):
        """Before the provider call: the record is still the approved, pending draft and its target is
        unchanged. Returns the pending record's own version for the domain's compare-and-swap.
        Residual window: a target edit between this check and the domain's write is not detected
        (the existing contact upsert has no compare-and-swap of its own)."""
        try:
            payload=self._read(scope,domain_ref)
        except ValueError as exc:
            raise NoEffectError('draft_unavailable') from exc
        approved_pending,_,approved_target=str(version).partition('.')
        current_pending,_,current_target=self._bound(scope,payload).partition('.')
        if payload.get('status') not in self._pending or current_pending!=approved_pending:
            raise NoEffectError('draft_changed')
        if current_target!=approved_target:
            raise NoEffectError('target_changed')
        return current_pending

    def reconcile(self,scope,domain_ref,operation_key):
        payload=self._read(scope,domain_ref)
        if payload.get('status') in self._terminal:
            return {'state':'completed','domain_ref':domain_ref}
        return {'state':'unknown'}


class TaskActionDomain:
    def __init__(self,*,repository):
        self._repository=repository

    def prepare(self,scope,arguments):
        from app.vault_runtime.tasks.background_actions import prepare
        return prepare(self._repository,scope,arguments)

    def _snapshot(self,scope,reference):
        from app.vault_runtime.tasks.background_actions import snapshot
        return snapshot(self._repository,scope,reference)

    def version(self,scope,domain_ref):
        return resource_version(self._snapshot(scope,domain_ref))

    def validate(self,scope,domain_ref,version):
        value=self._snapshot(scope,domain_ref)
        if (value['state']!='pending_review' or resource_version(value)!=version
                or value['target_revision']!=value['current_target_revision']
                or datetime.fromisoformat(value['expires_at'])<=datetime.now(timezone.utc)):
            raise ValueError('Prepared Task changed or expired')

    def execute(self,scope,domain_ref,operation_key):
        from app.vault_runtime.tasks.background_actions import execute
        return execute(self._repository,scope,domain_ref,operation_key)

    def reconcile(self,scope,domain_ref,operation_key):
        # The Task change and its pending completion commit together, so the pending state is the receipt.
        from app.vault_runtime.tasks.background_actions import pending_state
        state=pending_state(self._repository,scope,domain_ref)
        return {'state':'completed','domain_ref':domain_ref} if state=='completed' else {'state':'unknown'}


def calendar_domain(*,records,runtime,context_factory):
    from app.vault_runtime.calendar.tools import _calendar_create
    def prepare(scope,arguments):
        if 'pendingActionId' in arguments or 'approve' in arguments:
            raise ValueError('Prepare the exact event before requesting a decision')
        result=_calendar_create(runtime=runtime,records=records,context=context_factory(scope,'calendar_create'),arguments=arguments)
        return result['pendingActionId']
    def execute(scope,reference,operation_key):
        version=domain.pre_effect(scope,reference,_claimed(records._database_url,scope,'calendar',reference,operation_key))
        return _calendar_create(runtime=runtime,records=records,context=context_factory(scope,'calendar_create'),
                                arguments={'pendingActionId':reference,'approve':True},expected_pending_version=version)
    domain=PendingRecordDomain(store=records,source_table='calendar_pending_actions',prepare=prepare,execute=execute,
                               pending_states={'pending_confirmation'},terminal_states={'completed'})
    return domain


def contacts_domain(*,records,context_factory,usage=False):
    from app.vault_runtime.session_tools.brokers.contacts import contacts_tool_result
    prepare_name='contacts_prepare_use' if usage else 'contacts_prepare_save'
    confirm_name='contacts_confirm_use' if usage else 'contacts_confirm_pending'
    def invoke(scope,name,arguments,version=None):
        context=context_factory(scope,name)
        return contacts_tool_result(store=records,account_id=scope.user_id,workspace_id=scope.workspace_id,
            voice_realtime_session_id=context.voice_session_id,tool_call_id=context.tool_call_id,tool_name=name,arguments=arguments,expected_pending_version=version)
    def prepare(scope,arguments):
        if 'approve' in arguments or 'pendingActionId' in arguments:
            raise ValueError('Prepare contact data before requesting a decision')
        return invoke(scope,prepare_name,arguments)['pendingActionId']
    def execute(scope,reference,operation_key):
        kind='contacts_use' if usage else 'contacts'
        version=domain.pre_effect(scope,reference,_claimed(records._database_url,scope,kind,reference,operation_key))
        return invoke(scope,confirm_name,{'pendingActionId':reference,'approve':True},version)
    def target(scope,payload):
        # Updates, deletes and uses read an existing contact; a create has no target.
        if payload.get('action_type')=='create':
            return None
        contact_id=payload.get('contacts_entry_id')
        if not isinstance(contact_id,str) or not contact_id:
            return None
        row=records.get_private_record(account_id=scope.user_id,workspace_id=scope.workspace_id,
                                       source_table='contacts_entries',source_id=contact_id)
        return {'missing':contact_id} if row is None else row.get('sourcePayload')
    domain=PendingRecordDomain(store=records,source_table='contacts_pending_actions',prepare=prepare,execute=execute,
                               pending_states={'pending'},terminal_states={'confirmed'},target=target)
    return domain


def _claimed(database_url,scope,kind,reference,operation_key):
    """The trusted claim's approved version; a missing or stale claim means nothing was attempted."""
    from .errors import BackgroundRunAuthorizationError
    try:
        return trusted_claim_version(database_url,scope,kind,reference,operation_key)
    except BackgroundRunAuthorizationError as exc:
        raise NoEffectError('claim_invalid') from exc


def trusted_claim_version(database_url,scope,kind,reference,operation_key):
    """Native effects consume a current server-written claim, never a model flag."""
    from .coordination_repository import CoordinationRepository
    from .authority import validate_approval_channel
    from .errors import BackgroundRunAuthorizationError
    repo=CoordinationRepository(database_url=database_url)
    with repo._connect() as connection,connection.cursor() as cursor:
        repo._work(cursor,scope)
        cursor.execute("""SELECT * FROM vault_private.vault_background_actions WHERE user_id=%s AND workspace_id=%s
            AND work_id=%s AND intent_version=%s AND kind=%s AND domain_ref=%s AND operation_key=%s AND state='executing' FOR SHARE""",
            (scope.user_id,scope.workspace_id,scope.work_id,scope.intent_version,kind,reference,operation_key))
        row=cursor.fetchone()
        if row is None or row['worker_generation']!=scope.worker_generation or row['expires_at']<=datetime.now(timezone.utc):
            raise BackgroundRunAuthorizationError('Trusted domain effect claim required')
        validate_approval_channel(cursor,scope,row['channel'],row['channel_generation'])
        return row['resource_version']


class MailSendDomain:
    def __init__(self,*,runtime,context_factory,kind='mail',mailbox_role='normal_email'):
        self._runtime=runtime
        self._context=context_factory
        self._kind=kind
        self._role=mailbox_role

    @staticmethod
    def _reference(reference):
        value=json.loads(reference)
        if not isinstance(value,dict) or set(value)!={'mailbox_id','pending_request_id'} or any(not isinstance(v,str) or not v for v in value.values()):
            raise ValueError('Invalid Mail draft reference')
        return value

    def prepare(self,scope,arguments):
        if set(arguments)-{'mailboxAccountId','to','subject','body'}:
            raise ValueError('Prepare exact Mail recipients, subject and body')
        mailbox=arguments.get('mailboxAccountId')
        context=self._context(scope,'email_compose')
        with self._runtime.service(scope) as mail:
            account=mail._require_active_mailbox(account_id=scope.user_id,workspace_id=scope.workspace_id,mailbox_id=mailbox)
            if account.get('mailboxRole')!=self._role:
                raise ValueError('Mail role does not match this tool')
            prepared=mail.prepare_send(account_id=scope.user_id,workspace_id=scope.workspace_id,mailbox_id=mailbox,
                idempotency_key=context.tool_call_id,to_recipients=arguments.get('to',[]),subject=arguments.get('subject'),body=arguments.get('body'))
        return json.dumps({'mailbox_id':mailbox,'pending_request_id':prepared['pendingRequestId']},sort_keys=True,separators=(',',':'))

    def _snapshot(self,scope,reference):
        keys=self._reference(reference)
        with self._runtime.service(scope) as mail:
            return mail.read_prepared_send(account_id=scope.user_id,workspace_id=scope.workspace_id,**keys)

    def version(self,scope,domain_ref):
        return resource_version(self._snapshot(scope,domain_ref))

    def validate(self,scope,domain_ref,version):
        value=self._snapshot(scope,domain_ref)
        if (value['status']!='pending_confirmation' or resource_version(value)!=version
                or datetime.fromisoformat(value['expiresAt'])<=datetime.now(timezone.utc)):
            raise ValueError('Prepared Mail changed or expired')

    def execute(self,scope,domain_ref,operation_key):
        version=_claimed(self._runtime._database_url,scope,self._kind,domain_ref,operation_key)
        try:
            value=self._snapshot(scope,domain_ref)
        except ValueError as exc:
            raise NoEffectError('draft_unavailable') from exc
        if value['status']!='pending_confirmation' or resource_version(value)!=version:
            raise NoEffectError('draft_changed')
        keys=self._reference(domain_ref)
        with self._runtime.service(scope) as mail:
            result=mail.confirm_send(account_id=scope.user_id,workspace_id=scope.workspace_id,**keys,
                                     approve=True,expected_version=version)
        if result.get('status')!='sent':
            raise RuntimeError('Mail send outcome requires reconciliation')
        return result

    def reconcile(self,scope,domain_ref,operation_key):
        value=self._snapshot(scope,domain_ref)
        return {'state':'completed','domain_ref':domain_ref} if value['status']=='sent' else {'state':'unknown'}
