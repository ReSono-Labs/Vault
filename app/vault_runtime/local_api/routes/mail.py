"""Mail: mailboxes, messages and confirmed sending."""
from __future__ import annotations

from typing import Mapping
from urllib.parse import SplitResult
from .common import (
    LocalApiResponse,
    _csrf_token,
    _json_object,
    _optional_text,
    _required_bool,
    _required_object,
    _required_text,
    _session_token,
)


class MailRoutes:
    """VaultLocalApiApp routes: mail: mailboxes, messages and confirmed sending."""

    def _route_mail(
        self, *, method: str, path: str, target_parts: SplitResult, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        try:
            return self._handle_mail(
                method=method.upper(), path=path, headers=headers, body=body,
            )
        except Exception as exc:
            code = getattr(exc, "code", "mail_request_failed")
            status = 400 if isinstance(exc, ValueError) else 403
            return LocalApiResponse(status, {"error": {"code": code, "message": str(exc)}})

    def _handle_mail(
        self, *, method: str, path: str, headers: Mapping[str, str], body: bytes,
    ) -> LocalApiResponse:
        identity = self._identity_service
        runtime = self._email_runtime
        if identity is None or runtime is None:
            raise RuntimeError("Local Mail is unavailable.")
        principal = identity.authenticate(session_token=_session_token(headers))
        payload = _json_object(body) if method == "POST" else {}
        if method == "POST":
            identity.require_csrf(principal=principal, csrf_token=_csrf_token(headers))
        with runtime.service(principal) as mail:
            if path == "/mail/agent-accounts" and method == "GET":
                return LocalApiResponse(200, {"items": mail.list_mailboxes(account_id=principal.user_id, workspace_id=principal.workspace_id, mailbox_role="agent_mail")})
            if path == "/mail/agent-accounts" and method == "POST":
                record = mail.connect_mailbox(account_id=principal.user_id, workspace_id=principal.workspace_id, mailbox_role="agent_mail", credentials_payload=_required_object(payload, "credentials"), display_name=_optional_text(payload, "displayName"), validate_connection=_required_bool(payload, "validateConnection"))
                return LocalApiResponse(201, record)
            if path == "/mail/accounts" and method == "GET":
                return LocalApiResponse(200, {"items": mail.list_mailboxes(
                    account_id=principal.user_id, workspace_id=principal.workspace_id,
                    mailbox_role="normal_email",
                )})
            if path == "/mail/accounts" and method == "POST":
                record = mail.connect_mailbox(
                    account_id=principal.user_id, workspace_id=principal.workspace_id,
                    mailbox_role="normal_email", credentials_payload=_required_object(payload, "credentials"),
                    display_name=_optional_text(payload, "displayName"),
                    validate_connection=_required_bool(payload, "validateConnection"),
                )
                return LocalApiResponse(201, record)
            prefix = "/mail/accounts/"
            if not path.startswith(prefix):
                return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
            mailbox_id, _, operation = path.removeprefix(prefix).partition("/")
            if not mailbox_id or not operation:
                return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
            if method == "GET" and operation == "folders":
                return LocalApiResponse(200, {"items": mail.list_folders(
                    account_id=principal.user_id, workspace_id=principal.workspace_id, mailbox_id=mailbox_id,
                )})
            if method == "GET" and operation == "messages":
                return LocalApiResponse(200, {"items": mail.list_messages(
                    account_id=principal.user_id, workspace_id=principal.workspace_id,
                    mailbox_id=mailbox_id, limit=50,
                )})
            if method == "GET" and operation.startswith("messages/"):
                message_id = operation.removeprefix("messages/")
                item = mail.read_message(
                    account_id=principal.user_id, workspace_id=principal.workspace_id,
                    mailbox_id=mailbox_id, message_id=message_id,
                )
                return LocalApiResponse(200 if item else 404, {"item": item})
            if method == "POST" and operation == "sync":
                return LocalApiResponse(200, mail.sync_mailbox(
                    account_id=principal.user_id, workspace_id=principal.workspace_id,
                    mailbox_id=mailbox_id, trigger_kind="manual",
                ).as_dict())
            if method == "POST" and operation == "send/prepare":
                recipients = payload.get("to")
                if not isinstance(recipients, list) or any(not isinstance(item, str) for item in recipients):
                    raise ValueError("to must be a list of recipients")
                return LocalApiResponse(201, mail.prepare_send(
                    account_id=principal.user_id, workspace_id=principal.workspace_id,
                    mailbox_id=mailbox_id, idempotency_key=_required_text(payload, "idempotencyKey"),
                    to_recipients=recipients, subject=_required_text(payload, "subject"),
                    body=_required_text(payload, "body"),
                ))
            if method == "POST" and operation == "send/confirm":
                return LocalApiResponse(200, mail.confirm_send(
                    account_id=principal.user_id, workspace_id=principal.workspace_id,
                    mailbox_id=mailbox_id, pending_request_id=_required_text(payload, "pendingRequestId"),
                    approve=_required_bool(payload, "approve"),
                ))
            if method == "POST" and operation == "lifecycle":
                item = mail.set_mailbox_lifecycle(
                    account_id=principal.user_id, workspace_id=principal.workspace_id,
                    mailbox_id=mailbox_id, lifecycle_status=_required_text(payload, "status"),
                )
                return LocalApiResponse(200 if item else 404, {"item": item})
            if method == "POST" and operation == "remove":
                item = mail.permanently_remove_mailbox_local(
                    account_id=principal.user_id, workspace_id=principal.workspace_id,
                    mailbox_id=mailbox_id, confirmation_text=_required_text(payload, "confirmationText"),
                )
                return LocalApiResponse(200 if item else 404, {"item": item})
        return LocalApiResponse(404, {"error": {"code": "not_found", "message": "Not found."}})
