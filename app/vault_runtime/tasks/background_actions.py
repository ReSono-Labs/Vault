"""Background confirmation over the existing Tasks pending/action SQL implementation."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import json

from app.vault_runtime.background_agent.authority import validate_approval_channel
from app.vault_runtime.background_agent.action_domains import resource_version
from app.vault_runtime.background_agent.coordination_repository import CoordinationRepository
from app.vault_runtime.background_agent.errors import BackgroundRunAuthorizationError,BackgroundRunConflictError
from .repository import _task_text


def _repository(repository):
    return CoordinationRepository(database_url=repository._database_url)


def _read(cursor,scope,reference,*,lock=False):
    cursor.execute('''SELECT * FROM vault_private.vault_task_pending_actions
        WHERE action_id=%s AND user_id=%s AND workspace_id=%s AND background_work_id=%s
        AND background_intent_version=%s AND voice_session_id IS NULL'''+(' FOR UPDATE' if lock else ''),
        (reference,scope.user_id,scope.workspace_id,scope.work_id,scope.intent_version))
    row=cursor.fetchone()
    if row is None:
        raise BackgroundRunAuthorizationError('Prepared Task action unavailable')
    return row


def _snapshot(cursor,scope,row,*,lock=False):
    target=None
    if row['operation']!='add':
        cursor.execute('SELECT updated_at::text AS revision FROM vault_private.vault_tasks WHERE task_id=%s AND user_id=%s AND workspace_id=%s'+(' FOR UPDATE' if lock else ''),
                       (row['task_id'],scope.user_id,scope.workspace_id))
        target=cursor.fetchone()
        if target is None: raise BackgroundRunConflictError('Task target no longer exists')
        target=target['revision']
    return {'taskId':row['task_id'],'operation':row['operation'],'payload':json.loads(row['payload_json']),
            'state':row['state'],'expires_at':row['expires_at'].isoformat(),'target_revision':row['target_revision'],
            'current_target_revision':target}


def prepare(repository,scope,arguments):
    if set(arguments)-{'operation','taskId','payload'} or arguments.get('operation') not in {'add','edit','complete','remove'}:
        raise ValueError('Invalid Task proposal')
    operation=arguments['operation']
    payload=arguments.get('payload',{})
    if not isinstance(payload,dict) or set(payload)-{'text'}: raise ValueError('Invalid Task payload')
    if operation in {'add','edit'}: _task_text(payload)
    repo=_repository(repository)
    with repo._connect() as connection,connection.cursor() as cursor:
        repo._work(cursor,scope)
        task_id=arguments.get('taskId') if operation!='add' else str(uuid4())
        revision=None
        if operation!='add':
            cursor.execute('SELECT updated_at::text AS revision FROM vault_private.vault_tasks WHERE task_id=%s AND user_id=%s AND workspace_id=%s FOR SHARE',
                           (task_id,scope.user_id,scope.workspace_id))
            target=cursor.fetchone()
            if target is None: raise ValueError('Task not found')
            revision=target['revision']
        reference=str(uuid4())
        canonical=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False)
        cursor.execute('''INSERT INTO vault_private.vault_task_pending_actions
            (action_id,user_id,workspace_id,task_id,operation,payload_json,content_hash,state,voice_session_id,
             tool_call_id,prepared_utterance_id,expires_at,background_work_id,background_intent_version,target_revision)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'pending_review',NULL,%s,0,%s,%s,%s,%s)''',
            (reference,scope.user_id,scope.workspace_id,task_id,operation,canonical,resource_version(payload),
             reference,datetime.now(timezone.utc)+timedelta(minutes=10),scope.work_id,scope.intent_version,revision))
        return reference


def snapshot(repository,scope,reference):
    repo=_repository(repository)
    with repo._connect() as connection,connection.cursor() as cursor:
        # Domain validation may run while the action service owns the work lock
        # on another connection. Read scope here; effect execution locks it below.
        repo._owner(cursor,scope)
        cursor.execute('SELECT * FROM vault_private.vault_background_work WHERE work_id=%s AND user_id=%s AND workspace_id=%s',
                       (scope.work_id,scope.user_id,scope.workspace_id))
        work=cursor.fetchone()
        if work is None or (work['intent_version'],work['worker_id'],work['worker_generation'],work['grant_id'])!=(scope.intent_version,scope.worker_id,scope.worker_generation,scope.grant_id):
            raise BackgroundRunAuthorizationError('Task work scope changed')
        repo._authority(cursor,scope,work['local_session_id'],work['grant_id'])
        return _snapshot(cursor,scope,_read(cursor,scope,reference))


def pending_state(repository,scope,reference):
    """The pending record's own state, for reconciliation after an effect. Unlike snapshot() it does
    not need the target Task: a removed Task is exactly what a completed removal leaves behind."""
    repo=_repository(repository)
    with repo._connect() as connection,connection.cursor() as cursor:
        repo._owner(cursor,scope)
        return _read(cursor,scope,reference)['state']


def execute(repository,scope,reference,operation_key):
    """The Task change and its pending completion are one transaction: an error raised before commit
    rolls everything back, so it is a confirmed no-effect failure. A failed commit stays uncertain."""
    from app.vault_runtime.background_agent.action_domains import NoEffectError
    repo=_repository(repository)
    with repo._connect() as connection,connection.cursor() as cursor:
        try:
            repo._work(cursor,scope)
            cursor.execute('''SELECT * FROM vault_private.vault_background_actions WHERE user_id=%s AND workspace_id=%s
                AND work_id=%s AND intent_version=%s AND kind='tasks' AND domain_ref=%s AND operation_key=%s AND state='executing' FOR UPDATE''',
                (scope.user_id,scope.workspace_id,scope.work_id,scope.intent_version,reference,operation_key))
            approved=cursor.fetchone()
            if approved is None or approved['worker_generation']!=scope.worker_generation or approved['expires_at']<=datetime.now(timezone.utc):
                raise NoEffectError('claim_invalid')
            validate_approval_channel(cursor,scope,approved['channel'],approved['channel_generation'])
            row=_read(cursor,scope,reference,lock=True)
            value=_snapshot(cursor,scope,row,lock=True)
            if (row['state']!='pending_review' or row['expires_at']<=datetime.now(timezone.utc)
                    or resource_version(value)!=approved['resource_version'] or value['target_revision']!=value['current_target_revision']):
                raise NoEffectError('draft_changed')
            task_id=repository._apply(cursor,user_id=scope.user_id,workspace_id=scope.workspace_id,claim=value)
            cursor.execute("UPDATE vault_private.vault_task_pending_actions SET state='completed',updated_at=now() WHERE action_id=%s",(reference,))
        except NoEffectError:
            raise
        except BackgroundRunAuthorizationError as exc:
            raise NoEffectError('claim_invalid') from exc
        except BackgroundRunConflictError as exc:
            raise NoEffectError('draft_changed') from exc
        except Exception as exc:
            raise NoEffectError('task_error') from exc
    return {'taskId':task_id,'operation':row['operation']}
