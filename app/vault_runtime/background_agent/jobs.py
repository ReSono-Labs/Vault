"""Package-owned durable queue with Vault-owned authority, admission and attempt fences."""
from __future__ import annotations

import asyncio
import logging
import math
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Event, Lock, Thread
from time import monotonic

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row, tuple_row
from psycopg.types.json import Jsonb
import procrastinate
from procrastinate.worker import Worker

from .authority import BackgroundAuthority
from .coordination_contracts import ExecutionOutcome, WorkScope, WorkState, WORK_TRANSITIONS
from .coordination_repository import CoordinationRepository
from .errors import BackgroundRunAuthorizationError, BackgroundRunConflictError

ACTIVE = ('running', 'reviewing', 'repairing')
ADMISSION_KEY = 'vault-background-admission-v1'
ROUTINE_TICK_SECONDS = 15.0


def admission_available(cursor, user_id):
    """Call before acquiring run/work row locks; shared by legacy and durable paths."""
    cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (ADMISSION_KEY,))
    cursor.execute("""SELECT count(*) AS total,count(*) FILTER (WHERE user_id=%s) AS owned
        FROM vault_private.vault_background_runs WHERE state IN ('running','reviewing','repairing')""", (user_id,))
    row = cursor.fetchone()
    values = tuple(row.values()) if isinstance(row, dict) else row
    return values[0] < 4 and values[1] < 2


class _HonorJobRetry(procrastinate.BaseRetryStrategy):
    """Retry exactly when a task raises JobRetry (e.g. admission full); every other error fails.

    Without a strategy procrastinate 3.11 fails a job that raises JobRetry (worker.py,
    tasks.get_retry_exception), which left admitted-later work stranded in 'queued'."""

    def get_retry_decision(self, *, exception, job):
        return exception.retry_decision if isinstance(exception, procrastinate.exceptions.JobRetry) else None


RETRY = _HonorJobRetry()


@dataclass(frozen=True)
class JobAttempt:
    scope: WorkScope
    run_id: str
    generation: int
    request: dict
    tool_calls: int
    model_turns: int
    active_seconds: float
    checkpoint: dict | None


class BackgroundJobs:
    def __init__(self, *, database_url, executor, routines=None, record_outcome=None, deliver_outcome=None, resume_assignments=None):
        self._url = database_url
        self._repo = CoordinationRepository(database_url=database_url)
        self._authority = BackgroundAuthority(database_url=database_url)
        self._executor = executor
        self._routines = routines
        self._record_outcome = record_outcome
        self._deliver_outcome = deliver_outcome
        self._resume_assignments = resume_assignments
        self._dsn = make_conninfo(database_url, options='-csearch_path=vault_background_queue,public')
        self._sync = procrastinate.App(connector=procrastinate.SyncPsycopgConnector(conninfo=self._dsn))
        self._defer = self._sync.task(name='vault.work', retry=RETRY)(self._dispatch)
        self._defer_wake = self._sync.task(name='vault.wake')(self._wake)
        self._wake_handler = None
        self._checkins = None
        self._thread = None
        self._worker = None
        self._failure = None
        self._lock = Lock()
        self._ready = Event()
        self._stop_requested = Event()

    def attach_routines(self, routines) -> None:
        self._routines = routines

    def attach_checkins(self, checkins) -> None:
        """``checkins(now)``: the coordinator's daily look at unfinished work, run hourly."""
        self._checkins = checkins

    def attach_wake(self, handler) -> None:
        """``handler(user_id, workspace_id, conversation_id) -> 'started'|'idle'|'busy'|'closed'|'unavailable'``."""
        self._wake_handler = handler

    def _register(self, app):
        app.task(name='vault.work', retry=RETRY)(self._dispatch)
        app.task(name='vault.wake')(self._wake)

    def request_wake(self, user_id, workspace_id, conversation_id, *, delay_seconds=2.0, deadline=None):
        """Durably ask for a coordinator turn in this conversation.

        One waiting wake per conversation (queueing lock) collects every update that lands before it
        runs, so a burst of approvals or results produces one coordinator turn. The turn itself reads
        what changed from Vault's records, so a coalesced or repeated wake never loses or repeats work."""
        if not conversation_id:
            return False
        due = datetime.now(timezone.utc) + timedelta(seconds=max(0.0, float(delay_seconds)))
        if deadline is None:
            deadline = int((datetime.now(timezone.utc) + timedelta(minutes=30)).timestamp())
        with psycopg.connect(self._dsn, autocommit=True) as connection:
            try:
                self._defer_wake.configure(connection=connection, queueing_lock='vault-wake:'+conversation_id,
                    lock='vault-wake-run:'+conversation_id, schedule_at=due).defer(
                    user_id=user_id, workspace_id=workspace_id, conversation_id=conversation_id, deadline=deadline)
            except procrastinate.exceptions.AlreadyEnqueued:
                return False
        return True

    async def _wake(self, user_id, workspace_id, conversation_id, deadline):
        handler = self._wake_handler
        expired = datetime.now(timezone.utc).timestamp() > deadline
        if handler is None:
            state = 'busy'
        else:
            try:
                state = await asyncio.to_thread(handler, user_id, workspace_id, conversation_id)
            except Exception:
                logging.getLogger(__name__).warning("coordinator_wake_failed")
                state = 'busy'
        if state == 'busy' and not expired:
            # The task has no package retry strategy: ask again as a new waiting wake, which also
            # absorbs any update that lands meanwhile (the queueing lock admits it once this one runs).
            await asyncio.to_thread(self.request_wake, user_id, workspace_id, conversation_id,
                                    delay_seconds=5.0, deadline=deadline)

    def ensure_schema(self):
        self._repo.ensure_schema()
        with psycopg.connect(self._url) as connection:
            connection.execute('CREATE SCHEMA IF NOT EXISTS vault_background_queue')
            connection.execute('ALTER TABLE vault_private.vault_background_runs ADD COLUMN IF NOT EXISTS dispatch_job_id bigint')
        with self._sync.open():
            with psycopg.connect(self._dsn) as connection:
                exists = connection.execute("SELECT to_regclass('vault_background_queue.procrastinate_jobs')").fetchone()[0]
            if exists is None:
                self._sync.schema_manager.apply_schema()
        self._schema_ensured = True

    @staticmethod
    def _scope(row):
        return WorkScope(row['user_id'], row['workspace_id'], row['work_id'], row['intent_version'],
                         row['worker_id'], row['worker_generation'], row['grant_id'])

    @contextmanager
    def _queue_path(self, connection):
        with connection.cursor(row_factory=tuple_row) as cursor:
            prior = cursor.execute('SHOW search_path').fetchone()[0]
        connection.execute("SELECT set_config('search_path','vault_background_queue,public',true)")
        try:
            yield
        finally:
            if connection.info.transaction_status != psycopg.pq.TransactionStatus.INERROR:
                connection.execute("SELECT set_config('search_path',%s,true)", (prior,))

    def enqueue(self, connection, work_id, not_before=None):
        if not_before is not None and (not isinstance(not_before, datetime) or not_before.tzinfo is None):
            raise ValueError('Schedule must be timezone aware')
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute('SELECT * FROM vault_private.vault_background_work WHERE work_id=%s', (work_id,))
            row = cursor.fetchone()
            if row is None:
                raise BackgroundRunAuthorizationError('Unknown work')
            row = self._repo._work(cursor, self._scope(row))
            request = row['request_json']['request']
            if row['state'] == 'queued':
                cursor.execute('SELECT dispatch_job_id FROM vault_private.vault_background_runs WHERE work_id=%s', (work_id,))
                stored = cursor.fetchone()
                if stored and stored['dispatch_job_id'] is not None:
                    return stored['dispatch_job_id']
            if row['state'] != 'ready':
                raise BackgroundRunConflictError('Only ready work can be dispatched')
            cursor.execute("""INSERT INTO vault_private.vault_background_runs
                (run_id,user_id,workspace_id,local_session_id,execution_grant_id,work_id,request_json,state)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'queued') ON CONFLICT(run_id) DO NOTHING""",
                (request['run_id'],row['user_id'],row['workspace_id'],row['local_session_id'],row['grant_id'],work_id,Jsonb(request)))
            cursor.execute('SELECT work_id FROM vault_private.vault_background_runs WHERE run_id=%s FOR UPDATE', (request['run_id'],))
            if cursor.fetchone()['work_id'] != work_id:
                raise BackgroundRunConflictError('Run ID belongs to another work item')
            with self._queue_path(connection):
                job_id = self._defer.configure(connection=connection, lock='vault-work:'+work_id,
                    schedule_at=not_before).defer(work_id=work_id)
            cursor.execute("UPDATE vault_private.vault_background_work SET state='queued',updated_at=now() WHERE work_id=%s", (work_id,))
            cursor.execute("UPDATE vault_private.vault_background_runs SET state='queued',dispatch_job_id=%s,updated_at=now() WHERE work_id=%s", (job_id,work_id))
            return job_id

    def claim(self, work_id):
        with self._repo._connect() as connection, connection.cursor() as cursor:
            cursor.execute('SELECT * FROM vault_private.vault_background_work WHERE work_id=%s', (work_id,))
            row = cursor.fetchone()
            if row is None or row['state'] != 'queued':
                return None
            if not admission_available(cursor,row['user_id']):
                return None
            scope = self._scope(row)
            row = self._repo._work(cursor,scope)
            if row['state'] != 'queued':
                return None
            cursor.execute('SELECT * FROM vault_private.vault_background_runs WHERE work_id=%s FOR UPDATE',(work_id,))
            run = cursor.fetchone()
            if not run or run['cancellation_requested']:
                raise BackgroundRunAuthorizationError('Run cancelled or unavailable')
            limits = row['request_json']['request']['limits']
            if run['tool_calls'] >= limits['max_tool_calls'] or run['model_turns'] >= limits['max_model_turns'] or run['active_seconds'] >= limits['max_seconds']:
                cursor.execute("UPDATE vault_private.vault_background_work SET state='failed',updated_at=now() WHERE work_id=%s",(work_id,))
                cursor.execute("UPDATE vault_private.vault_background_runs SET state='failed',failure_code='budget_exhausted',updated_at=now() WHERE work_id=%s",(work_id,))
                return None
            cursor.execute("""UPDATE vault_private.vault_background_runs SET state='running',attempt_generation=attempt_generation+1,
                first_started_at=COALESCE(first_started_at,now()),updated_at=now()
                WHERE work_id=%s RETURNING attempt_generation""",(work_id,))
            generation=cursor.fetchone()['attempt_generation']
            cursor.execute("UPDATE vault_private.vault_background_work SET state='running',updated_at=now() WHERE work_id=%s",(work_id,))
            return JobAttempt(scope,run['run_id'],generation,row['request_json'],run['tool_calls'],run['model_turns'],run['active_seconds'],run['checkpoint_json'])

    def _attempt(self,cursor,attempt):
        row=self._repo._work(cursor,attempt.scope)
        cursor.execute('SELECT * FROM vault_private.vault_background_runs WHERE work_id=%s FOR UPDATE',(attempt.scope.work_id,))
        run=cursor.fetchone()
        if row['state']!='running' or run is None or run['attempt_generation']!=attempt.generation or run['cancellation_requested']:
            raise BackgroundRunAuthorizationError('Execution attempt is no longer current')
        return row,run

    def validate_attempt(self,attempt):
        with self._repo._connect() as connection,connection.cursor() as cursor:
            self._attempt(cursor,attempt)

    def debit(self,attempt,*,tool_calls=0,model_turns=0,active_seconds=0):
        if (any(type(n) is not int or n<0 for n in (tool_calls,model_turns))
                or not isinstance(active_seconds,(int,float)) or not math.isfinite(active_seconds) or active_seconds<0):
            raise ValueError('Budget debit must be nonnegative')
        with self._repo._connect() as connection,connection.cursor() as cursor:
            row,run=self._attempt(cursor,attempt)
            limits=row['request_json']['request']['limits']
            if run['tool_calls']+tool_calls>limits['max_tool_calls'] or run['model_turns']+model_turns>limits['max_model_turns'] or run['active_seconds']+active_seconds>limits['max_seconds']:
                raise BackgroundRunAuthorizationError('Cumulative execution budget exhausted')
            cursor.execute('UPDATE vault_private.vault_background_runs SET tool_calls=tool_calls+%s,model_turns=model_turns+%s,active_seconds=active_seconds+%s WHERE work_id=%s',
                (tool_calls,model_turns,active_seconds,attempt.scope.work_id))

    def finish(self,attempt,outcome):
        with self._repo._connect() as connection,connection.cursor() as cursor:
            try:
                row, _run = self._attempt(cursor,attempt)
            except BackgroundRunAuthorizationError:
                return False
            if self._record_outcome is not None:
                outcome = self._record_outcome(cursor, attempt, row, outcome)
            if outcome.state not in WORK_TRANSITIONS[WorkState.RUNNING]:
                raise ValueError('Invalid execution outcome')
            state=outcome.state.value
            terminal=state in {'completed','failed','cancelled','unknown'}
            if terminal:
                if not self._repo._accept_result(cursor, attempt.scope, attempt.run_id, outcome):
                    return False
            else:
                cursor.execute('UPDATE vault_private.vault_background_work SET state=%s,updated_at=now() WHERE work_id=%s',
                    (state,attempt.scope.work_id))
            checkpoint = outcome.checkpoint
            if checkpoint is not None and outcome.pending_action_id:
                checkpoint = {**checkpoint, "pending_action_id": outcome.pending_action_id}
            # Legacy run-state projection deliberately stays within its existing enum.
            projected=state if state in {'completed','failed','cancelled'} else ('failed' if state=='unknown' else 'queued')
            cursor.execute('''UPDATE vault_private.vault_background_runs SET state=%s,checkpoint_json=%s,output_json=%s,
                failure_code=%s,failure_message=%s,completed_at=CASE WHEN %s THEN now() ELSE NULL END,updated_at=now()
                WHERE work_id=%s''',
                (projected,Jsonb(checkpoint) if checkpoint is not None else None,
                 Jsonb(outcome.output) if outcome.output is not None else None,outcome.failure_code,
                 outcome.failure_message,terminal,attempt.scope.work_id))
        if self._deliver_outcome is not None:
            try:
                self._deliver_outcome(attempt, outcome)
            except Exception:
                logging.getLogger(__name__).warning("Background result delivery failed")
        return True

    def cancel(self,connection,work_id):
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute('SELECT * FROM vault_private.vault_background_work WHERE work_id=%s',(work_id,))
            row=cursor.fetchone()
            if row is None:
                raise BackgroundRunAuthorizationError('Unknown work')
            self._repo._work(cursor,self._scope(row),cancelling=True)
            if row['state'] in {'completed','failed','cancelled','unknown'}:
                return
            cursor.execute("""UPDATE vault_private.vault_background_runs
                SET cancellation_requested=true,attempt_generation=attempt_generation+1,
                    active_seconds=active_seconds + CASE WHEN state='running'
                        THEN GREATEST(0, EXTRACT(EPOCH FROM now()-updated_at)) ELSE 0 END,
                    state='cancelled',updated_at=now() WHERE work_id=%s RETURNING dispatch_job_id""",(work_id,))
            run=cursor.fetchone()
            cursor.execute("UPDATE vault_private.vault_background_work SET state='cancelled',updated_at=now() WHERE work_id=%s AND state NOT IN ('completed','failed','cancelled','unknown')",(work_id,))
            if run and run['dispatch_job_id'] is not None:
                with self._queue_path(connection):
                    self._sync.job_manager.cancel_job_by_id(run['dispatch_job_id'],abort=True,connection=connection)

    async def _dispatch(self,work_id):
        attempt=self.claim(work_id)
        if attempt is None:
            with self._repo._connect() as connection:
                row=connection.execute('SELECT state FROM vault_private.vault_background_work WHERE work_id=%s',(work_id,)).fetchone()
            if row and row['state']=='queued':
                raise procrastinate.exceptions.JobRetry(procrastinate.RetryDecision(retry_in={'seconds':2}))
            return
        started=monotonic()
        try:
            remaining=attempt.request['request']['limits']['max_seconds']-attempt.active_seconds
            outcome=await asyncio.wait_for(self._executor(attempt),timeout=remaining)
            self.debit(attempt,active_seconds=monotonic()-started)
            self.finish(attempt,outcome)
        except asyncio.CancelledError:
            self.finish(attempt,ExecutionOutcome(WorkState.UNKNOWN,failure_code='execution_interrupted'))
            raise
        except Exception:
            # Effects may already exist; only domain reconciliation may authorize a resend.
            self.finish(attempt,ExecutionOutcome(WorkState.UNKNOWN,failure_code='execution_outcome_unknown'))
            raise

    async def run_pending(self):
        self.resume_decided()
        app=procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=self._dsn))
        self._register(app)
        async with app.open_async():
            await app.run_worker_async(wait=False,concurrency=4,install_signal_handlers=False,listen_notify=False)

    def resume_decided(self) -> int:
        """Wake parked jobs from their persisted approval, including after a restart."""
        with self._repo._connect() as connection, connection.cursor() as cursor:
            cursor.execute("""
                SELECT w.*, r.attempt_generation
                FROM vault_private.vault_background_work w
                JOIN vault_private.vault_background_runs r USING (work_id, user_id, workspace_id)
                JOIN vault_private.vault_background_actions a
                  ON a.work_id = w.work_id AND a.user_id = w.user_id
                 AND a.workspace_id = w.workspace_id AND a.intent_version = w.intent_version
                 AND a.worker_generation IS NOT DISTINCT FROM w.worker_generation
                 AND a.action_id = r.checkpoint_json->>'pending_action_id'
                WHERE w.state IN ('waiting_approval', 'waiting_input')
                  AND NOT r.cancellation_requested
                  AND (a.state IN ('approved', 'denied', 'expired')
                       OR (a.state = 'pending' AND a.expires_at <= now()))
                ORDER BY w.updated_at, w.work_id
            """)
            candidates = cursor.fetchall()

        resumed = self._resume_assignments() if self._resume_assignments is not None else 0
        for candidate in candidates:
            scope = self._scope(candidate)
            try:
                with self._repo._connect() as connection, connection.cursor() as cursor:
                    work = self._repo._work(cursor, scope)
                    if work['state'] not in {'waiting_approval', 'waiting_input'}:
                        continue
                    cursor.execute("""
                        SELECT attempt_generation, cancellation_requested
                        FROM vault_private.vault_background_runs
                        WHERE work_id = %s FOR UPDATE
                    """, (scope.work_id,))
                    run = cursor.fetchone()
                    if (run is None or run['cancellation_requested']
                            or run['attempt_generation'] != candidate['attempt_generation']):
                        continue
                    cursor.execute("""
                        UPDATE vault_private.vault_background_work SET state = 'ready', updated_at = now()
                        WHERE work_id = %s
                    """, (scope.work_id,))
                    self.enqueue(connection, scope.work_id)
            except (BackgroundRunAuthorizationError, BackgroundRunConflictError):
                # Revocation, reset or a changed intent can invalidate a candidate after selection.
                continue
            resumed += 1
        return resumed

    async def reconcile_stalled(self, app):
        count=0
        # This check runs inside our own worker's loop, so that worker is alive: a late heartbeat
        # from it means a slow call, not a crash. Only other (dead) workers' jobs are reclaimed.
        own_worker=getattr(self._worker,'worker_id',None)
        for job in await app.job_manager.get_stalled_jobs(seconds_since_heartbeat=30):
            if own_worker is not None and getattr(job,'worker_id',None)==own_worker:
                continue
            if job.task_name=='vault.wake':
                # A wake lost with its process holds the conversation's wake lock: close it and ask
                # again. The new wake re-reads what changed, so nothing is lost or repeated.
                await app.job_manager.finish_job(job,status=procrastinate.jobs.Status.FAILED,delete_job=False)
                kwargs=job.task_kwargs
                try:
                    self.request_wake(kwargs['user_id'],kwargs['workspace_id'],kwargs['conversation_id'])
                except Exception as exc:
                    logging.getLogger(__name__).warning("coordinator_wake_request_failed error=%s", type(exc).__name__)
                count+=1
                continue
            if job.task_name!='vault.work':
                continue
            work_id=job.task_kwargs['work_id']
            with self._repo._connect() as connection,connection.cursor() as cursor:
                cursor.execute('SELECT * FROM vault_private.vault_background_work WHERE work_id=%s',(work_id,))
                row=cursor.fetchone()
                if row is not None:
                    self._repo._work(cursor,self._scope(row),cancelling=True)
                    if row['state']=='running':
                        cursor.execute("UPDATE vault_private.vault_background_work SET state='unknown',updated_at=now() WHERE work_id=%s",(work_id,))
                        cursor.execute("""UPDATE vault_private.vault_background_runs SET state='failed',
                            attempt_generation=attempt_generation+1,failure_code='stalled_outcome_unknown',updated_at=now()
                            WHERE work_id=%s""",(work_id,))
                        if row['worker_id']:
                            cursor.execute("UPDATE vault_private.vault_background_workers SET status='idle',updated_at=now() WHERE worker_id=%s AND generation=%s AND status='active'",
                                           (row['worker_id'],row['worker_generation']))
            # Reclaim the package claim; unknown work is then a no-op. Only
            # explicit domain reconciliation can authorize another effect.
            delay=min(60,2**min(job.attempts,5))
            await app.job_manager.retry_job(job,retry_at=datetime.now(timezone.utc)+timedelta(seconds=delay))
            count+=1
        return count

    def start(self):
        with self._lock:
            if self._thread is not None and self._thread.is_alive(): return
            self._failure=None
            self._ready.clear()
            self._stop_requested.clear()
            self._thread=Thread(target=self._thread_main,name='vault-background-durable',daemon=True)
            self._thread.start()
        if not self._ready.wait(5):
            raise RuntimeError('Durable worker startup timed out')
        if self._failure: raise RuntimeError('Durable worker startup failed') from self._failure

    def _thread_main(self):
        try: asyncio.run(self._serve())
        except Exception as exc:
            self._failure=exc
            self._ready.set()

    async def _serve(self):
        app=procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=self._dsn))
        self._register(app)
        async with app.open_async():
            self._worker=None   # startup: every stalled job belongs to a previous process
            await self.reconcile_stalled(app)
            self.resume_decided()
            self._worker=Worker(app,concurrency=4,install_signal_handlers=False,shutdown_graceful_timeout=3,
                                fetch_job_polling_interval=0.5,abort_job_polling_interval=0.5)
            task=asyncio.create_task(self._worker.run())
            await asyncio.sleep(0)
            self._ready.set()
            if self._stop_requested.is_set(): self._worker.stop()
            try:
                last_tick=0.0
                last_checkin=0.0
                last_reconcile=monotonic()
                while not task.done():
                    # 15 s keeps a one-time "in ten minutes" request close to its saved time.
                    if self._routines is not None and (monotonic()-last_tick)>=ROUTINE_TICK_SECONDS:
                        try:
                            self._routines.tick(datetime.now(timezone.utc))
                        except Exception as exc:
                            logging.getLogger(__name__).warning("routine_tick_failed error=%s", type(exc).__name__)
                        last_tick=monotonic()
                    if self._checkins is not None and (monotonic()-last_checkin)>=3600.0:
                        try:
                            await asyncio.to_thread(self._checkins, datetime.now(timezone.utc))
                        except Exception:
                            logging.getLogger(__name__).warning("coordinator_checkins_failed")
                        last_checkin=monotonic()
                    done,_=await asyncio.wait({task},timeout=5)
                    if not done and (monotonic()-last_reconcile)>=10.0:
                        last_reconcile=monotonic()
                        await self.reconcile_stalled(app)
                        self.resume_decided()
                await task
            finally:
                self._worker.stop()
                await task

    def stop(self,*,timeout=5):
        self._stop_requested.set()
        if self._worker is not None: self._worker.stop()
        if self._thread is not None:
            self._thread.join(timeout)
            if self._thread.is_alive(): raise RuntimeError('Durable worker did not stop')

    def health(self):
        return {'state':'degraded' if self._failure else ('running' if self._thread and self._thread.is_alive() else 'stopped')}
