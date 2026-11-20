"""Exact, one-use prepared decisions. UI adapters authenticate before entering here."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from .action_domains import NoEffectError
from .authority import proposal_hash,validate_approval_channel
from .coordination_contracts import OwnerScope,WorkScope,PreparedAction
from .coordination_repository import CoordinationRepository,_json
from .errors import BackgroundRunAuthorizationError,BackgroundRunConflictError

SPECIAL={'worker_create','execution_grant','routine_create'}
# Rakazo's approval cards wait until the owner answers ("Cards never block the chat. Keep talking to
# the bot, and answer the card whenever you're ready", docs/approvals.md @83db73c). A week keeps an
# unanswered card bounded; the decision still binds the exact prepared hash and current resource version.
ACTION_TTL=timedelta(days=7)
OWNER_APPROVAL='owner_approval'   # owner_approvals.OwnerApprovals consumes these
REOPEN=':r:'  # operation-key suffix of an owner-reopened action: one reopen per source action


def _base_key(operation_key):
    return operation_key.split(REOPEN,1)[0]


def _reopenable(row,now):
    if row['kind']==OWNER_APPROVAL:
        return False   # an interactive question belongs to one tool call; a new call asks again
    # Never anything that ran or may have run: completed, executing, unknown, or a failure with an effect.
    if row['state']=='denied' or row['state']=='expired':
        return True
    if row['state']=='pending':
        return row['expires_at']<=now
    return row['state']=='failed' and (row['receipt_json'] or {}).get('effect')=='none'


class BackgroundActions:
    def __init__(self,*,database_url,domains=None,authorizer=None):
        self._repo=CoordinationRepository(database_url=database_url)
        self._domains=dict(domains or {})
        self._authorizer=authorizer

    def _authorize(self,scope,kind,reference,arguments):
        # The authorizer receives the stored original arguments, never only a display summary.
        if self._authorizer is None or not self._authorizer(scope,kind,reference,arguments):
            raise BackgroundRunAuthorizationError('Current Vault tool/resource authority is required')

    @staticmethod
    def now():
        return datetime.now(timezone.utc)

    def check(self,scope,kind,arguments):
        """Authority before a domain draft exists (the bridge calls this first)."""
        if not isinstance(scope,WorkScope) or kind in SPECIAL or kind not in self._domains:
            raise BackgroundRunAuthorizationError('Work authority and a registered domain are required')
        with self._repo._connect() as connection,connection.cursor() as cursor:
            self._scope(cursor,scope)
        self._authorize(scope,kind,None,_json(arguments))

    def get(self,scope,action_id):
        """One of this work's actions (scoped read, no lock)."""
        with self._repo._connect() as connection,connection.cursor() as cursor:
            self._scope(cursor,scope)
            cursor.execute('''SELECT * FROM vault_private.vault_background_actions
                WHERE user_id=%s AND workspace_id=%s AND action_id=%s''',(scope.user_id,scope.workspace_id,action_id))
            row=cursor.fetchone()
            if row is None:
                raise BackgroundRunAuthorizationError('Action unavailable in this scope')
            self._scope(cursor,scope,row)
            return row

    @staticmethod
    def _hash(kind,arguments,version,reference):
        return proposal_hash(kind,arguments if kind in SPECIAL else {
            'arguments':arguments,'resource_version':version,'domain_ref':reference})

    def _scope(self,cursor,scope,row=None):
        self._repo._owner(cursor,scope)
        if isinstance(scope,WorkScope):
            work=self._repo._work(cursor,scope)
            if row is not None and (row['work_id'],row['intent_version'],row['worker_generation'])!=(scope.work_id,scope.intent_version,scope.worker_generation):
                raise BackgroundRunAuthorizationError('Action belongs to another work intent')
            return work
        # Owner approvals (interactive Chat/Voice) belong to the account, like role/grant proposals.
        if row is not None and (row['work_id'] is not None or (row['kind'] not in SPECIAL and row['kind']!=OWNER_APPROVAL)):
            raise BackgroundRunAuthorizationError('Work authority is required')

    def _read(self,cursor,scope,action_id):
        # Scope/worker locks precede action locks throughout decision/claim paths.
        self._scope(cursor,scope)
        cursor.execute('''SELECT * FROM vault_private.vault_background_actions
            WHERE user_id=%s AND workspace_id=%s AND action_id=%s FOR UPDATE''',
            (scope.user_id,scope.workspace_id,action_id))
        row=cursor.fetchone()
        if row is None:
            raise BackgroundRunAuthorizationError('Action unavailable in this scope')
        self._scope(cursor,scope,row)
        return row

    def _exact(self,row,action_hash):
        if (row['action_hash']!=action_hash or self._hash(row['kind'],row['arguments_json'],row['resource_version'],row['domain_ref'])!=action_hash
                or row['expires_at']<=datetime.now(timezone.utc)):
            raise BackgroundRunAuthorizationError('Prepared action changed or expired')

    def prepare(self,scope,kind,arguments,resource_version,domain_ref,*,origin=None):
        if not isinstance(arguments,dict) or 'approve' in arguments:
            raise ValueError('Model approval is not an action argument')
        arguments=_json(arguments)
        if kind not in SPECIAL and (not isinstance(scope,WorkScope) or kind not in self._domains or not domain_ref or not resource_version):
            raise ValueError('A registered domain and prepared reference are required')
        if kind in SPECIAL and isinstance(scope,WorkScope):
            raise ValueError('Role and standing-grant proposals precede assignment')
        detail = str(arguments.get('summary') or kind)
        title = f'Review {kind.replace("_", " ")}'
        if kind == 'worker_create' and arguments.get('add_read_tool') == 'memory_lookup':
            title = f"Enable Vault Memory search for {arguments['role_key']}"
        if kind == 'execution_grant':
            detail = f"Purpose: {arguments.get('purpose', '')}\nTools: {', '.join(arguments.get('tool_names') or [])}"
        fingerprint=self._hash(kind,arguments,resource_version,domain_ref)
        work_id=scope.work_id if isinstance(scope,WorkScope) else None
        intent=scope.intent_version if isinstance(scope,WorkScope) else None
        generation=scope.worker_generation if isinstance(scope,WorkScope) else None
        operation=f'{kind}:{work_id}:{intent}:{generation}:{fingerprint}'
        with self._repo._connect() as connection,connection.cursor() as cursor:
            self._scope(cursor,scope)
            if kind not in SPECIAL:
                self._domains[kind].validate(scope,domain_ref,resource_version)
                self._authorize(scope,kind,domain_ref,arguments)
            cursor.execute('''INSERT INTO vault_private.vault_background_actions
                (action_id,user_id,workspace_id,work_id,intent_version,worker_generation,kind,action_hash,
                 arguments_json,domain_ref,resource_version,title,detail,expires_at,operation_key,origin_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(user_id,workspace_id,operation_key) DO NOTHING RETURNING *''',
                (str(uuid4()),scope.user_id,scope.workspace_id,work_id,intent,generation,kind,fingerprint,Jsonb(arguments),
                 domain_ref,resource_version,title,detail[:2048],
                 datetime.now(timezone.utc)+ACTION_TTL,operation,Jsonb(origin or {})))
            row=cursor.fetchone() or self._latest(cursor,scope,operation)
            # The same exact operation returns its open action. A denied, expired or finished one is not
            # revived by preparing it again; only the owner can reopen it (reopen()).
            if not (row['state']=='approved' or (row['state']=='pending' and row['expires_at']>datetime.now(timezone.utc))):
                raise BackgroundRunConflictError('This exact action was already decided or expired; the owner must reopen it')
            return self._prepared(row)

    @staticmethod
    def _prepared(row):
        return PreparedAction(row['action_id'],row['action_hash'],row['work_id'],row['kind'],row['title'],row['detail'],row['expires_at'])

    @staticmethod
    def _latest(cursor,scope,operation):
        cursor.execute('''SELECT * FROM vault_private.vault_background_actions
            WHERE user_id=%s AND workspace_id=%s AND (operation_key=%s OR starts_with(operation_key,%s))
            ORDER BY created_at DESC,action_id DESC LIMIT 1 FOR UPDATE''',
            (scope.user_id,scope.workspace_id,operation,operation+REOPEN))
        return cursor.fetchone()

    def _owner_action_scope(self,cursor,principal,action_id,channel,channel_generation):
        """An authenticated owner's channel, and the scope of one of their own actions (all lookups scoped)."""
        owner=OwnerScope(principal.user_id,principal.workspace_id)
        if channel not in {'browser','link'} or channel_generation!=principal.session_id:
            raise BackgroundRunAuthorizationError('Current authenticated channel is required')
        self._repo._owner(cursor,owner)
        self._repo._authority(cursor,owner,principal.session_id,None)
        validate_approval_channel(cursor,owner,channel,channel_generation)
        cursor.execute('SELECT work_id FROM vault_private.vault_background_actions WHERE user_id=%s AND workspace_id=%s AND action_id=%s',
                       (owner.user_id,owner.workspace_id,action_id))
        ref=cursor.fetchone()
        if ref is None:
            raise BackgroundRunAuthorizationError('Action unavailable')
        if not ref['work_id']:
            return owner
        cursor.execute('SELECT * FROM vault_private.vault_background_work WHERE user_id=%s AND workspace_id=%s AND work_id=%s',
                       (owner.user_id,owner.workspace_id,ref['work_id']))
        work=cursor.fetchone()
        if work is None:
            raise BackgroundRunAuthorizationError('Work unavailable')
        return WorkScope(owner.user_id,owner.workspace_id,work['work_id'],work['intent_version'],work['worker_id'],work['worker_generation'],work['grant_id'])

    def decide(self,principal,decision):
        if (decision.actor_user_id,decision.workspace_id)!=(principal.user_id,principal.workspace_id):
            raise BackgroundRunAuthorizationError('Decision actor does not match authenticated user')
        with self._repo._connect() as connection,connection.cursor() as cursor:
            scope=self._owner_action_scope(cursor,principal,decision.action_id,decision.channel,decision.channel_generation)
            row=self._read(cursor,scope,decision.action_id)
            self._exact(row,decision.action_hash)
            expected='approved' if decision.choice=='allow_once' else 'denied'
            if row['state']!='pending':
                if (row['decision_id']==decision.decision_id and row['actor_user_id']==decision.actor_user_id
                        and row['channel']==decision.channel and row['channel_generation']==decision.channel_generation
                        and (row['state']==expected or (expected=='approved' and row['state'] in {'executing','completed','failed','unknown'}))):
                    return row['decision_id']
                raise BackgroundRunConflictError('Action already decided')
            # A decision id names one decision of one action; reusing it elsewhere is a conflict.
            cursor.execute('''SELECT 1 FROM vault_private.vault_background_actions
                WHERE user_id=%s AND workspace_id=%s AND decision_id=%s AND action_id<>%s''',
                (scope.user_id,scope.workspace_id,decision.decision_id,decision.action_id))
            if cursor.fetchone() is not None:
                raise BackgroundRunConflictError('This decision id was already used for another action')
            try:
                cursor.execute('''UPDATE vault_private.vault_background_actions SET state=%s,decision_id=%s,actor_user_id=%s,
                    channel=%s,channel_generation=%s,updated_at=now() WHERE action_id=%s''',
                    (expected,decision.decision_id,decision.actor_user_id,decision.channel,decision.channel_generation,decision.action_id))
            except psycopg.errors.UniqueViolation as exc:   # the same id landed concurrently on another action
                raise BackgroundRunConflictError('This decision id was already used for another action') from exc
            return decision.decision_id

    def claim(self,scope,action_id,action_hash):
        with self._repo._connect() as connection,connection.cursor() as cursor:
            row=self._read(cursor,scope,action_id)
            self._exact(row,action_hash)
            if row['state']!='approved':
                if row['state'] in {'executing','completed','failed','unknown'}:
                    raise BackgroundRunConflictError('Action has already been claimed')
                raise BackgroundRunAuthorizationError('Explicit trusted approval is required')
            if row['kind'] in SPECIAL or row['kind']==OWNER_APPROVAL:
                raise ValueError('Use the approved worker/grant or owner-approval consumers')
            validate_approval_channel(cursor,scope,row['channel'],row['channel_generation'])
            self._domains[row['kind']].validate(scope,row['domain_ref'],row['resource_version'])
            self._authorize(scope,row['kind'],row['domain_ref'],row['arguments_json'])
            cursor.execute("UPDATE vault_private.vault_background_actions SET state='executing',updated_at=now() WHERE action_id=%s",(action_id,))
            return row | {'state':'executing'}

    def record_outcome(self,scope,action_id,outcome):
        if not isinstance(outcome,dict) or outcome.get('state') not in {'completed','failed','unknown'}:
            raise ValueError('A terminal effect receipt is required')
        outcome=_json(outcome)
        with self._repo._connect() as connection,connection.cursor() as cursor:
            row=self._read(cursor,scope,action_id)
            if row['state'] not in {'executing','unknown'}:
                if row['state']==outcome['state'] and row['receipt_json']==outcome:
                    return
                raise BackgroundRunConflictError('Action is not awaiting an effect receipt')
            cursor.execute('UPDATE vault_private.vault_background_actions SET state=%s,receipt_json=%s,updated_at=now() WHERE action_id=%s',
                           (outcome['state'],Jsonb(outcome),action_id))

    def execute(self,scope,action_id,action_hash):
        with self._repo._connect() as connection,connection.cursor() as cursor:
            row=self._read(cursor,scope,action_id)
            if row['state']=='completed':
                if row['action_hash']!=action_hash:
                    raise BackgroundRunAuthorizationError('Action hash changed')
                return row['receipt_json']
            if row['state'] in {'executing','unknown'}:
                return {'state':'unknown'}
        claimed=self.claim(scope,action_id,action_hash)
        domain=self._domains[claimed['kind']]
        try:
            result=domain.execute(scope,claimed['domain_ref'],claimed['operation_key'])
            outcome={'state':'completed','result':result}
        except NoEffectError as exc:
            # The domain confirmed nothing was done (a check before any effect, or a rolled-back transaction).
            outcome={'state':'failed','effect':'none','code':exc.code}
        except Exception:
            # A provider may have performed the effect before the connection failed.
            outcome={'state':'unknown'}
        self.record_outcome(scope,action_id,outcome)
        return outcome

    def reopen(self,principal,action_id,*,channel,channel_generation):
        """Owner-requested reopen of a denied, expired or no-effect-failed action: a new pending action
        for the same exact operation that needs its own decision. The original is never revived, and
        nothing that ran or may have run (completed, executing, unknown) can be reopened."""
        now=datetime.now(timezone.utc)
        with self._repo._connect() as connection,connection.cursor() as cursor:
            scope=self._owner_action_scope(cursor,principal,action_id,channel,channel_generation)
            row=self._read(cursor,scope,action_id)   # locks the source: concurrent reopens serialize
            if not _reopenable(row,now):
                raise BackgroundRunConflictError('Only a denied, expired or no-effect action can be reopened')
            if row['kind'] not in SPECIAL:
                try:
                    self._domains[row['kind']].validate(scope,row['domain_ref'],row['resource_version'])
                except (ValueError,BackgroundRunConflictError) as exc:
                    raise BackgroundRunConflictError('The prepared draft changed or expired; prepare it again') from exc
                self._authorize(scope,row['kind'],row['domain_ref'],row['arguments_json'])
            if row['state']=='pending':
                cursor.execute("UPDATE vault_private.vault_background_actions SET state='expired',updated_at=now() WHERE action_id=%s",(action_id,))
            cursor.execute('''INSERT INTO vault_private.vault_background_actions
                (action_id,user_id,workspace_id,work_id,intent_version,worker_generation,kind,origin_json,action_hash,
                 arguments_json,domain_ref,resource_version,title,detail,expires_at,operation_key)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(user_id,workspace_id,operation_key) DO NOTHING RETURNING *''',
                (str(uuid4()),row['user_id'],row['workspace_id'],row['work_id'],row['intent_version'],row['worker_generation'],
                 row['kind'],Jsonb({**(row['origin_json'] or {}),'reopened_from':action_id}),row['action_hash'],
                 Jsonb(row['arguments_json']),row['domain_ref'],row['resource_version'],row['title'],row['detail'],
                 now+ACTION_TTL,_base_key(row['operation_key'])+REOPEN+action_id))
            reopened=cursor.fetchone()
            if reopened is None:
                raise BackgroundRunConflictError('This action was already reopened')
            return self._prepared(reopened)

    def reconcile(self,scope,action_id):
        with self._repo._connect() as connection,connection.cursor() as cursor:
            row=self._read(cursor,scope,action_id)
            if row['state']=='completed':
                return row['receipt_json']
            if row['state'] not in {'executing','unknown'} or row['kind'] not in self._domains:
                raise BackgroundRunConflictError('No ambiguous effect to reconcile')
        outcome=self._domains[row['kind']].reconcile(scope,row['domain_ref'],row['operation_key'])
        if not isinstance(outcome,dict) or outcome.get('state') not in {'completed','unknown'}:
            raise ValueError('Domain reconciliation must provide evidence or remain unknown')
        self.record_outcome(scope,action_id,outcome)
        return outcome
