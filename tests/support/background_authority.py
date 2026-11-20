"""Shared test helpers moved out of test modules (TST-01)."""

import importlib.util
from dataclasses import replace

import psycopg
from psycopg.types.json import Jsonb

from tests.support.background_coordination import prepare


def components(context):
    m, repo, owner, request = prepare(context)
    for name in ("authority", "worker_repository"):
        assert importlib.util.find_spec(f"app.vault_runtime.background_agent.{name}") is not None, f"Missing {name}"
    authority = importlib.import_module("app.vault_runtime.background_agent.authority").BackgroundAuthority(database_url=context[0])
    workers = importlib.import_module("app.vault_runtime.background_agent.worker_repository").WorkerRepository(database_url=context[0])
    return m, repo, owner, request, authority, workers


def standing_work(context, policy=None):
    m, repo, owner, request, authority, workers = components(context)
    policy = policy or {"tool_names": ["proof_read"], "resource_policy": {}}
    with psycopg.connect(context[0]) as connection:
        connection.execute("""INSERT INTO vault_private.vault_background_execution_grants
            (grant_id,user_id,workspace_id,purpose,policy_json) VALUES ('grant',%s,%s,'Read approved data',%s)""",
            (owner.user_id, owner.workspace_id, Jsonb(policy)))
    request = replace(request, grant_id="grant", local_session_id=None)
    work_id = repo.create_work(owner, request, "proof:work")
    scope = m.WorkScope(owner.user_id, owner.workspace_id, work_id, 1, None, None, "grant")
    for prior, after in ((m.WorkState.PROPOSED, m.WorkState.READY), (m.WorkState.READY, m.WorkState.QUEUED),
                         (m.WorkState.QUEUED, m.WorkState.RUNNING)):
        repo.transition(scope, prior, after, {})
    return m, repo, owner, scope, authority, workers


def approve_fixture(context, prepared):
    """Server-written trusted receipt until the public action service is built in Task 4."""
    m = importlib.import_module("app.vault_runtime.background_agent.coordination_contracts")
    principal = context[1]
    with psycopg.connect(context[0]) as connection:
        connection.execute("""UPDATE vault_private.vault_background_actions SET state='approved',
            actor_user_id=%s,decision_id='decision',channel='browser',channel_generation=%s WHERE action_id=%s""",
            (principal.user_id, principal.session_id, prepared.action_id))
    return m.ApprovalDecision(prepared.action_id, prepared.action_hash, "allow_once", principal.user_id,
                              principal.workspace_id, "browser", principal.session_id, "decision")
