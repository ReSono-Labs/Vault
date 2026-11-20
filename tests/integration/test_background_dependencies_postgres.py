"""Task 0 proofs against real package/psycopg APIs in the isolated test database."""
from __future__ import annotations

import asyncio
import os
from queue import SimpleQueue
from threading import Thread, get_ident

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
import pytest

procrastinate = pytest.importorskip("procrastinate")


@pytest.fixture()
def proof_dsn():
    raw = os.environ.get("VAULT_TEST_DATABASE_URL")
    if not raw:
        pytest.skip("Isolated VAULT_TEST_DATABASE_URL is required")
    assert conninfo_to_dict(raw)["dbname"] == "resono_vault_test"
    with psycopg.connect(raw) as connection:
        connection.execute("DROP SCHEMA IF EXISTS background_proof CASCADE")
        connection.execute("CREATE SCHEMA background_proof")
    dsn = make_conninfo(raw, options="-csearch_path=background_proof,public")
    app = procrastinate.App(connector=procrastinate.SyncPsycopgConnector(conninfo=dsn))
    with app.open():
        app.schema_manager.apply_schema()
    try:
        yield dsn
    finally:
        with psycopg.connect(raw) as connection:
            connection.execute("DROP SCHEMA background_proof CASCADE")


@pytest.mark.parametrize("commit", [False, True])
def test_work_and_job_commit_or_rollback_together(proof_dsn, commit):
    app = procrastinate.App(connector=procrastinate.SyncPsycopgConnector(conninfo=proof_dsn))

    @app.task(name="proof.work")
    def work(work_id):
        raise AssertionError("Transaction proof must not execute the job")

    with app.open():
        with psycopg.connect(proof_dsn) as connection:
            connection.execute("CREATE TABLE proof_work (id text PRIMARY KEY)")
        with psycopg.connect(proof_dsn) as connection:
            connection.execute("INSERT INTO proof_work VALUES ('work-1')")
            work.configure(connection=connection).defer(work_id="work-1")
            if not commit:
                connection.rollback()
        with psycopg.connect(proof_dsn) as connection:
            assert connection.execute("SELECT count(*) FROM proof_work").fetchone()[0] == int(commit)
            assert connection.execute("SELECT count(*) FROM procrastinate_jobs").fetchone()[0] == int(commit)


def test_running_cancel_releases_job(proof_dsn):
    async def scenario():
        app = procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=proof_dsn))
        started, released = asyncio.Event(), asyncio.Event()
        completed = []

        @app.task(name="proof.wait")
        async def wait():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                released.set()

        @app.task(name="proof.next")
        async def next_job():
            completed.append("next")

        async with app.open_async():
            job_id = await wait.defer_async()
            await next_job.defer_async()
            running = asyncio.create_task(app.run_worker_async(
                wait=False, concurrency=1, install_signal_handlers=False,
                listen_notify=False, abort_job_polling_interval=0.02,
            ))
            try:
                await asyncio.wait_for(started.wait(), 5)
                await app.job_manager.cancel_job_by_id_async(job_id, abort=True)
                await asyncio.wait_for(running, 5)
                assert released.is_set()
                assert completed == ["next"]
                assert (await app.job_manager.get_job_status_async(job_id)).value == "aborted"
            finally:
                if not running.done():
                    running.cancel()
                    await asyncio.gather(running, return_exceptions=True)

    asyncio.run(scenario())


def test_stalled_job_is_reconciled(proof_dsn):
    async def scenario():
        app = procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=proof_dsn))
        effects = []

        @app.task(name="proof.recover")
        async def recover():
            effects.append("recovered")

        async with app.open_async():
            job_id = await recover.defer_async()
            abandoned_worker = await app.job_manager.register_worker()
            claimed = await app.job_manager.fetch_job(queues=None, worker_id=abandoned_worker)
            assert claimed is not None and claimed.id == job_id
            # Deterministic passage of time after an abandoned claim: no timing sleeps.
            with psycopg.connect(proof_dsn) as connection:
                connection.execute(
                    "UPDATE procrastinate_workers SET last_heartbeat=now()-interval '60 seconds' WHERE id=%s",
                    (abandoned_worker,),
                )
            stalled = list(await app.job_manager.get_stalled_jobs(seconds_since_heartbeat=30))
            assert [job.id for job in stalled] == [job_id]
            await app.job_manager.retry_job(stalled[0])
            await app.run_worker_async(wait=False, install_signal_handlers=False, listen_notify=False)
            assert (await app.job_manager.get_job_status_async(job_id)).value == "succeeded"
            assert effects == ["recovered"]

    asyncio.run(scenario())


def test_worker_starts_and_stops_in_background_thread_without_owning_process_signals(proof_dsn):
    result = SimpleQueue()
    parent_thread = get_ident()

    def thread_main():
        async def scenario():
            app = procrastinate.App(connector=procrastinate.PsycopgConnector(conninfo=proof_dsn))
            thread_ids = []

            @app.task(name="proof.thread")
            async def mark():
                thread_ids.append(get_ident())

            async with app.open_async():
                job_id = await mark.defer_async()
                await app.run_worker_async(wait=False, install_signal_handlers=False, listen_notify=False)
                assert (await app.job_manager.get_job_status_async(job_id)).value == "succeeded"
            return thread_ids

        try:
            result.put(asyncio.run(scenario()))
        except BaseException as exc:
            result.put(exc)

    thread = Thread(target=thread_main, daemon=True)
    thread.start()
    thread.join(timeout=10)
    assert not thread.is_alive(), "Embedded worker did not stop"
    observed = result.get_nowait()
    if isinstance(observed, BaseException):
        raise observed
    assert len(observed) == 1 and observed[0] != parent_thread
