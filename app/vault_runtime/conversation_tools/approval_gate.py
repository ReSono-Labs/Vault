"""Which Chat/Voice tool calls stop for the owner's approval, and the text the owner reviews.

v1 gates the confirm calls whose current proof is only the model's ``approve`` flag: sending mail,
creating a calendar event, saving or using a contact. The prepare calls still create the domain's
pending draft as before; the confirm call is the hard stop. The text comes from that draft, never
from the model's arguments.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import psycopg

GATED = frozenset({
    "email_send_pending",
    "agent_mail_send_pending",
    "calendar_create",
    "contacts_confirm_pending",
    "contacts_confirm_use",
    "tasks_confirm_action",
    "memory_confirm_action",
    "command_run_approved",
})


def needs_approval(name: str, arguments: dict) -> bool:
    if name not in GATED or not isinstance(arguments, dict):
        return False
    if name == "calendar_create" and "pendingActionId" not in arguments:
        return False                       # the prepare form of calendar_create
    return arguments.get("approve") is not False   # cancelling a draft needs no approval


def tool_arguments(arguments: dict) -> dict:
    return {key: value for key, value in arguments.items() if key != "approve"}


def _draft_deadline(payload: dict) -> datetime | None:
    raw = payload.get("expires_at") or payload.get("expiresAt")
    if not isinstance(raw, str) or not raw:
        return None
    deadline = datetime.fromisoformat(raw)
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    if deadline <= datetime.now(timezone.utc):
        raise ValueError("The prepared change expired; prepare it again")
    return deadline


class ApprovalText:
    """Title, detail lines and draft deadline for the popup, read from the pending draft in this account."""

    def __init__(self, *, database_url: str, records) -> None:
        self._database_url, self._records = database_url, records

    def describe(self, principal, name: str, arguments: dict):
        if name in {"email_send_pending", "agent_mail_send_pending"}:
            return self._mail(principal, name, arguments)
        if name == "calendar_create":
            return self._calendar(principal, arguments)
        if name in {"contacts_confirm_pending", "contacts_confirm_use"}:
            return self._contact(principal, name, arguments)
        if name == "tasks_confirm_action":
            return self._task(principal, arguments)
        if name == "memory_confirm_action":
            return self._memory(principal, arguments)
        if name == "command_run_approved":
            return self._command(principal, arguments)
        return self._generic(name, arguments)

    def _pending(self, principal, table, reference):
        if not isinstance(reference, str) or not reference:
            raise ValueError("pendingActionId is required")
        row = self._records.get_private_record(account_id=principal.user_id, workspace_id=principal.workspace_id,
                                               source_table=table, source_id=reference)
        payload = (row or {}).get("sourcePayload")
        if not isinstance(payload, dict):
            raise ValueError("The prepared change was not found; prepare it again")
        return payload

    def _mail(self, principal, name, arguments):
        reference = arguments.get("pendingRequestId")
        if not isinstance(reference, str) or not reference:
            raise ValueError("pendingRequestId is required")
        role = "agent_mail" if name.startswith("agent_mail") else "normal_email"
        mailbox_id = arguments.get("mailboxAccountId")
        with psycopg.connect(self._database_url) as connection:
            row = connection.execute("""SELECT r.recipients_jsonb,r.subject,r.body_text,r.status,r.expires_at,
                    m.mailbox_role,r.mailbox_account_id
                FROM vault_private.vault_email_send_requests r
                JOIN vault_private.vault_email_mailbox_accounts m
                  ON m.vault_email_mailbox_account_id=r.mailbox_account_id
                 AND m.account_id=r.account_id AND m.workspace_id=r.workspace_id
                WHERE r.vault_email_send_request_id=%s AND r.account_id=%s AND r.workspace_id=%s""",
                (reference, principal.user_id, principal.workspace_id)).fetchone()
        if (row is None or row[3] != "pending_confirmation" or row[5] != role
                or (isinstance(mailbox_id, str) and mailbox_id and row[6] != mailbox_id)):
            raise ValueError("The prepared email was not found or was already handled; prepare it again")
        if row[4] <= datetime.now(timezone.utc):
            raise ValueError("The prepared email expired; prepare it again")
        recipients, subject, body, deadline = row[0] or [], row[1] or "", row[2] or "", row[4]
        lines = [f"To: {', '.join(str(r) for r in recipients)}", f"Subject: {subject}"]
        lines += [line for line in body.strip().splitlines() if line.strip()][:6]
        title = "Send an email" + (" from the agent mailbox" if name.startswith("agent_mail") else "")
        return title, lines, reference, deadline

    def _calendar(self, principal, arguments):
        reference = arguments.get("pendingActionId")
        payload = self._pending(principal, "calendar_pending_actions", reference)
        if payload.get("status") != "pending_confirmation":
            raise ValueError("The prepared event was already handled; prepare it again")
        deadline = _draft_deadline(payload)
        event = payload.get("arguments") if isinstance(payload.get("arguments"), dict) else {}
        lines = [str(event.get("title") or "Untitled event")]
        if event.get("allDay"):
            lines.append("All day")
        for key, label in (("startsAt", "Starts"), ("endsAt", "Ends"), ("location", "Where")):
            if event.get(key):
                lines.append(f"{label}: {event[key]}")
        if event.get("description"):
            lines.append(str(event["description"]))
        return "Add a calendar event", lines, reference, deadline

    def _contact(self, principal, name, arguments):
        reference = arguments.get("pendingActionId")
        payload = self._pending(principal, "contacts_pending_actions", reference)
        if payload.get("status") != "pending":
            raise ValueError("The prepared contact change was already handled; prepare it again")
        deadline = _draft_deadline(payload)
        summary = str(payload.get("confirmation_summary") or "").strip()
        if name == "contacts_confirm_use":
            title = "Use a contact's details"
        else:
            title = {"create": "Add a contact", "update": "Change a contact", "delete": "Delete a contact"}.get(
                str(payload.get("action_type")), "Change a contact")
        return title, [line for line in summary.splitlines() if line.strip()] or [title], reference, deadline

    def _task(self, principal, arguments):
        reference = arguments.get("actionId")
        content_hash = arguments.get("contentHash")
        if not isinstance(reference, str) or not reference or not isinstance(content_hash, str) or not content_hash:
            raise ValueError("actionId and contentHash are required")
        with psycopg.connect(self._database_url) as connection:
            row = connection.execute(
                """SELECT task_id, operation, payload_json, state, expires_at, content_hash
                   FROM vault_private.vault_task_pending_actions
                   WHERE action_id=%s AND user_id=%s AND workspace_id=%s""",
                (reference, principal.user_id, principal.workspace_id),
            ).fetchone()
        if row is None or row[3] != "pending_review" or row[5] != content_hash:
            raise ValueError("The prepared task change was not found or was already handled; prepare it again")
        if row[4] <= datetime.now(timezone.utc):
            raise ValueError("The prepared task change expired; prepare it again")
        payload = json.loads(row[2]) if isinstance(row[2], str) else (row[2] or {})
        operation = str(row[1] or "add")
        title = {
            "add": "Add a task",
            "edit": "Change a task",
            "complete": "Complete a task",
            "remove": "Remove a task",
        }.get(operation, "Change a task")
        text = str(payload.get("text") or "").strip()
        lines = [text] if text else [f"Task: {row[0]}"]
        return title, lines, reference, row[4]

    def _memory(self, principal, arguments):
        reference = arguments.get("actionId")
        if not isinstance(reference, str) or not reference:
            raise ValueError("actionId is required")
        with psycopg.connect(self._database_url) as connection:
            row = connection.execute(
                """SELECT p.action_kind, p.memory_id, p.proposed_content, p.status, m.content_text
                   FROM vault_private.vault_memory_pending_actions p
                   LEFT JOIN vault_private.vault_memory_records m
                     ON m.memory_id=p.memory_id AND m.workspace_id=p.workspace_id
                   WHERE p.action_id=%s AND p.workspace_id=%s AND p.user_id=%s""",
                (reference, principal.workspace_id, principal.user_id),
            ).fetchone()
        if row is None or row[3] != "pending":
            raise ValueError("The prepared memory change was not found or was already handled; prepare it again")
        action_kind, proposed, old_text = str(row[0]), str(row[2] or "").strip(), str(row[4] or "").strip()
        if action_kind == "forget":
            title = "Forget a memory"
            lines = [old_text] if old_text else ["Forget stored memory"]
        else:
            title = "Update a memory"
            lines = ([f"Before: {old_text}"] if old_text else []) + ([f"After: {proposed}"] if proposed else [])
        return title, lines or [title], reference, None

    def _command(self, principal, arguments):
        reference = arguments.get("requestId")
        if not isinstance(reference, str) or not reference:
            raise ValueError("requestId is required")
        with psycopg.connect(self._database_url) as connection:
            row = connection.execute(
                """SELECT directory, command, state, expires_at
                   FROM vault_private.command_requests
                   WHERE request_id=%s AND user_id=%s AND workspace_id=%s""",
                (reference, principal.user_id, principal.workspace_id),
            ).fetchone()
        if row is None or row[2] not in {"pending", "approved"}:
            raise ValueError("The prepared command was not found or was already handled")
        if row[3] <= datetime.now(timezone.utc):
            raise ValueError("The prepared command expired")
        return "Run a command", [f"Folder: {row[0]}", f"Command: {row[1]}"], reference, row[3]

    @staticmethod
    def _generic(name: str, arguments: dict):
        from app.vault_runtime.voice.tools import redact_tool_arguments

        redacted = redact_tool_arguments(arguments)
        lines = []
        if isinstance(redacted, dict):
            for k, v in list(redacted.items())[:8]:
                lines.append(f"{k}: {v}")
        return f"Run {name}", lines or [f"Tool: {name}"], None, None


# ── the gate (inside ToolCatalog.invoke, so every agent path gets it) ─────────

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Callable


@dataclass(frozen=True, slots=True)
class ApprovalWait:
    """Hooks of the caller that is stopped: when the turn/call ends (cancelled), and when the wait
    starts and ends (Chat keeps it out of working time; a phone call keeps its idle timer fresh)."""
    cancelled: Callable[[], bool] = lambda: False
    started: Callable[[], None] = lambda: None
    ended: Callable[[], None] = lambda: None
    on_question: Callable[[dict], None] = lambda _question: None


class ApprovalGate:
    """The system's hard stop. The agent does not know about it: it calls the tool as usual; a
    gated call is held here until the owner answers on the Link phone or the website."""

    def __init__(self, *, approvals, text: ApprovalText, tool_authority=None) -> None:
        self._approvals, self._text, self._tool_authority = approvals, text, tool_authority

    @staticmethod
    def _origin(context):
        from app.vault_runtime.background_agent.owner_approvals import ApprovalOrigin
        if context.turn_id is not None:
            return ApprovalOrigin(tool_call_id=context.tool_call_id, conversation_id=context.conversation_id,
                                  turn_id=context.turn_id)
        if context.voice_session_id is not None:
            return ApprovalOrigin(tool_call_id=context.tool_call_id, voice_session_id=context.voice_session_id)
        return None

    def applies(self, context, name: str, arguments: dict) -> bool:
        # Interactive Chat turns and Voice calls. Delegated background work has its own prepared
        # actions (BackgroundActionBridge); the legacy explicit Background path is unchanged here.
        if (
            context.background_scope is not None
            or context.local_session_id is None
            or self._origin(context) is None
            or not isinstance(arguments, dict)
        ):
            return False
        if name == "command_run_approved":
            # If the user already clicked Run on the website (state='approved'), do not ask again.
            req_id = arguments.get("requestId")
            db_url = getattr(self._text, "_database_url", None)
            if isinstance(req_id, str) and req_id and isinstance(db_url, str):
                with psycopg.connect(db_url) as conn:
                    r = conn.execute(
                        "SELECT state FROM vault_private.command_requests WHERE request_id=%s AND user_id=%s",
                        (req_id, context.user_id),
                    ).fetchone()
                    if r and r[0] == "approved":
                        return False
        if needs_approval(name, arguments):
            return True
        if self._tool_authority is not None:
            return bool(
                self._tool_authority.requires_approval(
                    user_id=context.user_id, workspace_id=context.workspace_id, tool_name=name,
                )
            )
        return False

    def hold(self, context, name: str, arguments: dict, wait: ApprovalWait):
        """Ask and wait. Returns (approval_id, None) when allowed, (None, refusal_text) otherwise."""
        from app.vault_runtime.background_agent.errors import (
            BackgroundRunAuthorizationError, BackgroundRunConflictError,
        )
        principal = SimpleNamespace(user_id=context.user_id, workspace_id=context.workspace_id,
                                    session_id=context.local_session_id)
        try:
            title, lines, reference, *rest = self._text.describe(principal, name, arguments)
            deadline = rest[0] if rest else None
            approval = self._approvals.ask(principal, origin=self._origin(context), tool_name=name,
                                           tool_arguments=tool_arguments(arguments), title=title,
                                           detail_lines=lines, domain_ref=reference, deadline=deadline)
        except BackgroundRunConflictError:
            return None, "Already waiting for the owner's answer to another request; try again after it."
        except BackgroundRunAuthorizationError:
            return None, "The owner's session is no longer active. It was not done."
        except ValueError as exc:
            return None, str(exc)
        shown = self._approvals.pending(
            principal, turn_id=context.turn_id, voice_session_id=context.voice_session_id,
        )
        if shown is not None:
            wait.on_question(shown)
        wait.started()
        try:
            answer = self._approvals.wait(principal, approval.action_id, cancelled=wait.cancelled)
        except BackgroundRunAuthorizationError:
            return None, "The owner's approval could not be verified. It was not done."
        finally:
            wait.ended()
        if answer == "allowed":
            try:
                self._approvals.consume(principal, approval.action_id)
            except (BackgroundRunAuthorizationError, BackgroundRunConflictError):
                return None, "The owner's approval could not be verified. It was not done."
            return approval.action_id, None
        if answer == "denied":
            return None, "The owner denied this. It was not done; do not try it again."
        if answer == "cancelled":
            return None, "The conversation ended before the owner answered. It was not done."
        return None, "The owner did not answer in time. It was not done."

    def finish(self, context, approval_id: str, outcome: dict) -> None:
        principal = SimpleNamespace(user_id=context.user_id, workspace_id=context.workspace_id,
                                    session_id=context.local_session_id)
        self._approvals.finish(principal, approval_id, outcome)
