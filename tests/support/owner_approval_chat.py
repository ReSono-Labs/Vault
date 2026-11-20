"""Shared owner-approval chat helpers (TST-01: test modules never import each other)."""
import json
from types import SimpleNamespace as NS

from tests.support.genui_conversation import call, finish


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
