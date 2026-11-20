from __future__ import annotations

from dataclasses import replace

import psycopg
from psycopg.types.json import Jsonb
import pytest

from app.vault_runtime.background_agent.contracts import BackgroundRunState
from app.vault_runtime.background_agent.errors import BackgroundRunAuthorizationError, BackgroundRunConflictError
from tests.support.background_coordination import prepare
from tests.support.legacy_runs import insert_legacy_run


def test_work_and_observation_are_scoped_and_idempotent(context):
    m, repo, owner, request = prepare(context)
    assert repo.observe(owner, "chat", "turn-1", {"text": "brief"}) == repo.observe(owner, "chat", "turn-1", {"text": "brief"})
    work_id = repo.create_work(owner, request, "chat:turn-1")
    assert repo.create_work(owner, request, "chat:turn-1") == work_id
    with pytest.raises(BackgroundRunConflictError):
        repo.create_work(owner, replace(request, request=replace(request.request, objective="Changed")), "chat:turn-1")
    other = context[2]
    with pytest.raises(BackgroundRunAuthorizationError):
        repo.get(m.OwnerScope(other.user_id, other.workspace_id), work_id)


def test_cross_user_worker_and_session_links_are_rejected(context):
    m, repo, owner, request = prepare(context)
    url, _owner, other, _runs = context
    work_id = repo.create_work(owner, request, "chat:turn-1")
    with psycopg.connect(url) as connection:
        connection.execute("""INSERT INTO vault_private.vault_background_workers
            (worker_id,user_id,workspace_id,role_key,spec_json,spec_hash)
            VALUES ('foreign-worker',%s,%s,'research',%s,%s)""",
            (other.user_id, other.workspace_id, Jsonb({"purpose": "Other user's work"}), "a" * 64))
    work = m.WorkScope(owner.user_id, owner.workspace_id, work_id, 1, None, None, None)
    with pytest.raises(BackgroundRunAuthorizationError):
        repo.assign(work, "foreign-worker")
    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with psycopg.connect(url) as connection:
            connection.execute("""INSERT INTO vault_private.vault_background_sessions
                (session_id,user_id,workspace_id,worker_id,work_id,worker_generation,intent_version)
                VALUES ('session',%s,%s,'foreign-worker',%s,1,1)""", (owner.user_id, owner.workspace_id, work_id))


def test_assignment_uses_one_private_session_and_pins_worker_generation(context):
    m, repo, owner, request = prepare(context)
    url = context[0]
    with psycopg.connect(url) as connection:
        connection.execute("""INSERT INTO vault_private.vault_background_workers
            (worker_id,user_id,workspace_id,role_key,spec_json,spec_hash)
            VALUES ('worker',%s,%s,'research',%s,%s)""",
            (owner.user_id, owner.workspace_id, Jsonb({"purpose": "Approved research fixture"}), "b" * 64))
    work_id = repo.create_work(owner, request, "chat:turn-1")
    initial = m.WorkScope(owner.user_id, owner.workspace_id, work_id, 1, None, None, None)
    session = repo.assign(initial, "worker")
    assert repo.assign(initial, "worker") == session
    row = repo.get(owner, work_id)
    assert (row["worker_id"], row["worker_generation"]) == ("worker", 1)
    with psycopg.connect(url) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_background_sessions").fetchone()[0] == 1
        connection.execute("UPDATE vault_private.vault_background_workers SET generation=2 WHERE worker_id='worker'")
    stale = m.WorkScope(owner.user_id, owner.workspace_id, work_id, 1, "worker", 1, None)
    with pytest.raises(BackgroundRunAuthorizationError):
        repo.transition(stale, m.WorkState.PROPOSED, m.WorkState.READY, {})


def test_assignment_never_reuses_a_different_specialists_session(context):
    m, repo, owner, request = prepare(context)
    work_id = repo.create_work(owner, request, "chat:turn-1")
    with psycopg.connect(context[0]) as connection:
        for worker_id in ("research", "documents"):
            connection.execute("""INSERT INTO vault_private.vault_background_workers
                (worker_id,user_id,workspace_id,role_key,spec_json,spec_hash)
                VALUES (%s,%s,%s,%s,%s,%s)""", (worker_id, owner.user_id, owner.workspace_id,
                worker_id, Jsonb({"purpose": worker_id}), "a" * 64))
        connection.execute("""INSERT INTO vault_private.vault_background_sessions
            (session_id,user_id,workspace_id,worker_id,work_id,worker_generation,intent_version)
            VALUES ('old-session',%s,%s,'research',%s,1,1)""", (owner.user_id, owner.workspace_id, work_id))
    scope = m.WorkScope(owner.user_id, owner.workspace_id, work_id, 1, None, None, None)
    with pytest.raises(BackgroundRunConflictError):
        repo.assign(scope, "documents")


def test_state_compare_and_swap_and_terminal_result_dedup(context):
    m, repo, owner, request = prepare(context)
    work_id = repo.create_work(owner, request, "chat:turn-1")
    scope = m.WorkScope(owner.user_id, owner.workspace_id, work_id, 1, None, None, None)
    assert repo.transition(scope, m.WorkState.PROPOSED, m.WorkState.READY, {})
    assert not repo.transition(scope, m.WorkState.PROPOSED, m.WorkState.READY, {})
    with pytest.raises(ValueError):
        repo.transition(scope, m.WorkState.READY, m.WorkState.COMPLETED, {})
    assert repo.transition(scope, m.WorkState.READY, m.WorkState.QUEUED, {})
    assert repo.transition(scope, m.WorkState.QUEUED, m.WorkState.RUNNING, {})
    url, principal, _other, runs = context
    insert_legacy_run(url, user_id=principal.user_id, workspace_id=principal.workspace_id,
                      local_session_id=principal.session_id, request=request.request)
    with psycopg.connect(url) as connection:
        connection.execute("UPDATE vault_private.vault_background_runs SET work_id=%s WHERE run_id=%s", (work_id, request.request.run_id))
    outcome = m.ExecutionOutcome(m.WorkState.COMPLETED, output={"summary": "Checked brief"})
    assert repo.accept_result(scope, request.request.run_id, outcome)
    assert not repo.accept_result(scope, request.request.run_id, outcome)
    assert repo.get(owner, work_id)["state"] == "completed"


def test_additive_schema_preserves_old_history_and_excludes_new_work_from_legacy_recovery(context):
    url, principal, _other, runs = context
    kwargs = dict(user_id=principal.user_id, workspace_id=principal.workspace_id, local_session_id=principal.session_id)
    _m, repo, owner, request = prepare(context)
    legacy = replace(request.request, run_id="legacy")
    insert_legacy_run(url, **kwargs, request=legacy, state="queued")
    insert_legacy_run(url, **kwargs, request=request.request, state="queued")
    work_id = repo.create_work(owner, request, "chat:turn-1")
    with psycopg.connect(url) as connection:
        connection.execute("UPDATE vault_private.vault_background_runs SET work_id=%s WHERE run_id=%s", (work_id, request.request.run_id))
    repo.ensure_schema()
    assert runs.recover_interrupted() == 1
    assert runs.get_in_workspace(**kwargs, run_id="legacy").failure_code == "runtime_interrupted"
    assert runs.get_in_workspace(**kwargs, run_id=request.request.run_id).state is BackgroundRunState.QUEUED
    assert runs.get_in_workspace(**kwargs, run_id="legacy").request.payload() == legacy.payload()
    events = runs.list_events(**kwargs, run_id="legacy")
    assert [(event.event_type, event.state, event.detail) for event in events] == [
        ("recovered_as_failed", BackgroundRunState.FAILED, {"previousState": "queued"})]


def test_grantless_run_cannot_lose_its_session_authority(context):
    _m, _repo, _owner, request = prepare(context)
    url, principal, _other, runs = context
    insert_legacy_run(url, user_id=principal.user_id, workspace_id=principal.workspace_id,
                      local_session_id=principal.session_id, request=request.request)
    with pytest.raises(psycopg.errors.CheckViolation):
        with psycopg.connect(url) as connection:
            connection.execute("UPDATE vault_private.vault_background_runs SET local_session_id=NULL WHERE run_id=%s", (request.request.run_id,))
