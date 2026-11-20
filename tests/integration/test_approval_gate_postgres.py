"""The system's approve/deny stop lives in ToolCatalog.invoke: Chat and Voice agents call tools as
usual and a gated call is held until the owner answers (plan 2026-11-17-vault-owner-approvals.md)."""
import threading
import time

import pytest

from tests.support.owner_approvals import _link, _service
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult


class FakeText:
    def describe(self, principal, name, arguments):
        return "Send an email", ["To: sam@example.com", "Subject: Lunch"], arguments.get("pendingRequestId")


def _catalog(context, **service):
    from app.vault_runtime.conversation_tools.approval_gate import ApprovalGate
    calls = []
    catalog = ToolCatalog(authorizer=lambda *_: True)
    schema = {"type": "object", "properties": {"pendingRequestId": {"type": "string"}, "approve": {"type": "boolean"}},
              "additionalProperties": False}
    for name in ("email_send_pending", "email_check"):
        catalog.register(ToolDefinition(tool_id=f"builtin.{name}.v1", name=name, description=name, input_schema=schema,
            handler=lambda ctx, args, n=name: (calls.append((n, dict(args))) or ToolInvocationResult("sent")),
            effect_class="write", audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND})))
    approvals = _service(context, **service)
    catalog.set_approval_gate(ApprovalGate(approvals=approvals, text=FakeText()))
    return catalog, approvals, calls


def _chat(principal, call="call-1"):
    return ToolInvocationContext(agent=AgentKind.VOICE, user_id=principal.user_id, workspace_id=principal.workspace_id,
        tool_call_id=call, local_session_id=principal.session_id, conversation_id="conversation-1", turn_id="turn-1")


def _voice(principal, call="voice-call-1"):
    return ToolInvocationContext(agent=AgentKind.VOICE, user_id=principal.user_id, workspace_id=principal.workspace_id,
        tool_call_id=call, local_session_id=principal.session_id, voice_session_id="voice-1")


def _answer_when_asked(approvals, principal, choice, channel="browser", **where):
    def run():
        for _ in range(200):
            shown = approvals.pending(principal, **where)
            if shown:
                approvals.answer(principal, shown["id"], choice, channel=channel)
                return
            time.sleep(0.02)
    thread = threading.Thread(target=run)
    thread.start()
    return thread


def test_the_agent_just_calls_the_tool_and_the_system_holds_it_until_the_owner_allows(context):
    catalog, approvals, calls = _catalog(context)
    owner = context[1]
    answering = _answer_when_asked(approvals, owner, "allow_once", turn_id="turn-1")
    # The model's own approve flag is not an approval: the call still stops for the owner.
    result = catalog.invoke("email_send_pending", {"pendingRequestId": "send-1", "approve": True}, context=_chat(owner))
    answering.join()
    assert result.text == "sent" and calls == [("email_send_pending", {"pendingRequestId": "send-1", "approve": True})]


def test_a_denied_call_never_reaches_the_tool(context):
    catalog, approvals, calls = _catalog(context)
    owner = context[1]
    answering = _answer_when_asked(approvals, owner, "deny", turn_id="turn-1")
    result = catalog.invoke("email_send_pending", {"pendingRequestId": "send-1"}, context=_chat(owner))
    answering.join()
    assert result.is_error and "denied" in result.text and calls == []


def test_the_phone_answers_a_voice_call_the_same_way(context):
    catalog, approvals, calls = _catalog(context)
    owner = context[1]
    phone = _link(context)
    answering = _answer_when_asked(approvals, phone, "allow_once", channel="link", voice_session_id="voice-1")
    result = catalog.invoke("email_send_pending", {"pendingRequestId": "send-1"}, context=_voice(owner))
    answering.join()
    assert result.text == "sent" and len(calls) == 1


def test_no_answer_in_time_is_deny(context):
    catalog, _approvals, calls = _catalog(context, ttl_seconds=1)
    result = catalog.invoke("email_send_pending", {"pendingRequestId": "send-1"}, context=_chat(context[1]))
    assert result.is_error and "did not answer" in result.text and calls == []


def test_the_turn_or_call_ending_first_is_deny_and_the_hooks_see_the_wait(context):
    from app.vault_runtime.conversation_tools.approval_gate import ApprovalWait
    catalog, _approvals, calls = _catalog(context)
    seen = []
    stop_at = time.monotonic() + 0.3
    wait = ApprovalWait(cancelled=lambda: time.monotonic() > stop_at, started=lambda: seen.append("started"),
                        ended=lambda: seen.append("ended"))
    result = catalog.invoke("email_send_pending", {"pendingRequestId": "send-1"}, context=_chat(context[1]), approval_wait=wait)
    assert result.is_error and "ended" in result.text and calls == [] and seen == ["started", "ended"]


def test_cancelling_a_draft_and_ungated_tools_do_not_stop(context):
    catalog, _approvals, calls = _catalog(context)
    owner = context[1]
    assert catalog.invoke("email_send_pending", {"pendingRequestId": "send-1", "approve": False}, context=_chat(owner)).text == "sent"
    assert catalog.invoke("email_check", {}, context=_chat(owner, "call-2")).text == "sent"
    assert [name for name, _ in calls] == ["email_send_pending", "email_check"]


def test_another_account_cannot_answer_and_its_own_calls_wait_for_itself(context):
    catalog, approvals, calls = _catalog(context, ttl_seconds=1)
    owner, second = context[1], context[2]
    def intruder():
        for _ in range(40):
            shown = approvals.pending(owner, turn_id="turn-1")
            if shown:
                with pytest.raises(Exception):
                    approvals.answer(second, shown["id"], "allow_once", channel="browser")
                return
            time.sleep(0.02)
    thread = threading.Thread(target=intruder)
    thread.start()
    result = catalog.invoke("email_send_pending", {"pendingRequestId": "send-1"}, context=_chat(owner))
    thread.join()
    assert result.is_error and calls == []


def test_real_draft_deadline_and_mailbox_role_and_revoked_channel_refusal(context, tmp_path):
    from datetime import datetime, timedelta, timezone
    import psycopg
    from app.vault_runtime.conversation_tools.approval_gate import ApprovalGate, ApprovalText
    from app.vault_runtime.email.runtime import LocalEmailRuntime
    from app.vault_runtime.email.schema import ensure_email_schema
    from app.vault_runtime.extensions.secrets import LocalMasterKey
    from app.vault_runtime.personal_data import PersonalDataRepository
    from tests.support.local_email_runtime import _credentials

    owner = context[1]
    phone = _link(context)
    records = PersonalDataRepository(database_url=context[0])
    records.ensure_schema()
    with psycopg.connect(context[0]) as connection, connection.cursor() as cursor:
        ensure_email_schema(cursor)
    runtime = LocalEmailRuntime(database_url=context[0], master_key=LocalMasterKey(tmp_path / "mail.key"))
    with runtime.service(owner) as mail:
        mailbox = mail.connect_mailbox(account_id=owner.user_id, workspace_id=owner.workspace_id,
            mailbox_role="normal_email", credentials_payload=_credentials("owner@example.com", "fixture"),
            display_name="Fixture", validate_connection=False)
        prepared = mail.prepare_send(account_id=owner.user_id, workspace_id=owner.workspace_id,
            mailbox_id=mailbox["mailboxAccountId"], idempotency_key="send-key-1",
            to_recipients=["sam@example.com"], subject="Lunch", body="Meet at noon")
    req_id = prepared["pendingRequestId"]
    soon = datetime.now(timezone.utc) + timedelta(seconds=60)
    with psycopg.connect(context[0]) as connection:
        connection.execute("UPDATE vault_private.vault_email_send_requests SET expires_at=%s WHERE vault_email_send_request_id=%s",
                           (soon, req_id))

    calls = []
    catalog = ToolCatalog(authorizer=lambda *_: True)
    schema = {"type": "object", "properties": {"pendingRequestId": {"type": "string"}, "approve": {"type": "boolean"}},
              "additionalProperties": False}
    for name in ("email_send_pending", "agent_mail_send_pending"):
        catalog.register(ToolDefinition(tool_id=f"builtin.{name}.v1", name=name, description=name, input_schema=schema,
            handler=lambda ctx, args, n=name: (calls.append((n, dict(args))) or ToolInvocationResult("sent")),
            effect_class="write", audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND})))
    approvals = _service(context, poll_seconds=0.05)
    catalog.set_approval_gate(ApprovalGate(approvals=approvals, text=ApprovalText(database_url=context[0], records=records)))

    # Wrong mailbox role (agent_mail_send_pending for a normal_email draft) is refused before asking.
    wrong_role = catalog.invoke("agent_mail_send_pending", {"pendingRequestId": req_id}, context=_chat(owner, "call-role"))
    assert wrong_role.is_error and calls == []

    # Deadline is capped to the draft's own expiry (< 5 minutes), and unpairing after allow returns a clean refusal.
    seen_expires = []
    def allow_then_unpair():
        for _ in range(100):
            shown = approvals.pending(phone, turn_id="turn-1")
            if shown:
                seen_expires.append(shown["expires_at"])
                approvals.answer(phone, shown["id"], "allow_once", channel="link")
                with psycopg.connect(context[0]) as connection:
                    connection.execute("DELETE FROM vault_private.link_companion_link WHERE id=1")
                return
            time.sleep(0.01)
    approvals._poll = 0.25
    thread = threading.Thread(target=allow_then_unpair)
    thread.start()
    result = catalog.invoke("email_send_pending", {"pendingRequestId": req_id}, context=_chat(owner, "call-unpair"))
    thread.join()
    assert seen_expires and abs(seen_expires[0] - int(soon.timestamp())) <= 2
    assert result.is_error and "not done" in result.text and calls == []
