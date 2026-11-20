"""Vault Chat stops at a gated tool call and the Link phone shows the question in the running turn's
status, then answers it (plan 2026-11-17-vault-owner-approvals.md, step 2)."""
import json
from time import monotonic, sleep
from types import SimpleNamespace as NS

from tests.support.genui_conversation import call, finish, grant
from tests.support.link_companion_chat import _chat, _pair


class FakeText:
    def describe(self, principal, name, arguments):
        return "Send an email", ["To: sam@example.com", "Subject: Lunch"], arguments["pendingRequestId"]


def _mount(m):
    from app.vault_runtime.background_agent.coordination_repository import CoordinationRepository
    from app.vault_runtime.background_agent.owner_approvals import OwnerApprovals
    from app.vault_runtime.conversation_tools.approval_gate import ApprovalGate
    CoordinationRepository(database_url=m.url).ensure_schema()
    approvals = OwnerApprovals(database_url=m.url, poll_seconds=0.05)
    m.app._conversation_runtime.catalog.set_approval_gate(ApprovalGate(approvals=approvals, text=FakeText()))
    m.app._conversation_runtime.approvals = approvals
    return approvals


def _turn_with_gated_send(m, seen):
    async def runner(**kwargs):
        tool, raw = call(kwargs, "r1", "call-send", "email_send_pending", {"pendingRequestId": "send-1", "approve": True})
        seen["tool"] = json.loads(await tool.on_invoke_tool(NS(tool_call_id="call-send"), raw))
        return finish(kwargs, "Done.")
    m.app._conversation_runtime.runner = runner


def _waiting_status(m, token, run_id):
    deadline = monotonic() + 10
    while monotonic() < deadline:
        status = _chat(m, "GET", f"runs/{run_id}", token).payload
        if "approval" in status:
            return status
        assert status["state"] in {"queued", "running"}, status
        sleep(0.05)
    raise AssertionError("the question never appeared")


def _finished(m, token, run_id):
    deadline = monotonic() + 15
    while monotonic() < deadline:
        status = _chat(m, "GET", f"runs/{run_id}", token).payload
        if status["state"] not in {"queued", "running"}:
            return status
        sleep(0.05)
    raise AssertionError("turn did not finish")


def test_chat_stops_at_the_gate_the_phone_sees_it_and_allows_it(mounted):
    m = mounted
    m.app._conversation_runtime.memories._embedder_factory = None
    grant(m)
    approvals = _mount(m)
    seen = {}
    _turn_with_gated_send(m, seen)
    token, _pairing = _pair(m)
    session = _chat(m, "POST", "sessions", token, {}).payload["id"]
    submitted = monotonic()
    run_id = _chat(m, "POST", f"sessions/{session}/messages", token, {"text": "Send Sam the lunch email"}).payload["run_id"]
    waiting = _waiting_status(m, token, run_id)
    before_gate = monotonic() - submitted
    assert waiting["state"] == "running", "a hard stop: the turn is still running"
    question = waiting["approval"]
    assert question["title"] == "Send an email" and question["choices"] == ["allow_once", "deny"]
    assert question["detail"] == ["To: sam@example.com", "Subject: Lunch"]
    # Waiting for the owner is not working time: the working limit leaves 2 seconds after the time the
    # turn took to reach the gate, then the owner takes longer than that to answer.
    limit = int(before_gate) + 2
    m.app._conversation_runtime.turn_seconds = limit
    sleep(limit + 1)
    answered = _chat(m, "POST", f"runs/{run_id}/approval", token, {"id": question["id"], "choice": "allow_once"})
    assert answered.status_code == 200 and answered.payload["result"] == "approved"
    again = _chat(m, "POST", f"runs/{run_id}/approval", token, {"id": question["id"], "choice": "allow_once"})
    assert again.payload["result"] == "approved", "a repeated answer counts once"
    done = _finished(m, token, run_id)
    assert done["state"] == "completed" and done["text"] == "Done."
    assert "denied" not in json.dumps(seen["tool"]) and "did not answer" not in json.dumps(seen["tool"])
    from psycopg import connect
    with connect(m.url) as connection:
        state = connection.execute("SELECT state FROM vault_private.vault_background_actions WHERE action_id=%s",
                                   (question["id"],)).fetchone()[0]
    assert state in {"completed", "failed"}, "the tool ran after the allow (its own result may be an error)"
    assert approvals.pending(m.principal, turn_id=run_id) is None


def test_a_phone_deny_reaches_the_agent_as_not_done(mounted):
    m = mounted
    m.app._conversation_runtime.memories._embedder_factory = None
    grant(m)
    _mount(m)
    seen = {}
    _turn_with_gated_send(m, seen)
    token, _pairing = _pair(m)
    session = _chat(m, "POST", "sessions", token, {}).payload["id"]
    run_id = _chat(m, "POST", f"sessions/{session}/messages", token, {"text": "Send it"}).payload["run_id"]
    question = _waiting_status(m, token, run_id)["approval"]
    assert _chat(m, "POST", f"runs/{run_id}/approval", token, {"id": question["id"], "choice": "deny"}).payload["result"] == "denied"
    flipped = _chat(m, "POST", f"runs/{run_id}/approval", token, {"id": question["id"], "choice": "allow_once"})
    assert flipped.status_code >= 400, "a different second answer is refused, never an allow"
    assert _finished(m, token, run_id)["state"] == "completed"
    assert "denied" in json.dumps(seen["tool"])


def test_the_website_sees_and_answers_its_own_question(mounted):
    m = mounted
    m.app._conversation_runtime.memories._embedder_factory = None
    grant(m)
    _mount(m)
    seen = {}
    _turn_with_gated_send(m, seen)
    token, _pairing = _pair(m)
    session = _chat(m, "POST", "sessions", token, {}).payload["id"]
    run_id = _chat(m, "POST", f"sessions/{session}/messages", token, {"text": "Send it"}).payload["run_id"]
    question = _waiting_status(m, token, run_id)["approval"]
    listed = m.app.handle(method="GET", target="/approvals", headers=m.headers)
    assert listed.status_code == 200 and [item["id"] for item in listed.payload["items"]] == [question["id"]]
    no_csrf = {k: v for k, v in m.headers.items() if k.lower() != "x-resono-csrf"}
    refused = m.app.handle(method="POST", target=f"/approvals/{question['id']}/decision", headers=no_csrf,
                           body=json.dumps({"choice": "allow_once"}).encode())
    assert refused.status_code >= 400
    allowed = m.app.handle(method="POST", target=f"/approvals/{question['id']}/decision", headers=m.headers,
                           body=json.dumps({"choice": "allow_once"}).encode())
    assert allowed.status_code == 200 and allowed.payload["result"] == "approved"
    assert _finished(m, token, run_id)["state"] == "completed"
