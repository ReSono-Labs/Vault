"""Shared test helpers moved out of test modules (TST-01)."""

from dataclasses import replace

import psycopg

from app.vault_runtime.background_agent.coordination_contracts import WorkState, WorkScope
from tests.support.background_coordination import prepare


def ready(context, suffix='1', principal=None):
    m, repo, owner, request = prepare(context, 'run-'+suffix)
    if principal:
        owner = m.OwnerScope(principal.user_id, principal.workspace_id)
        request = replace(request, local_session_id=principal.session_id)
    work_id = repo.create_work(owner, request, 'job:'+suffix)
    scope = WorkScope(owner.user_id, owner.workspace_id, work_id, 1, None, None, None)
    repo.transition(scope, WorkState.PROPOSED, WorkState.READY, {})
    return work_id


def enqueue(context, jobs, work_id):
    with psycopg.connect(context[0]) as connection:
        return jobs.enqueue(connection, work_id)
