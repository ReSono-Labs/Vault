"""Durable dispatch using real PostgreSQL and package jobs; no model/network effects."""
import asyncio
import importlib
import importlib.util

import psycopg
import pytest

from tests.support.background_coordination import prepare
from app.vault_runtime.background_agent.coordination_contracts import ExecutionOutcome, WorkState, WorkScope
from app.vault_runtime.background_agent.errors import BackgroundRunAuthorizationError, BackgroundRunConflictError
from tests.support.background_jobs import ready, enqueue
from tests.support.legacy_runs import insert_legacy_run
from app.vault_runtime.background_agent.jobs import admission_available as module_admission


@pytest.fixture
def jobs(context):
    assert importlib.util.find_spec('app.vault_runtime.background_agent.jobs') is not None, 'Missing durable dispatch'
    module = importlib.import_module('app.vault_runtime.background_agent.jobs')
    async def execute(attempt):
        return ExecutionOutcome(WorkState.COMPLETED, output={'summary': 'checked'})
    value = module.BackgroundJobs(database_url=context[0], executor=execute)
    value.ensure_schema()
    yield value
    value.stop()
    with psycopg.connect(context[0]) as connection:
        connection.execute('DROP SCHEMA IF EXISTS vault_background_queue CASCADE')


def test_work_and_job_are_atomic_and_duplicate_delivery_is_harmless(context, jobs):
    work = ready(context)
    with psycopg.connect(context[0]) as connection:
        jobs.enqueue(connection, work)
        connection.rollback()
    with psycopg.connect(context[0]) as connection:
        assert connection.execute('SELECT state FROM vault_private.vault_background_work WHERE work_id=%s',(work,)).fetchone()[0]=='ready'
        assert connection.execute('SELECT count(*) FROM vault_background_queue.procrastinate_jobs').fetchone()[0]==0
    first=enqueue(context,jobs,work)
    assert enqueue(context,jobs,work)==first
    attempt=jobs.claim(work)
    assert attempt is not None
    assert jobs.claim(work) is None
    assert jobs.finish(attempt,ExecutionOutcome(WorkState.COMPLETED,output={'result':'once'}))
    assert not jobs.finish(attempt,ExecutionOutcome(WorkState.COMPLETED,output={'result':'duplicate'}))
    with psycopg.connect(context[0]) as connection:
        assert connection.execute('SELECT args FROM vault_background_queue.procrastinate_jobs WHERE id=%s',(first,)).fetchone()[0]=={'work_id':work}


def test_waiting_releases_slot_and_stale_attempt_cannot_write(context,jobs):
    work=ready(context)
    enqueue(context,jobs,work)
    old=jobs.claim(work)
    assert jobs.finish(old,ExecutionOutcome(WorkState.WAITING_APPROVAL,checkpoint={'version':1},pending_action_id='pending'))
    with psycopg.connect(context[0]) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_background_runs WHERE state IN ('running','reviewing','repairing')").fetchone()[0]==0
        connection.execute("UPDATE vault_private.vault_background_work SET state='ready' WHERE work_id=%s",(work,))
    enqueue(context,jobs,work)
    current=jobs.claim(work)
    assert current.generation>old.generation
    with pytest.raises(BackgroundRunAuthorizationError):
        jobs.validate_attempt(old)
    assert not jobs.finish(old,ExecutionOutcome(WorkState.COMPLETED,output={}))
    jobs.validate_attempt(current)


def test_admission_is_two_per_user_four_total_and_counts_legacy(context,jobs):
    _m,_repo,_owner,legacy=prepare(context,'legacy')
    principal=context[1]
    keys=dict(user_id=principal.user_id,workspace_id=principal.workspace_id,local_session_id=principal.session_id)
    insert_legacy_run(context[0],**keys,request=legacy.request,state='running')
    works=[ready(context,str(n)) for n in range(3)]
    others=[ready(context,'other'+str(n),context[2]) for n in range(2)]
    for work in works+others: enqueue(context,jobs,work)
    assert jobs.claim(works[0]) is not None
    assert jobs.claim(works[1]) is None
    assert jobs.claim(works[2]) is None
    assert jobs.claim(others[0]) is not None
    assert jobs.claim(others[1]) is not None
    with psycopg.connect(context[0]) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_background_runs WHERE state='running'").fetchone()[0]==4
    with psycopg.connect(context[0]) as connection, connection.cursor() as cursor:
        assert not module_admission(cursor,principal.user_id)
        assert not module_admission(cursor,'nobody-else')


def test_cancel_fences_active_attempt_and_cancels_package_job(context,jobs):
    work=ready(context)
    job_id=enqueue(context,jobs,work)
    attempt=jobs.claim(work)
    with psycopg.connect(context[0]) as connection: jobs.cancel(connection,work)
    with pytest.raises(BackgroundRunAuthorizationError): jobs.validate_attempt(attempt)
    assert not jobs.finish(attempt,ExecutionOutcome(WorkState.COMPLETED,output={}))
    with psycopg.connect(context[0]) as connection:
        assert connection.execute('SELECT status FROM vault_background_queue.procrastinate_jobs WHERE id=%s',(job_id,)).fetchone()[0]=='cancelled'


def test_package_worker_executes_through_injected_adapter(context,jobs):
    work=ready(context)
    enqueue(context,jobs,work)
    asyncio.run(jobs.run_pending())
    with psycopg.connect(context[0]) as connection:
        assert connection.execute('SELECT state,result_json FROM vault_private.vault_background_work WHERE work_id=%s',(work,)).fetchone()==('completed',{'summary':'checked'})


def test_stalled_claim_is_fenced_without_repeating_unknown_effect(context,jobs):
    import procrastinate
    async def scenario():
        work=ready(context)
        job_id=enqueue(context,jobs,work)
        app=procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=jobs._dsn))
        async with app.open_async():
            worker_id=await app.job_manager.register_worker()
            claimed=await app.job_manager.fetch_job(queues=None,worker_id=worker_id)
            assert claimed.id==job_id
            attempt=jobs.claim(work)
            with psycopg.connect(jobs._dsn) as connection:
                connection.execute("UPDATE procrastinate_workers SET last_heartbeat=now()-interval '60 seconds' WHERE id=%s",(worker_id,))
            assert await jobs.reconcile_stalled(app)==1
            with pytest.raises(BackgroundRunAuthorizationError): jobs.validate_attempt(attempt)
            with psycopg.connect(context[0]) as connection:
                assert connection.execute('SELECT state FROM vault_private.vault_background_work WHERE work_id=%s',(work,)).fetchone()[0]=='unknown'
        await jobs.run_pending()
    asyncio.run(scenario())


def test_slow_run_on_this_live_worker_is_not_reclaimed(context,jobs):
    """A long tool call can delay this worker's heartbeat past 30 s; that is not a crash."""
    import procrastinate
    from types import SimpleNamespace
    async def scenario():
        work=ready(context)
        job_id=enqueue(context,jobs,work)
        app=procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=jobs._dsn))
        async with app.open_async():
            worker_id=await app.job_manager.register_worker()
            claimed=await app.job_manager.fetch_job(queues=None,worker_id=worker_id)
            assert claimed.id==job_id
            attempt=jobs.claim(work)
            with psycopg.connect(jobs._dsn) as connection:
                connection.execute("UPDATE procrastinate_workers SET last_heartbeat=now()-interval '60 seconds' WHERE id=%s",(worker_id,))
            jobs._worker=SimpleNamespace(worker_id=worker_id)
            assert await jobs.reconcile_stalled(app)==0
            jobs.validate_attempt(attempt)
            with psycopg.connect(context[0]) as connection:
                assert connection.execute('SELECT state FROM vault_private.vault_background_work WHERE work_id=%s',(work,)).fetchone()[0]=='running'
            # Another worker that stopped sending heartbeats is still reclaimed.
            jobs._worker=SimpleNamespace(worker_id=worker_id+1000)
            assert await jobs.reconcile_stalled(app)==1
            with pytest.raises(BackgroundRunAuthorizationError): jobs.validate_attempt(attempt)
            jobs._worker=None
    asyncio.run(scenario())


def test_durable_budget_is_not_reset_by_wait_and_resume(context,jobs):
    work=ready(context)
    enqueue(context,jobs,work)
    first=jobs.claim(work)
    jobs.debit(first,tool_calls=2,model_turns=3,active_seconds=4)
    jobs.finish(first,ExecutionOutcome(WorkState.WAITING_INPUT,checkpoint={'safe':'saved'}))
    with psycopg.connect(context[0]) as connection:
        connection.execute("UPDATE vault_private.vault_background_work SET state='ready' WHERE work_id=%s",(work,))
    enqueue(context,jobs,work)
    second=jobs.claim(work)
    assert (second.tool_calls,second.model_turns,second.active_seconds)==(2,3,4)
    with pytest.raises(BackgroundRunAuthorizationError): jobs.debit(first,tool_calls=1)
    with pytest.raises(BackgroundRunAuthorizationError): jobs.debit(second,tool_calls=500)


def test_supervised_worker_starts_once_stops_and_reports_failure(context,jobs):
    jobs.start()
    thread=jobs._thread
    jobs.start()
    assert jobs._thread is thread
    assert jobs.health()['state']=='running'
    jobs.stop()
    assert jobs.health()['state']=='stopped'


def test_specialist_cannot_accept_second_live_assignment(context,jobs):
    from app.vault_runtime.background_agent.worker_repository import WorkerRepository
    from app.vault_runtime.background_agent.coordination_contracts import WorkerSpec
    from tests.support.background_authority import approve_fixture
    m,repo,owner,_request=prepare(context)
    workers=WorkerRepository(database_url=context[0])
    proposal=workers.propose(owner,WorkerSpec('research','Research','Check sources',(),{}))
    worker=workers.create_from_approval(approve_fixture(context,proposal))
    first=ready(context,'first')
    second=ready(context,'second')
    repo.assign(WorkScope(owner.user_id,owner.workspace_id,first,1,None,None,None),worker)
    with pytest.raises(BackgroundRunConflictError):
        repo.assign(WorkScope(owner.user_id,owner.workspace_id,second,1,None,None,None),worker)


def test_aware_scheduling_and_dict_row_transaction_are_supported(context,jobs):
    from datetime import datetime,timedelta,timezone
    from psycopg.rows import dict_row
    work=ready(context)
    with psycopg.connect(context[0],row_factory=dict_row) as connection:
        job_id=jobs.enqueue(connection,work,datetime.now(timezone.utc)+timedelta(minutes=1))
        assert connection.execute('SHOW search_path').fetchone()['search_path']=='"$user", public'
    assert job_id>0
