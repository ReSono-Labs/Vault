"""One owner-approval system for Vault Chat and Voice (plan 2026-11-17-vault-owner-approvals.md, step 1).

Every approval belongs to one account; only that account answers it, from the website ('browser')
or, for the device owner, the paired Link phone ('link'). Allow once or deny; no answer = deny.
"""
from concurrent.futures import ThreadPoolExecutor
import threading
import time

import psycopg
import pytest

from app.vault_runtime.background_agent.errors import BackgroundRunAuthorizationError, BackgroundRunConflictError
from tests.support.owner_approvals import _service, _identities, _link


def _origin(turn="turn-1", call="call-1", voice=None):
    from app.vault_runtime.background_agent.owner_approvals import ApprovalOrigin
    if voice:
        return ApprovalOrigin(voice_session_id=voice, tool_call_id=call)
    return ApprovalOrigin(conversation_id="conversation-1", turn_id=turn, tool_call_id=call)


def _ask(service, principal, origin=None, **overrides):
    values = dict(origin=origin or _origin(), tool_name="email_send_pending",
                  tool_arguments={"pendingRequestId": "send-1"}, title="Send an email",
                  detail_lines=["To: sam@example.com", "Subject: Lunch"], domain_ref="send-1", resource_version="v1")
    values.update(overrides)
    return service.ask(principal, **values)


def _state(context, action_id):
    with psycopg.connect(context[0]) as connection:
        return connection.execute("SELECT state FROM vault_private.vault_background_actions WHERE action_id=%s",
                                  (action_id,)).fetchone()[0]


def test_the_phone_sees_the_contract_shape_and_an_allow_lets_the_tool_run_once(context):
    service = _service(context)
    owner = context[1]
    approval = _ask(service, owner)
    shown = service.pending(owner, turn_id="turn-1")
    assert shown == {"id": approval.action_id, "title": "Send an email", "detail": ["To: sam@example.com", "Subject: Lunch"],
                     "choices": ["allow_once", "deny"], "expires_at": int(approval.expires_at.timestamp())}
    assert approval.expires_at.timestamp() - time.time() <= 300
    assert service.answer(owner, approval.action_id, "allow_once", channel="browser") == "approved"
    assert service.answer(owner, approval.action_id, "allow_once", channel="browser") == "approved", "a repeated tap counts once"
    assert service.wait(owner, approval.action_id) == "allowed"
    assert service.pending(owner, turn_id="turn-1") is None
    service.consume(owner, approval.action_id)
    with pytest.raises(BackgroundRunConflictError):
        service.consume(owner, approval.action_id)
    service.finish(owner, approval.action_id, {"state": "completed"})
    assert _state(context, approval.action_id) == "completed"


def test_the_tool_call_waits_until_the_owner_answers(context):
    service = _service(context)
    owner = context[1]
    approval = _ask(service, owner)
    timer = threading.Timer(0.3, lambda: service.answer(owner, approval.action_id, "allow_once", channel="browser"))
    timer.start()
    started = time.monotonic()
    assert service.wait(owner, approval.action_id) == "allowed"
    assert time.monotonic() - started >= 0.25
    timer.join()


def test_deny_is_final_and_nothing_runs(context):
    service = _service(context)
    owner = context[1]
    approval = _ask(service, owner)
    assert service.answer(owner, approval.action_id, "deny", channel="browser") == "denied"
    assert service.wait(owner, approval.action_id) == "denied"
    with pytest.raises(BackgroundRunAuthorizationError):
        service.consume(owner, approval.action_id)
    with pytest.raises(BackgroundRunConflictError):
        service.answer(owner, approval.action_id, "allow_once", channel="browser")


def test_no_answer_in_time_is_deny_and_a_late_answer_changes_nothing(context):
    service = _service(context, ttl_seconds=1)
    owner = context[1]
    approval = _ask(service, owner)
    assert service.wait(owner, approval.action_id) == "expired"
    assert _state(context, approval.action_id) == "expired"
    assert service.answer(owner, approval.action_id, "allow_once", channel="browser") == "expired"
    with pytest.raises(BackgroundRunAuthorizationError):
        service.consume(owner, approval.action_id)


def test_the_turn_ending_first_is_deny(context):
    service = _service(context)
    owner = context[1]
    approval = _ask(service, owner)
    assert service.wait(owner, approval.action_id, cancelled=lambda: True) == "cancelled"
    assert _state(context, approval.action_id) == "expired"
    assert service.answer(owner, approval.action_id, "allow_once", channel="browser") == "expired"


def test_one_waiting_approval_per_account_and_a_retry_reuses_it(context):
    service = _service(context)
    owner = context[1]
    first = _ask(service, owner)
    assert _ask(service, owner).action_id == first.action_id, "the same tool call asking again gets the same approval"
    with pytest.raises(BackgroundRunConflictError):
        _ask(service, owner, origin=_origin(call="call-2"))
    service.answer(owner, first.action_id, "deny", channel="browser")
    assert _ask(service, owner, origin=_origin(call="call-2")).action_id != first.action_id


def test_four_accounts_each_wait_on_their_own_approval_and_only_answer_their_own(context):
    service = _service(context)
    identities = _identities(context)
    owner, second = context[1], context[2]
    for name in ("third", "fourth"):
        identities.create_user(actor=owner, username=name, password=f"{name}-password", display_name=name.title(),
                               experience_style="strict")
    users = [owner, second] + [identities.login(username=n, password=f"{n}-password").principal for n in ("third", "fourth")]
    approvals = [_ask(service, user, origin=_origin(turn=f"turn-{i}", call=f"call-{i}")) for i, user in enumerate(users)]
    assert len({a.action_id for a in approvals}) == 4
    for i, user in enumerate(users):
        mine = approvals[i]
        for j, other in enumerate(users):
            if j == i:
                continue
            assert service.pending(other, turn_id=f"turn-{i}") is None, "never shown to another account"
            with pytest.raises(BackgroundRunAuthorizationError):
                service.answer(other, mine.action_id, "allow_once", channel="browser")
        assert service.pending(user, turn_id=f"turn-{i}")["id"] == mine.action_id
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda pair: service.answer(pair[0], pair[1].action_id, "allow_once", channel="browser"),
                                zip(users, approvals)))
    assert results == ["approved"] * 4


def test_the_phone_answers_only_for_the_paired_owner_and_the_first_answer_wins(context):
    service = _service(context)
    owner, second = context[1], context[2]
    phone = _link(context)
    approval = _ask(service, owner)
    with pytest.raises(BackgroundRunAuthorizationError):
        service.answer(owner, approval.action_id, "allow_once", channel="link"), "the browser session is not the phone"
    assert service.answer(phone, approval.action_id, "deny", channel="link") == "denied"
    with pytest.raises(BackgroundRunConflictError):
        service.answer(owner, approval.action_id, "allow_once", channel="browser")
    theirs = _ask(service, second, origin=_origin(turn="turn-s", call="call-s"))
    with pytest.raises(BackgroundRunAuthorizationError):
        service.answer(phone, theirs.action_id, "allow_once", channel="link")
    assert service.pending(phone, turn_id="turn-s") is None


def test_unpairing_the_phone_after_its_allow_stops_the_tool(context):
    service = _service(context)
    owner = context[1]
    phone = _link(context)
    approval = _ask(service, owner)
    service.answer(phone, approval.action_id, "allow_once", channel="link")
    with psycopg.connect(context[0]) as connection:
        connection.execute("DELETE FROM vault_private.link_companion_link WHERE id=1")
    with pytest.raises(BackgroundRunAuthorizationError):
        service.consume(owner, approval.action_id)


def test_only_the_two_choices_exist(context):
    service = _service(context)
    owner = context[1]
    approval = _ask(service, owner)
    for choice in ("always", "allow", "", None):
        with pytest.raises(ValueError):
            service.answer(owner, approval.action_id, choice, channel="browser")
    assert _state(context, approval.action_id) == "pending"


def test_voice_calls_use_the_same_approvals(context):
    service = _service(context)
    owner = context[1]
    approval = _ask(service, owner, origin=_origin(voice="voice-1", call="voice-call-1"))
    assert service.pending(owner, voice_session_id="voice-1")["id"] == approval.action_id
    assert service.pending(owner, turn_id="turn-1") is None
    assert service.answer(owner, approval.action_id, "allow_once", channel="browser") == "approved"


def test_waiting_approvals_left_by_a_restart_are_expired(context):
    service = _service(context)
    owner = context[1]
    approval = _ask(service, owner)
    assert service.expire_all_waiting() == 1
    assert _state(context, approval.action_id) == "expired"
    assert _ask(service, owner, origin=_origin(call="call-2")).action_id != approval.action_id


def test_background_action_paths_refuse_owner_approvals(context):
    from app.vault_runtime.background_agent.actions import BackgroundActions
    from app.vault_runtime.background_agent.coordination_contracts import OwnerScope
    service = _service(context)
    owner = context[1]
    approval = _ask(service, owner)
    service.answer(owner, approval.action_id, "allow_once", channel="browser")
    actions = BackgroundActions(database_url=context[0], domains={}, authorizer=lambda *_: True)
    scope = OwnerScope(owner.user_id, owner.workspace_id)
    with pytest.raises((ValueError, BackgroundRunAuthorizationError)):
        actions.claim(scope, approval.action_id, approval.action_hash)
    with pytest.raises((ValueError, BackgroundRunConflictError)):
        actions.reopen(owner, approval.action_id, channel="browser", channel_generation=owner.session_id)
