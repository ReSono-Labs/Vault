from dataclasses import replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import psycopg
from psycopg.types.json import Jsonb
import pytest

from tests.support.background_coordination import prepare
from app.vault_runtime.background_agent.errors import BackgroundRunAuthorizationError, BackgroundRunConflictError
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.voice.repository import VoiceSessionRepository
from app.vault_runtime.voice.tools import LocalToolAuthority
from tests.support.background_authority import components, standing_work, approve_fixture


def test_standing_grant_works_without_browser_and_revocation_stops_it(context):
    _m, _repo, _owner, scope, authority, _workers = standing_work(context)
    with psycopg.connect(context[0]) as connection:
        connection.execute("UPDATE vault_private.local_sessions SET expires_at=now()-interval '1 second'")
    authority.validate(scope, "proof_read", {})
    with psycopg.connect(context[0]) as connection:
        connection.execute("UPDATE vault_private.vault_background_execution_grants SET status='revoked'")
    with pytest.raises(BackgroundRunAuthorizationError):
        authority.validate(scope, "proof_read", {})


@pytest.mark.parametrize("change", [
    "UPDATE vault_private.vault_background_execution_grants SET expires_at=now()-interval '1 second'",
    "UPDATE vault_private.local_users SET status='locked'",
    "UPDATE vault_private.local_workspaces SET status='archived'",
    "UPDATE vault_private.local_workspace_memberships SET status='revoked'",
])
def test_current_identity_and_grant_state_is_rechecked(context, change):
    _m, _repo, _owner, scope, authority, _workers = standing_work(context)
    with psycopg.connect(context[0]) as connection:
        connection.execute(change)
    with pytest.raises(BackgroundRunAuthorizationError):
        authority.validate(scope, "proof_read", {})


def test_wrong_scope_expired_session_and_ungranted_tool_are_denied(context):
    m, repo, owner, request, authority, _workers = components(context)
    work_id = repo.create_work(owner, request, "session-work")
    scope = m.WorkScope(owner.user_id, owner.workspace_id, work_id, 1, None, None, None)
    with psycopg.connect(context[0]) as connection:
        connection.execute("UPDATE vault_private.local_sessions SET expires_at=now()-interval '1 second'")
    with pytest.raises(BackgroundRunAuthorizationError):
        authority.validate(scope)


def test_resource_bounds_and_live_vault_grants_are_both_required(context):
    m, _repo, owner, scope, authority, _workers = standing_work(context, {
        "tool_names": ["proof_read"], "resource_policy": {"tool_arguments": {"proof_read": {"folder": ["approved"]}}},
    })
    VoiceSessionRepository(database_url=context[0]).ensure_schema()
    local = LocalToolAuthority(database_url=context[0], background_authority=authority)
    local.set_grant(actor_user_id=owner.user_id, workspace_id=owner.workspace_id, tool_name="proof_read",
                    effect_class="read", voice_enabled=False, background_enabled=True, user_id=owner.user_id)
    effects = []
    catalog = ToolCatalog(authorizer=local.authorize, background_authorizer=local.authorize_background)
    catalog.register(ToolDefinition(tool_id="builtin.proof-read.v1", name="proof_read", description="Read approved fixture",
        input_schema={"type": "object", "properties": {"folder": {"type": "string"}}, "required": ["folder"], "additionalProperties": False},
        handler=lambda _context, arguments: (effects.append(arguments) or ToolInvocationResult("ok"))))
    ctx = ToolInvocationContext(agent=AgentKind.BACKGROUND, user_id=owner.user_id, workspace_id=owner.workspace_id,
                                tool_call_id="call", local_session_id=None, background_scope=scope)
    assert catalog.invoke("proof_read", {"folder": "other"}, context=ctx).is_error
    assert catalog.invoke("proof_read", {"folder": "approved"}, context=ctx).text == "ok"
    local.set_grant(actor_user_id=owner.user_id, workspace_id=owner.workspace_id, tool_name="proof_read",
                    effect_class="read", voice_enabled=False, background_enabled=False, user_id=owner.user_id)
    assert catalog.invoke("proof_read", {"folder": "approved"}, context=ctx).is_error
    assert effects == [{"folder": "approved"}]
    with pytest.raises(BackgroundRunAuthorizationError):
        authority.validate(scope, "ungranted", {})
    foreign = context[2]
    with pytest.raises(BackgroundRunAuthorizationError):
        authority.validate(replace(scope, user_id=foreign.user_id, workspace_id=foreign.workspace_id))


def test_worker_creation_requires_exact_approved_receipt_and_is_idempotent(context):
    m, _repo, owner, _request, _authority, workers = components(context)
    spec = m.WorkerSpec("research", "Research approved sources", "Return checked results", ("proof_read",), {})
    proposal = workers.propose(owner, spec)
    fake = m.ApprovalDecision(proposal.action_id, proposal.action_hash, "allow_once", owner.user_id,
                             owner.workspace_id, "browser", context[1].session_id, "decision")
    with pytest.raises(BackgroundRunAuthorizationError):
        workers.create_from_approval(fake)
    receipt = approve_fixture(context, proposal)
    worker_id = workers.create_from_approval(receipt)
    assert workers.create_from_approval(receipt) == worker_id
    assert workers.get(owner, worker_id) == spec
    with psycopg.connect(context[0]) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_background_workers").fetchone()[0] == 1
    generation = workers.set_state(owner, worker_id, 1, "paused")
    assert generation == 2
    with pytest.raises(BackgroundRunConflictError):
        workers.set_state(owner, worker_id, 1, "idle")


def test_changed_approved_spec_and_forged_grant_decision_do_not_create_authority(context):
    m, _repo, owner, _request, authority, workers = components(context)
    proposal = workers.propose(owner, m.WorkerSpec("research", "Research", "Read sources", ("proof_read",), {}))
    decision = approve_fixture(context, proposal)
    with psycopg.connect(context[0]) as connection:
        connection.execute("UPDATE vault_private.vault_background_actions SET arguments_json=%s WHERE action_id=%s",
                           (Jsonb({"purpose": "Widened purpose"}), proposal.action_id))
    with pytest.raises(BackgroundRunAuthorizationError):
        workers.create_from_approval(decision)
    with pytest.raises(BackgroundRunAuthorizationError):
        authority.grant(context[1], {"purpose": "Widened purpose", "tool_names": ["proof_read"], "resource_policy": {}}, decision)


def test_explicit_grant_creation_is_bound_to_approved_policy_and_revocable(context):
    m, _repo, owner, _request, authority, _workers = components(context)
    policy = {"purpose": "Prepare approved briefs", "tool_names": ["proof_read"], "resource_policy": {}}
    digest = sha256(json.dumps({"kind": "execution_grant", "arguments": policy},
                              sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    expires = datetime.now(timezone.utc) + timedelta(minutes=10)
    prepared = m.PreparedAction("grant-action", digest, None, "execution_grant", "Enable preparation", "Read only", expires)
    with psycopg.connect(context[0]) as connection:
        connection.execute("""INSERT INTO vault_private.vault_background_actions
            (action_id,user_id,workspace_id,kind,action_hash,arguments_json,title,detail,expires_at,operation_key)
            VALUES (%s,%s,%s,'execution_grant',%s,%s,'Enable','Read only',%s,'grant-proof')""",
            (prepared.action_id, owner.user_id, owner.workspace_id, digest, Jsonb(policy), expires))
    decision = approve_fixture(context, prepared)
    grant_id = authority.grant(context[1], policy, decision)
    assert authority.grant(context[1], policy, decision) == grant_id
    authority.revoke(context[1], grant_id)
    with psycopg.connect(context[0]) as connection:
        assert connection.execute("SELECT status FROM vault_private.vault_background_execution_grants WHERE grant_id=%s",
                                  (grant_id,)).fetchone()[0] == "revoked"


def test_account_removal_erases_coordination_without_affecting_owner(context):
    from app.vault_runtime.local_identity.repository import LocalIdentityRepository
    m, repo, owner, request, _authority, _workers = components(context)
    secondary = context[2]
    secondary_scope = m.OwnerScope(secondary.user_id, secondary.workspace_id)
    secondary_request = replace(request, local_session_id=secondary.session_id)
    repo.create_work(secondary_scope, secondary_request, "secondary-work")
    owner_work = repo.create_work(owner, request, "owner-work")
    LocalIdentityRepository(database_url=context[0]).owner_remove_user(user_id=secondary.user_id)
    with psycopg.connect(context[0]) as connection:
        assert connection.execute("SELECT count(*) FROM vault_private.vault_background_work WHERE user_id=%s",
                                  (secondary.user_id,)).fetchone()[0] == 0
    assert repo.get(owner, owner_work)["work_id"] == owner_work


def test_reset_invalidates_assignment_and_erases_private_checkpoint(context):
    m, repo, owner, request, authority, workers = components(context)
    proposal = workers.propose(owner, m.WorkerSpec("research", "Research", "Check sources", ("proof_read",), {}))
    worker_id = workers.create_from_approval(approve_fixture(context, proposal))
    work_id = repo.create_work(owner, request, "assigned")
    unassigned = m.WorkScope(owner.user_id, owner.workspace_id, work_id, 1, None, None, None)
    session_id = repo.assign(unassigned, worker_id)
    assigned = replace(unassigned, worker_id=worker_id, worker_generation=1)
    with psycopg.connect(context[0]) as connection:
        connection.execute("UPDATE vault_private.vault_background_sessions SET checkpoint_json=%s,history_json=%s WHERE session_id=%s",
                           (Jsonb({"private": "checkpoint"}), Jsonb(["private history"]), session_id))
    authority.validate(assigned)
    assert workers.set_state(owner, worker_id, 1, "reset") == 2
    with pytest.raises(BackgroundRunAuthorizationError):
        authority.validate(assigned)
    with psycopg.connect(context[0]) as connection:
        assert connection.execute("SELECT checkpoint_json,history_json FROM vault_private.vault_background_sessions WHERE session_id=%s",
                                  (session_id,)).fetchone() == (None, [])


def test_account_removal_erases_tasks_and_pending_task_actions_without_affecting_owner(context):
    """The account row is kept as a tombstone (status deleted), so the Tasks tables' ON DELETE
    CASCADE never fires; the removal itself must erase them (HANDOFF item 9)."""
    from app.vault_runtime.local_identity.repository import LocalIdentityRepository
    from app.vault_runtime.tasks.repository import TaskRepository
    m, repo, owner, request, _authority, _workers = components(context)
    TaskRepository(database_url=context[0]).ensure_schema()
    secondary = context[2]
    secondary_work = repo.create_work(m.OwnerScope(secondary.user_id, secondary.workspace_id),
                                      replace(request, local_session_id=secondary.session_id), "secondary-work")
    with psycopg.connect(context[0]) as connection:
        # Including the secondary user's Tasks in the owner's shared workspace, which no workspace
        # deletion removes.
        for user, workspace, task in ((secondary.user_id, secondary.workspace_id, "secondary-task"),
                                      (secondary.user_id, owner.workspace_id, "secondary-shared-task"),
                                      (owner.user_id, owner.workspace_id, "owner-task")):
            connection.execute("""INSERT INTO vault_private.vault_tasks (task_id,user_id,workspace_id,task_text,status)
                VALUES (%s,%s,%s,'Private text','open')""", (task, user, workspace))
            connection.execute("""INSERT INTO vault_private.vault_task_pending_actions
                (action_id,user_id,workspace_id,task_id,operation,payload_json,content_hash,state,voice_session_id,
                 tool_call_id,expires_at,background_work_id,background_intent_version)
                VALUES (%s,%s,%s,%s,'edit','{}','h','pending_review',NULL,'call',now()+interval '10 minutes',%s,1)""",
                (f"pending-{task}", user, workspace, task, secondary_work if task == "secondary-task" else None))
    with psycopg.connect(context[0]) as connection:
        connection.execute("""INSERT INTO vault_private.local_workspace_memberships (membership_id,workspace_id,user_id,membership_type)
            VALUES ('shared-membership',%s,%s,'member') ON CONFLICT DO NOTHING""", (owner.workspace_id, secondary.user_id))
    LocalIdentityRepository(database_url=context[0]).owner_remove_user(user_id=secondary.user_id)
    with psycopg.connect(context[0]) as connection:
        for table in ("vault_tasks", "vault_task_pending_actions"):
            assert connection.execute(f"SELECT count(*) FROM vault_private.{table} WHERE user_id=%s",
                                      (secondary.user_id,)).fetchone()[0] == 0
            assert connection.execute(f"SELECT count(*) FROM vault_private.{table} WHERE user_id=%s",
                                      (owner.user_id,)).fetchone()[0] == 1
