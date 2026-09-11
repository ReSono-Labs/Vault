from __future__ import annotations

from base64 import b64encode
from typing import Any, Mapping

from app.vault_runtime.email_service import VaultEmailService
from app.vault_runtime.session_tools.primitives import (
    bounded_int,
    optional_private_argument_text,
    private_argument_text,
    private_bool,
    private_string_list,
)


EMAIL_SIGNAL_CACHE_TOOLS = frozenset(
    {
        "email_account_status",
        "email_list_folders",
        "email_check",
        "email_get_unread",
        "email_search",
        "email_read",
        "email_read_attachment",
        "email_contact_lookup",
    }
)
EMAIL_SIGNAL_SIDE_EFFECT_TOOLS = frozenset(
    {
        "email_mark_read",
        "email_mark_unread",
        "email_compose",
        "email_send_pending",
        "email_archive",
        "email_create_folder",
        "email_rename_folder",
        "email_move_message",
    }
)


class VaultEmailSignalSessionTools:
    def __init__(self, *, store: Any, mailbox_role: str = "normal_email") -> None:
        self._store = store
        self._mailbox_role = mailbox_role

    def execute_cache_tool(
        self,
        *,
        account_id: str,
        workspace_id: str,
        voice_realtime_session_id: str,
        tool_call_id: str,
        tool_name: str,
        arguments: Mapping[str, Any],
        auto_mark_read: bool = True,
    ) -> dict[str, Any]:
        return self._execute_canonical_cache_tool(
            service=self._canonical_service(),
            account_id=account_id,
            workspace_id=workspace_id,
            tool_name=tool_name,
            arguments=arguments,
        )

    def execute_side_effect_tool(
        self,
        *,
        account_id: str,
        workspace_id: str,
        voice_realtime_session_id: str,
        tool_call_id: str,
        tool_name: str,
        arguments: Mapping[str, Any],
        caller_owned_provider_action_id: str | None = None,
    ) -> dict[str, Any]:
        return self._execute_canonical_side_effect_tool(
            service=self._canonical_service(),
            account_id=account_id,
            workspace_id=workspace_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments=arguments,
        )

    def _canonical_service(self) -> VaultEmailService:
        if not callable(getattr(self._store, "email_store", None)):
            raise RuntimeError("Canonical Vault Email store is unavailable.")
        if not callable(getattr(self._store, "get_provider_credential_by_id", None)):
            raise RuntimeError("Canonical Vault Email credential store is unavailable.")
        return VaultEmailService(store=self._store)

    def _execute_canonical_cache_tool(
        self,
        *,
        service: VaultEmailService,
        account_id: str,
        workspace_id: str,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        if tool_name == "email_account_status":
            requested_id = optional_private_argument_text(arguments, "mailboxAccountId")
            if requested_id:
                mailbox = service.mailbox_status(
                    account_id=account_id,
                    workspace_id=workspace_id,
                    mailbox_id=requested_id,
                    mailbox_role=self._mailbox_role,
                )
                if mailbox is None:
                    raise PermissionError("The requested Email mailbox is outside this route scope.")
                return {"status": "completed", "item": mailbox, "source": "vault_email_canonical"}
            mailboxes = service.list_mailboxes(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_role=self._mailbox_role,
            )
            return {
                "status": "completed",
                "items": mailboxes,
                "count": len(mailboxes),
                "source": "vault_email_canonical",
            }
        mailbox = self._resolve_canonical_mailbox(
            service=service,
            account_id=account_id,
            workspace_id=workspace_id,
            arguments=arguments,
            mailbox_role=self._mailbox_role,
        )
        if mailbox is None:
            return {
                "status": "configuration_required",
                "source": "vault_email",
                "cloudFallback": False,
                "message": "No active Email mailbox is connected to this Vault.",
            }
        mailbox_id = str(mailbox["mailboxAccountId"])
        if tool_name == "email_list_folders":
            folders = service.list_folders(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=mailbox_id,
            )
            return {
                "status": "completed",
                "items": folders,
                "count": len(folders),
                "mailboxAccountId": mailbox_id,
                "source": "vault_email_canonical",
            }
        if tool_name == "email_read_attachment":
            attachment = service.read_attachment(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=mailbox_id,
                attachment_id=private_argument_text(arguments, "attachmentId", required=True),
            )
            if attachment and attachment.get("contentBytes") is not None:
                content_bytes = attachment.pop("contentBytes")
                attachment["contentBase64"] = b64encode(content_bytes).decode("ascii")
            return {
                "status": "completed" if attachment else "not_found",
                "item": attachment,
                "mailboxAccountId": mailbox_id,
                "source": "vault_email_canonical",
            }
        freshness = {
            "source": "vault_email_canonical",
            "syncStatus": mailbox.get("syncStatus"),
            "resultsMayBePartial": mailbox.get("syncStatus") != "complete",
            "refreshMode": "background_sync",
        }
        if tool_name == "email_read":
            item = service.read_message(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=mailbox_id,
                message_id=private_argument_text(arguments, "messageId", required=True),
            )
            return {
                "status": "completed" if item else "not_found",
                "item": item,
                "mailboxAccountId": mailbox_id,
                "freshness": freshness,
            }
        folder_id = self._canonical_folder_id(
            service=service,
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
            requested_folder=optional_private_argument_text(arguments, "folder"),
        )
        query = (
            private_argument_text(arguments, "query", required=True)
            if tool_name in {"email_search", "email_contact_lookup"}
            else None
        )
        items = service.list_messages(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
            folder_id=folder_id,
            query=query,
            unread_only=tool_name == "email_get_unread",
            limit=bounded_int(arguments.get("limit"), default=25, minimum=1, maximum=100),
        )
        if tool_name == "email_contact_lookup":
            contacts: list[dict[str, Any]] = []
            seen: set[str] = set()
            for item in items:
                for address in item.get("from") or []:
                    email_address = str(address.get("email") or "").casefold()
                    if not email_address or email_address in seen:
                        continue
                    seen.add(email_address)
                    contacts.append(address)
            return {
                "status": "completed",
                "items": contacts,
                "count": len(contacts),
                "mailboxAccountId": mailbox_id,
                "freshness": freshness,
            }
        return {
            "status": "completed",
            "items": items,
            "count": len(items),
            "mailboxAccountId": mailbox_id,
            "freshness": freshness,
        }

    def _execute_canonical_side_effect_tool(
        self,
        *,
        service: VaultEmailService,
        account_id: str,
        workspace_id: str,
        tool_call_id: str,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        mailbox = self._resolve_canonical_mailbox(
            service=service,
            account_id=account_id,
            workspace_id=workspace_id,
            arguments=arguments,
            mailbox_role=self._mailbox_role,
        )
        if mailbox is None:
            return {"status": "configuration_required", "cloudFallback": False}
        mailbox_id = str(mailbox["mailboxAccountId"])
        if tool_name == "email_compose":
            request = service.prepare_send(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=mailbox_id,
                idempotency_key=tool_call_id,
                to_recipients=private_string_list(arguments.get("to"), key="to"),
                subject=private_argument_text(arguments, "subject", required=True),
                body=private_argument_text(arguments, "body", required=True),
            )
            return {
                **request,
                "confirmationRequired": True,
                "providerSideEffect": "not_executed",
                "mailboxAccountId": mailbox_id,
                "source": "vault_email_canonical",
            }
        if tool_name == "email_send_pending":
            return service.confirm_send(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=mailbox_id,
                pending_request_id=private_argument_text(
                    arguments, "pendingRequestId", required=True
                ),
                approve=private_bool(arguments.get("approve"), key="approve", default=True),
            )
        if tool_name == "email_create_folder":
            service.create_folder(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=mailbox_id,
                folder_name=private_argument_text(arguments, "folderName", required=True),
            )
            return {"status": "completed", "mailboxAccountId": mailbox_id}
        if tool_name == "email_rename_folder":
            service.rename_folder(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=mailbox_id,
                source_folder=private_argument_text(arguments, "sourceFolder", required=True),
                destination_folder=private_argument_text(arguments, "destinationFolder", required=True),
            )
            return {"status": "completed", "mailboxAccountId": mailbox_id}
        if tool_name == "email_move_message":
            service.move_message(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=mailbox_id,
                provider_message_id=private_argument_text(arguments, "messageId", required=True),
                source_folder=private_argument_text(arguments, "sourceFolder", required=True),
                destination_folder=private_argument_text(arguments, "destinationFolder", required=True),
            )
            return {"status": "completed", "mailboxAccountId": mailbox_id}
        provider_message_id = private_argument_text(arguments, "messageId", required=True)
        source_folder = (
            optional_private_argument_text(arguments, "sourceFolder")
            or optional_private_argument_text(arguments, "folder")
            or "INBOX"
        )
        if tool_name in {"email_mark_read", "email_mark_unread"}:
            service.set_read_state(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=mailbox_id,
                provider_message_id=provider_message_id,
                source_folder=source_folder,
                is_read=tool_name == "email_mark_read",
            )
        elif tool_name == "email_archive":
            service.archive_message(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=mailbox_id,
                provider_message_id=provider_message_id,
                source_folder=source_folder,
            )
        else:
            raise ValueError("Unsupported canonical Email operation.")
        return {
            "status": "completed",
            "source": "vault_email_canonical",
            "mailboxAccountId": mailbox_id,
        }

    def _resolve_canonical_mailbox(
        self,
        *,
        service: VaultEmailService,
        account_id: str,
        workspace_id: str,
        arguments: Mapping[str, Any],
        mailbox_role: str,
    ) -> dict[str, Any] | None:
        requested_id = optional_private_argument_text(arguments, "mailboxAccountId")
        if requested_id:
            mailbox = service.mailbox_status(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=requested_id,
                mailbox_role=mailbox_role,
            )
            if mailbox is None:
                raise PermissionError("The requested Email mailbox is outside this route scope.")
            return mailbox
        mailboxes = [
            mailbox
            for mailbox in service.list_mailboxes(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_role=mailbox_role,
            )
            if mailbox.get("lifecycleStatus") == "active"
        ]
        if not mailboxes:
            return None
        if len(mailboxes) > 1:
            raise ValueError("mailboxAccountId is required when more than one Email mailbox is active.")
        return mailboxes[0]

    @staticmethod
    def _canonical_folder_id(
        *,
        service: VaultEmailService,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        requested_folder: str | None,
    ) -> str | None:
        if not requested_folder:
            return None
        normalized = requested_folder.casefold()
        for folder in service.list_folders(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
        ):
            if normalized in {
                str(folder.get("folderId") or "").casefold(),
                str(folder.get("providerFolderKey") or "").casefold(),
                str(folder.get("displayName") or "").casefold(),
            }:
                return str(folder["folderId"])
        raise ValueError("The requested Email folder was not found.")
