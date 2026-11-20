"""Delegated write tools go through trusted prepared actions; the model never approves (Task 4)."""
import psycopg
import pytest
from psycopg.types.json import Jsonb

from tests.support.background_authority import standing_work
from app.vault_runtime.background_agent.coordination_contracts import ApprovalDecision
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult
from app.vault_runtime.voice.repository import VoiceSessionRepository
from app.vault_runtime.voice.tools import LocalToolAuthority

TASK_TOOLS = ["tasks_list", "tasks_read", "tasks_add", "tasks_edit", "tasks_mark_completed", "tasks_remove", "tasks_confirm_action"]


class FakeCalendar:
    def __init__(self):
        self.effects = []
    def prepare(self, scope, arguments):
        return "calendar-pending"
    def version(self, scope, reference):
        return "v1"
    def validate(self, scope, reference, version):
        pass
    def execute(self, scope, reference, operation_key):
        self.effects.append(operation_key)
        return {"eventId": "event-1"}
    def reconcile(self, scope, reference, operation_key):
        return {"state": "unknown"}


def build(context, *, tool_names=None, resource_policy=None):
    from app.vault_runtime.background_agent.actions import BackgroundActions
    from app.vault_runtime.background_agent.action_bridge import BackgroundActionBridge, current_tool_authorizer
    from app.vault_runtime.background_agent.action_domains import TaskActionDomain
    from app.vault_runtime.tasks.repository import TaskRepository
    from app.vault_runtime.tasks_tools import register_tasks_tools
    names = tool_names if tool_names is not None else TASK_TOOLS + ["calendar_create"]
    _m, _repo, owner, scope, authority, _workers = standing_work(
        context, {"tool_names": names, "resource_policy": resource_policy or {}})
    VoiceSessionRepository(database_url=context[0]).ensure_schema()
    local = LocalToolAuthority(database_url=context[0], background_authority=authority)
    for name in TASK_TOOLS + ["calendar_create"]:
        local.set_grant(actor_user_id=owner.user_id, workspace_id=owner.workspace_id, tool_name=name,
                        effect_class="read" if name in {"tasks_list", "tasks_read"} else "write",
                        voice_enabled=False, background_enabled=True, user_id=owner.user_id)
    catalog = ToolCatalog(authorizer=local.authorize, background_authorizer=local.authorize_background)
    tasks = TaskRepository(database_url=context[0])
    tasks.ensure_schema()
    calendar = FakeCalendar()
    actions = BackgroundActions(database_url=context[0], domains={"tasks": TaskActionDomain(repository=tasks), "calendar": calendar},
                                authorizer=current_tool_authorizer(catalog=catalog, tool_authority=local, work_session=lambda _s: None))
    bridge = BackgroundActionBridge(actions=actions, domains=actions._domains)
    register_tasks_tools(catalog=catalog, repository=tasks, background_actions=bridge)
    # A stand-in for calendar_create's registration (its hook calls the same bridge).
    catalog.register(ToolDefinition(tool_id="builtin.calendar-create.v1", name="calendar_create", description="Calendar",
        input_schema={"type": "object", "properties": {"title": {"type": "string"}, "pendingActionId": {"type": "string"},
                      "approve": {"type": "boolean"}}, "additionalProperties": False},
        handler=lambda ctx, args: bridge.invoke(ctx, "calendar_create", args), effect_class="write",
        audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND})))
    ctx = ToolInvocationContext(agent=AgentKind.BACKGROUND, user_id=owner.user_id, workspace_id=owner.workspace_id,
                                tool_call_id="worker-call", local_session_id=None, background_scope=scope)
    return dict(catalog=catalog, bridge=bridge, actions=actions, tasks=tasks, calendar=calendar, scope=scope, ctx=ctx, owner=owner)


def owner_decides(context, payload, choice="allow_once", identifier="owner-decision"):
    principal = context[1]
    return ApprovalDecision(payload["actionId"], payload["contentHash"], choice, principal.user_id, principal.workspace_id,
                            "browser", principal.session_id, identifier)


def count(context, sql):
    with psycopg.connect(context[0]) as connection:
        return connection.execute(sql).fetchone()[0]


def task_texts(env):
    return [t.task_text for t in env["tasks"].list(user_id=env["owner"].user_id, workspace_id=env["owner"].workspace_id)]


def test_a_write_tool_prepares_and_waits_and_only_the_owners_decision_lets_it_run(context):
    env = build(context)
    prepared = env["catalog"].invoke("tasks_add", {"text": "Buy milk"}, context=env["ctx"])
    payload = prepared.structured_content
    assert not prepared.is_error and payload["status"] == "waiting_for_owner_approval"
    assert payload["review"] == "Add task: Buy milk"
    assert task_texts(env) == []
    stored = count(context, "SELECT arguments_json FROM vault_private.vault_background_actions")
    assert stored == {"tool": "tasks_add", "tool_arguments": {"text": "Buy milk"}, "summary": "Add task: Buy milk"}
    confirm = {"actionId": payload["actionId"], "contentHash": payload["contentHash"]}
    early = env["catalog"].invoke("tasks_confirm_action", confirm, context=env["ctx"])
    assert early.structured_content["status"] == "waiting_for_owner_approval" and task_texts(env) == []
    env["actions"].decide(context[1], owner_decides(context, payload))
    done = env["catalog"].invoke("tasks_confirm_action", confirm, context=env["ctx"])
    assert done.structured_content["status"] == "completed" and task_texts(env) == ["Buy milk"]
    again = env["catalog"].invoke("tasks_confirm_action", confirm, context=env["ctx"])
    assert again.structured_content["status"] == "completed" and task_texts(env) == ["Buy milk"]


def test_the_models_approve_flag_is_never_a_decision(context):
    env = build(context)
    payload = env["catalog"].invoke("calendar_create", {"title": "Dentist"}, context=env["ctx"]).structured_content
    assert payload["pendingActionId"] == payload["actionId"]
    with_flag = env["catalog"].invoke("calendar_create", {"pendingActionId": payload["actionId"], "approve": True}, context=env["ctx"])
    assert with_flag.structured_content["status"] == "waiting_for_owner_approval"
    assert env["calendar"].effects == []
    refused = env["catalog"].invoke("calendar_create", {"title": "Dentist", "approve": True}, context=env["ctx"])
    assert refused.is_error and env["calendar"].effects == []
    assert count(context, "SELECT count(*) FROM vault_private.vault_background_actions WHERE state<>'pending'") == 0


def test_a_denied_action_is_never_run_by_confirm(context):
    env = build(context)
    payload = env["catalog"].invoke("tasks_add", {"text": "Not this"}, context=env["ctx"]).structured_content
    env["actions"].decide(context[1], owner_decides(context, payload, "deny"))
    result = env["catalog"].invoke("tasks_confirm_action", {"actionId": payload["actionId"], "contentHash": payload["contentHash"]},
                                   context=env["ctx"])
    assert result.is_error and result.structured_content["status"] == "denied" and task_texts(env) == []


def test_unsupported_write_tools_fail_closed(context):
    env = build(context)
    for name in ("email_mark_read", "email_move_message", "agent_mail_archive"):
        result = env["bridge"].invoke(env["ctx"], name, {"messageId": "m1"})
        assert result.is_error and result.structured_content["code"] == "unsupported_background_tool"
    # A supported tool whose domain is not mounted is unsupported too, never a permissive fallback.
    result = env["bridge"].invoke(env["ctx"], "email_compose", {"mailboxAccountId": "m", "to": ["a@b"], "subject": "s", "body": "b"})
    assert result.structured_content["code"] == "unsupported_background_tool"
    assert count(context, "SELECT count(*) FROM vault_private.vault_background_actions") == 0


def test_authority_is_checked_before_any_draft_with_the_original_arguments(context):
    env = build(context, tool_names=["tasks_edit", "tasks_confirm_action"],
                resource_policy={"tool_arguments": {"tasks_edit": {"taskId": ["allowed-task"]}}})
    # Not in the grant: refused, and no Task draft is left behind.
    refused = env["bridge"].invoke(env["ctx"], "tasks_add", {"text": "Sneaky"})
    assert refused.is_error and refused.structured_content["code"] == "not_granted"
    # The resource bound is checked on the original arguments (taskId), not on the summary.
    outside = env["bridge"].invoke(env["ctx"], "tasks_edit", {"taskId": "other-task", "text": "Changed"})
    assert outside.is_error and outside.structured_content["code"] == "not_granted"
    assert count(context, "SELECT count(*) FROM vault_private.vault_task_pending_actions") == 0
    assert count(context, "SELECT count(*) FROM vault_private.vault_background_actions") == 0


def test_authorizer_refuses_a_mislabelled_or_confirm_shaped_action(context):
    from app.vault_runtime.background_agent.action_bridge import current_tool_authorizer
    env = build(context)
    authorize = env["actions"]._authorizer
    scope = env["scope"]
    assert authorize(scope, "tasks", None, {"tool": "tasks_add", "tool_arguments": {"text": "ok"}})
    assert not authorize(scope, "calendar", None, {"tool": "tasks_add", "tool_arguments": {"text": "ok"}})
    assert not authorize(scope, "tasks", None, {"tool": "tasks_confirm_action", "tool_arguments": {}})
    assert not authorize(scope, "calendar", None, {"tool": "calendar_create", "tool_arguments": {"pendingActionId": "x"}})
    assert not authorize(scope, "tasks", None, {"summary": "Add task: ok"})


def test_revoking_the_grant_after_approval_stops_the_effect(context):
    env = build(context)
    payload = env["catalog"].invoke("tasks_add", {"text": "Revoked"}, context=env["ctx"]).structured_content
    env["actions"].decide(context[1], owner_decides(context, payload))
    with psycopg.connect(context[0]) as connection:
        connection.execute("UPDATE vault_private.vault_background_execution_grants SET status='revoked'")
    # The catalog refuses the confirm tool itself now; the bridge's own claim check refuses too.
    via_catalog = env["catalog"].invoke("tasks_confirm_action", {"actionId": payload["actionId"], "contentHash": payload["contentHash"]},
                                        context=env["ctx"])
    assert via_catalog.is_error
    direct = env["bridge"].invoke(env["ctx"], "tasks_confirm_action", {"actionId": payload["actionId"], "contentHash": payload["contentHash"]})
    assert direct.is_error and task_texts(env) == []
    assert count(context, f"SELECT state FROM vault_private.vault_background_actions WHERE action_id='{payload['actionId']}'") == "approved"


def test_confirm_cannot_cross_tools_or_change_the_reviewed_hash(context):
    env = build(context)
    payload = env["catalog"].invoke("tasks_add", {"text": "Exact"}, context=env["ctx"]).structured_content
    env["actions"].decide(context[1], owner_decides(context, payload))
    wrong_tool = env["bridge"].invoke(env["ctx"], "calendar_create", {"pendingActionId": payload["actionId"]})
    assert wrong_tool.is_error
    wrong_hash = env["catalog"].invoke("tasks_confirm_action", {"actionId": payload["actionId"], "contentHash": "0" * 64}, context=env["ctx"])
    assert wrong_hash.is_error and task_texts(env) == []
