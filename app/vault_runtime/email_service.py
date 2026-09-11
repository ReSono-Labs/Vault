from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from typing import Any, Mapping, Protocol

from app.vault_runtime.email_provider import (
    VaultEmailCredentials,
    VaultEmailFolder,
    VaultEmailProviderClient,
)
from app.vault_runtime.email_store import mailbox_account_id


logger = logging.getLogger(__name__)


class VaultEmailServiceStore(Protocol):
    def upsert_provider_credential(
        self, payload: dict[str, Any], *, account_id: str, workspace_id: str
    ) -> dict[str, Any]: ...

    def get_provider_credential_by_id(
        self, *, account_id: str, workspace_id: str, provider_credential_id: str
    ) -> dict[str, Any] | None: ...

    def delete_provider_credential_by_id(
        self, *, account_id: str, workspace_id: str, provider_credential_id: str
    ) -> bool: ...

    def email_store(self): ...


@dataclass(frozen=True, slots=True)
class VaultEmailSyncSummary:
    status: str
    folder_count: int
    message_count: int
    attachment_count: int
    failure_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "folderCount": self.folder_count,
            "messageCount": self.message_count,
            "attachmentCount": self.attachment_count,
            "failureCount": self.failure_count,
        }


class VaultEmailService:
    def __init__(
        self,
        *,
        store: VaultEmailServiceStore,
        provider: VaultEmailProviderClient | None = None,
    ) -> None:
        self._store = store
        self._email_store = store.email_store()
        self._provider = provider or VaultEmailProviderClient()

    def connect_mailbox(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_role: str,
        credentials_payload: Mapping[str, Any],
        display_name: str | None = None,
        validate_connection: bool = True,
    ) -> dict[str, Any]:
        credentials = credentials_from_payload(credentials_payload)
        role = _mailbox_role(mailbox_role)
        resolved_mailbox_id = mailbox_account_id(
            workspace_id=workspace_id,
            email_address=credentials.email_address,
        )
        provider_kind = "email"
        credential_id = f"{provider_kind}:{resolved_mailbox_id}"
        if validate_connection:
            self._provider.validate_credentials(credentials=credentials)
        mailbox = self._email_store.upsert_mailbox(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_role=role,
            email_address=credentials.email_address,
            display_name=display_name,
            provider_credential_id=credential_id,
        )
        self._store.upsert_provider_credential(
            {
                "providerKind": provider_kind,
                "providerCredentialId": credential_id,
                "mailboxAccountId": resolved_mailbox_id,
                "credentials": dict(credentials_payload),
                "status": "active",
            },
            account_id=account_id,
            workspace_id=workspace_id,
        )
        return {
            **mailbox,
            "credentialStatus": "stored_vault_local",
        }

    def list_mailboxes(
        self, *, account_id: str, workspace_id: str, mailbox_role: str | None = None
    ) -> list[dict[str, Any]]:
        return self._email_store.list_mailboxes(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_role=mailbox_role,
        )

    def sync_due_mailboxes(
        self,
        *,
        limit: int,
        sync_interval_seconds: int,
        page_size: int,
    ) -> list[VaultEmailSyncSummary]:
        due_before = datetime.now(UTC) - timedelta(
            seconds=max(30, int(sync_interval_seconds))
        )
        candidates = self._email_store.list_sync_candidates(
            due_before=due_before,
            limit=limit,
        )
        return [
            self.sync_mailbox(
                account_id=str(candidate["accountId"]),
                workspace_id=str(candidate["workspaceId"]),
                mailbox_id=str(candidate["mailboxAccountId"]),
                trigger_kind="worker",
                page_size=page_size,
                max_pages_per_folder=1,
            )
            for candidate in candidates
        ]

    def mailbox_status(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        mailbox_role: str | None = None,
    ) -> dict[str, Any] | None:
        return self._email_store.get_mailbox(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
            mailbox_role=mailbox_role,
        )

    def list_folders(
        self, *, account_id: str, workspace_id: str, mailbox_id: str
    ) -> list[dict[str, Any]]:
        self._require_active_mailbox(
            account_id=account_id, workspace_id=workspace_id, mailbox_id=mailbox_id
        )
        return self._email_store.list_folders(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
        )

    def list_messages(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        folder_id: str | None = None,
        query: str | None = None,
        unread_only: bool = False,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        self._require_active_mailbox(
            account_id=account_id, workspace_id=workspace_id, mailbox_id=mailbox_id
        )
        return self._email_store.list_messages(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
            folder_id=folder_id,
            query=query,
            unread_only=unread_only,
            limit=limit,
        )

    def read_message(
        self, *, account_id: str, workspace_id: str, mailbox_id: str, message_id: str
    ) -> dict[str, Any] | None:
        self._require_active_mailbox(
            account_id=account_id, workspace_id=workspace_id, mailbox_id=mailbox_id
        )
        return self._email_store.get_message(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
            message_id=message_id,
        )

    def read_attachment(
        self, *, account_id: str, workspace_id: str, mailbox_id: str, attachment_id: str
    ) -> dict[str, Any] | None:
        self._require_active_mailbox(
            account_id=account_id, workspace_id=workspace_id, mailbox_id=mailbox_id
        )
        return self._email_store.get_attachment(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
            attachment_id=attachment_id,
        )

    def sync_mailbox(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        trigger_kind: str = "manual",
        page_size: int = 100,
        max_pages_per_folder: int = 5,
        max_attachment_bytes: int = 10 * 1024 * 1024,
    ) -> VaultEmailSyncSummary:
        claim_sync = getattr(self._email_store, "claim_sync", None)
        claim_context = (
            claim_sync(mailbox_id=mailbox_id)
            if callable(claim_sync)
            else nullcontext(True)
        )
        with claim_context as acquired:
            if not acquired:
                logger.info(
                    "vault_email_sync_skipped_already_running",
                    extra={"mailboxId": mailbox_id, "triggerKind": trigger_kind},
                )
                return VaultEmailSyncSummary("already_running", 0, 0, 0, 0)
            return self._sync_claimed_mailbox(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=mailbox_id,
                trigger_kind=trigger_kind,
                page_size=page_size,
                max_pages_per_folder=max_pages_per_folder,
                max_attachment_bytes=max_attachment_bytes,
            )

    def _sync_claimed_mailbox(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        trigger_kind: str,
        page_size: int,
        max_pages_per_folder: int,
        max_attachment_bytes: int,
    ) -> VaultEmailSyncSummary:
        mailbox = self._require_active_mailbox(
            account_id=account_id, workspace_id=workspace_id, mailbox_id=mailbox_id
        )
        credentials = self._credentials_for_mailbox(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox=mailbox,
        )
        run_id = self._email_store.start_sync_run(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
            trigger_kind=trigger_kind,
        )
        folder_count = message_count = attachment_count = failure_count = 0
        all_complete = True
        try:
            sync_session = getattr(self._provider, "sync_session", None)
            provider_context = (
                sync_session(credentials=credentials)
                if callable(sync_session)
                else nullcontext(self._provider)
            )
            with provider_context as sync_provider:
                provider_folders = sync_provider.list_folders(
                    credentials=credentials
                )
                folder_count = len(provider_folders)
                reconcile_folder_inventory = getattr(
                    self._email_store, "reconcile_folder_inventory", None
                )
                if callable(reconcile_folder_inventory):
                    reconcile_folder_inventory(
                        account_id=account_id,
                        workspace_id=workspace_id,
                        mailbox_id=mailbox_id,
                        provider_folder_keys=[
                            folder.provider_folder_key for folder in provider_folders
                        ],
                    )
                for folder in provider_folders:
                    folder_complete, stored_messages, stored_attachments = self._sync_folder(
                        account_id=account_id,
                        workspace_id=workspace_id,
                        mailbox_id=mailbox_id,
                        credentials=credentials,
                        provider=sync_provider,
                        folder=folder,
                        page_size=page_size,
                        max_pages=max_pages_per_folder,
                        max_attachment_bytes=max_attachment_bytes,
                    )
                    all_complete = all_complete and folder_complete
                    message_count += stored_messages
                    attachment_count += stored_attachments
            status = "complete" if all_complete else "partial"
            self._email_store.finish_sync_run(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=mailbox_id,
                run_id=run_id,
                status=status,
                folder_count=folder_count,
                message_count=message_count,
                attachment_count=attachment_count,
            )
        except Exception as exc:
            failure_count = 1
            error_code, error_class = support_safe_provider_error(exc)
            logger.warning(
                "vault_email_sync_failed",
                extra={
                    "errorCode": error_code,
                    "errorClass": error_class,
                    "mailboxId": mailbox_id,
                    "syncRunId": run_id,
                },
            )
            self._email_store.finish_sync_run(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=mailbox_id,
                run_id=run_id,
                status="failed",
                folder_count=folder_count,
                message_count=message_count,
                attachment_count=attachment_count,
                failure_count=failure_count,
                error_code=error_code,
                error_class=error_class,
            )
            return VaultEmailSyncSummary(
                "failed", folder_count, message_count, attachment_count, failure_count
            )
        return VaultEmailSyncSummary(
            status, folder_count, message_count, attachment_count, failure_count
        )

    def set_read_state(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        provider_message_id: str,
        source_folder: str,
        is_read: bool,
    ) -> None:
        credentials = self._credentials_for_active_mailbox(
            account_id=account_id, workspace_id=workspace_id, mailbox_id=mailbox_id
        )
        provider_uid, resolved_source_folder = self._provider_message_target(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
            message_reference=provider_message_id,
        )
        self._provider.set_read_state(
            credentials=credentials,
            message_id=provider_uid,
            source_folder=resolved_source_folder,
            is_read=is_read,
        )

    def archive_message(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        provider_message_id: str,
        source_folder: str,
    ) -> None:
        credentials = self._credentials_for_active_mailbox(
            account_id=account_id, workspace_id=workspace_id, mailbox_id=mailbox_id
        )
        provider_uid, resolved_source_folder = self._provider_message_target(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
            message_reference=provider_message_id,
        )
        self._provider.archive_message(
            credentials=credentials,
            message_id=provider_uid,
            source_folder=resolved_source_folder,
        )

    def create_folder(
        self, *, account_id: str, workspace_id: str, mailbox_id: str, folder_name: str
    ) -> None:
        credentials = self._credentials_for_active_mailbox(
            account_id=account_id, workspace_id=workspace_id, mailbox_id=mailbox_id
        )
        self._provider.create_folder(credentials=credentials, folder_name=folder_name)

    def rename_folder(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        source_folder: str,
        destination_folder: str,
    ) -> None:
        credentials = self._credentials_for_active_mailbox(
            account_id=account_id, workspace_id=workspace_id, mailbox_id=mailbox_id
        )
        self._provider.rename_folder(
            credentials=credentials,
            source_folder=source_folder,
            destination_folder=destination_folder,
        )

    def move_message(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        provider_message_id: str,
        source_folder: str,
        destination_folder: str,
    ) -> None:
        credentials = self._credentials_for_active_mailbox(
            account_id=account_id, workspace_id=workspace_id, mailbox_id=mailbox_id
        )
        provider_uid, resolved_source_folder = self._provider_message_target(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
            message_reference=provider_message_id,
        )
        self._provider.move_message(
            credentials=credentials,
            message_id=provider_uid,
            source_folder=resolved_source_folder,
            destination_folder=destination_folder,
        )

    def _provider_message_target(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        message_reference: str,
    ) -> tuple[str, str]:
        """Resolve a public Vault message ID to its scoped IMAP UID and folder."""
        message = self._email_store.get_message(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
            message_id=message_reference,
        )
        if message is not None:
            folder_record_id = str(message.get("folderId") or "")
            provider_uid = str(message.get("providerUid") or "")
            folder = next(
                (
                    item
                    for item in self._email_store.list_folders(
                        account_id=account_id,
                        workspace_id=workspace_id,
                        mailbox_id=mailbox_id,
                    )
                    if str(item.get("folderId") or "") == folder_record_id
                ),
                None,
            )
            provider_folder_key = (
                str(folder.get("providerFolderKey") or "") if folder else ""
            )
            if not provider_uid.isdigit() or not provider_folder_key:
                raise RuntimeError("Mailbox message provider coordinates are unavailable.")
            return provider_uid, provider_folder_key
        raise PermissionError("Message scope was not authorized.")

    def prepare_send(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        idempotency_key: str,
        to_recipients: list[str],
        subject: str,
        body: str,
    ) -> dict[str, Any]:
        self._require_active_mailbox(
            account_id=account_id, workspace_id=workspace_id, mailbox_id=mailbox_id
        )
        recipients = [_required(value, "recipient") for value in to_recipients]
        if not recipients:
            raise ValueError("At least one recipient is required.")
        return self._email_store.create_send_request(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
            idempotency_key=_required(idempotency_key, "idempotencyKey"),
            recipients=recipients,
            subject=_required(subject, "subject"),
            body_text=_required(body, "body"),
        )

    def confirm_send(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        pending_request_id: str,
        approve: bool,
    ) -> dict[str, Any]:
        claim = self._email_store.claim_send_request(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
            pending_request_id=pending_request_id,
            approve=approve,
        )
        if claim.get("status") != "sending":
            return claim
        credentials = self._credentials_for_active_mailbox(
            account_id=account_id, workspace_id=workspace_id, mailbox_id=mailbox_id
        )
        try:
            self._provider.send_message(
                credentials=credentials,
                to_recipients=list(claim["recipients"]),
                subject=str(claim["subject"]),
                body=str(claim["bodyText"]),
            )
        except Exception as exc:
            error_code, _ = support_safe_provider_error(exc)
            self._email_store.finish_send_request(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=mailbox_id,
                pending_request_id=pending_request_id,
                sent=False,
                error_code=error_code,
            )
            return {"status": "failed", "code": error_code}
        self._email_store.finish_send_request(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
            pending_request_id=pending_request_id,
            sent=True,
        )
        return {"status": "sent", "pendingRequestId": pending_request_id}

    def set_mailbox_lifecycle(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        lifecycle_status: str,
    ) -> dict[str, Any] | None:
        return self._email_store.set_mailbox_lifecycle(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
            lifecycle_status=lifecycle_status,
        )

    def permanently_remove_mailbox_local(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        confirmation_text: str,
    ) -> dict[str, Any] | None:
        removed = self._email_store.permanently_remove_mailbox_local(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
            confirmation_text=confirmation_text,
        )
        if not removed:
            return None
        credential_id = str(removed.pop("providerCredentialId"))
        self._store.delete_provider_credential_by_id(
            account_id=account_id,
            workspace_id=workspace_id,
            provider_credential_id=credential_id,
        )
        return removed

    def _sync_folder(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        credentials: VaultEmailCredentials,
        provider,
        folder: VaultEmailFolder,
        page_size: int,
        max_pages: int,
        max_attachment_bytes: int,
    ) -> tuple[bool, int, int]:
        initial_folder_id = self._email_store.upsert_folder(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
            folder=folder,
        )
        cursor = self._email_store.get_cursor(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
            folder_id=initial_folder_id,
            cursor_kind="backfill",
        )
        before_uid = cursor.get("nextBeforeUid") if cursor and not cursor.get("backfillComplete") else None
        if cursor and cursor.get("backfillComplete"):
            incremental = self._email_store.get_cursor(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=mailbox_id,
                folder_id=initial_folder_id,
                cursor_kind="incremental",
            )
            after_uid = incremental.get("lastUid") if incremental else None
            page = provider.fetch_message_page(
                credentials=credentials,
                folder=folder,
                after_uid=after_uid,
                limit=page_size,
                max_attachment_bytes=max_attachment_bytes,
            )
            reconcile_folder_snapshot = getattr(
                self._email_store, "reconcile_folder_snapshot", None
            )
            if (
                callable(reconcile_folder_snapshot)
                and page.provider_uid_flags is not None
            ):
                reconcile_folder_snapshot(
                    account_id=account_id,
                    workspace_id=workspace_id,
                    mailbox_id=mailbox_id,
                    folder_id=initial_folder_id,
                    uid_validity=page.uid_validity,
                    provider_uid_flags=page.provider_uid_flags,
                )
            complete, stored_messages, stored_attachments = self._store_page(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=mailbox_id,
                folder=folder,
                folder_record_id=initial_folder_id,
                page=page,
                cursor_kind="incremental",
                backfill_complete=True,
            )
            self._email_store.upsert_cursor(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=mailbox_id,
                folder_id=initial_folder_id,
                cursor_kind="incremental",
                uid_validity=page.uid_validity,
                last_uid=max((*page.provider_uids, int(after_uid or 0))),
                next_before_uid=None,
                backfill_complete=True,
            )
            return complete, stored_messages, stored_attachments
        stored_messages = stored_attachments = 0
        complete = False
        for _ in range(max(1, min(int(max_pages), 100))):
            page = provider.fetch_message_page(
                credentials=credentials,
                folder=folder,
                before_uid=before_uid,
                limit=page_size,
                max_attachment_bytes=max_attachment_bytes,
            )
            complete, page_messages, page_attachments = self._store_page(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=mailbox_id,
                folder=folder,
                folder_record_id=initial_folder_id,
                page=page,
                cursor_kind="backfill",
                backfill_complete=page.complete,
            )
            stored_messages += page_messages
            stored_attachments += page_attachments
            before_uid = page.next_before_uid
            if complete:
                break
        if complete:
            last_uid = (
                max(0, int(page.uid_next) - 1)
                if page.uid_next is not None
                else max(page.provider_uids, default=0)
            )
            self._email_store.upsert_cursor(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=mailbox_id,
                folder_id=initial_folder_id,
                cursor_kind="incremental",
                uid_validity=page.uid_validity,
                last_uid=last_uid,
                next_before_uid=None,
                backfill_complete=True,
            )
        return complete, stored_messages, stored_attachments

    def _store_page(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        folder: VaultEmailFolder,
        folder_record_id: str,
        page,
        cursor_kind: str,
        backfill_complete: bool,
    ) -> tuple[bool, int, int]:
        folder_record_id = self._email_store.upsert_folder(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
            folder=folder,
            uid_validity=page.uid_validity,
            uid_next=page.uid_next,
            reconciliation_status="complete" if backfill_complete else "backfilling",
        )
        attachment_count = 0
        for provider_uid, message in zip(page.provider_uids, page.messages, strict=True):
            self._email_store.upsert_message(
                account_id=account_id,
                workspace_id=workspace_id,
                mailbox_id=mailbox_id,
                folder_record_id=folder_record_id,
                uid_validity=page.uid_validity,
                provider_uid=provider_uid,
                message=message,
            )
            attachment_count += len(message.attachments)
        self._email_store.upsert_cursor(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
            folder_id=folder_record_id,
            cursor_kind=cursor_kind,
            uid_validity=page.uid_validity,
            last_uid=max(page.provider_uids, default=None),
            next_before_uid=page.next_before_uid,
            backfill_complete=backfill_complete,
        )
        return backfill_complete, len(page.messages), attachment_count

    def _require_active_mailbox(
        self, *, account_id: str, workspace_id: str, mailbox_id: str
    ) -> dict[str, Any]:
        mailbox = self._email_store.get_mailbox(
            account_id=account_id,
            workspace_id=workspace_id,
            mailbox_id=mailbox_id,
        )
        if not mailbox:
            raise PermissionError("Mailbox scope was not authorized.")
        if mailbox.get("lifecycleStatus") != "active":
            raise RuntimeError("Mailbox is not active.")
        return mailbox

    def _credentials_for_active_mailbox(
        self, *, account_id: str, workspace_id: str, mailbox_id: str
    ) -> VaultEmailCredentials:
        mailbox = self._require_active_mailbox(
            account_id=account_id, workspace_id=workspace_id, mailbox_id=mailbox_id
        )
        return self._credentials_for_mailbox(
            account_id=account_id, workspace_id=workspace_id, mailbox=mailbox
        )

    def _credentials_for_mailbox(
        self, *, account_id: str, workspace_id: str, mailbox: Mapping[str, Any]
    ) -> VaultEmailCredentials:
        provider_kind = "email"
        credential_id = f"{provider_kind}:{mailbox['mailboxAccountId']}"
        record = self._store.get_provider_credential_by_id(
            account_id=account_id,
            workspace_id=workspace_id,
            provider_credential_id=credential_id,
        )
        payload = record.get("sourcePayload") if isinstance(record, Mapping) else None
        if not isinstance(payload, Mapping):
            raise RuntimeError("Mailbox credentials are unavailable.")
        credentials_payload = payload.get("credentials")
        if not isinstance(credentials_payload, Mapping):
            raise RuntimeError("Mailbox credentials are unavailable.")
        return credentials_from_payload(credentials_payload)


def credentials_from_payload(payload: Mapping[str, Any]) -> VaultEmailCredentials:
    imap = payload.get("imap") if isinstance(payload.get("imap"), Mapping) else {}
    smtp = payload.get("smtp") if isinstance(payload.get("smtp"), Mapping) else {}
    return VaultEmailCredentials(
        email_address=_required(payload.get("emailAddress") or payload.get("email_address"), "emailAddress"),
        imap_host=_required(imap.get("host") or payload.get("imapHost"), "imap.host"),
        imap_port=_port(imap.get("port") or payload.get("imapPort"), 993),
        imap_username=_required(imap.get("username") or payload.get("imapUsername"), "imap.username"),
        imap_password=_required(imap.get("password") or payload.get("imapPassword"), "imap.password"),
        imap_use_tls=_boolean(imap.get("useTls", payload.get("imapUseTls")), True),
        smtp_host=_required(smtp.get("host") or payload.get("smtpHost"), "smtp.host"),
        smtp_port=_port(smtp.get("port") or payload.get("smtpPort"), 465),
        smtp_username=_required(smtp.get("username") or payload.get("smtpUsername"), "smtp.username"),
        smtp_password=_required(smtp.get("password") or payload.get("smtpPassword"), "smtp.password"),
        smtp_use_tls=_boolean(smtp.get("useTls", payload.get("smtpUseTls")), True),
    )


def support_safe_provider_error(exc: Exception) -> tuple[str, str]:
    class_name = exc.__class__.__name__.casefold()
    if "auth" in class_name or "login" in str(exc).casefold():
        return "email_provider_auth_failed", "authentication"
    if isinstance(exc, TimeoutError) or "timeout" in class_name:
        return "email_provider_timeout", "transport"
    if isinstance(exc, (ConnectionError, OSError)):
        return "email_provider_unavailable", "transport"
    if isinstance(exc, PermissionError):
        return "email_scope_denied", "authorization"
    return "email_provider_operation_failed", "provider"


def _mailbox_role(value: str) -> str:
    normalized = _required(value, "mailboxRole")
    if normalized not in {"normal_email", "agent_mail"}:
        raise ValueError("Unsupported mailbox role.")
    return normalized


def _required(value: Any, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field} is required.")
    return normalized


def _port(value: Any, default: int) -> int:
    resolved = int(value or default)
    if resolved < 1 or resolved > 65535:
        raise ValueError("Email provider port is invalid.")
    return resolved


def _boolean(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() in {"1", "true", "yes", "on"}


__all__ = [
    "VaultEmailService",
    "VaultEmailSyncSummary",
    "credentials_from_payload",
    "support_safe_provider_error",
]
