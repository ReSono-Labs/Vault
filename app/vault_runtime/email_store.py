from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from psycopg.types.json import Jsonb

from app.vault_runtime.email_provider import VaultEmailFolder, VaultEmailMessage


TRASH_SPECIAL_USE = "trash"


def mailbox_account_id(*, workspace_id: str, email_address: str) -> str:
    return f"vault-email-mailbox-{uuid5(NAMESPACE_URL, f'{workspace_id}:{email_address.casefold()}')}"


def folder_id(*, mailbox_id: str, provider_folder_key: str) -> str:
    return f"vault-email-folder-{uuid5(NAMESPACE_URL, f'{mailbox_id}:{provider_folder_key}')}"


def message_id(*, folder_record_id: str, uid_validity: int, provider_uid: int) -> str:
    return f"vault-email-message-{uuid5(NAMESPACE_URL, f'{folder_record_id}:{uid_validity}:{provider_uid}')}"


class VaultPostgresEmailStore:
    """Canonical, scope-bound Email records inside the existing Vault database."""

    def __init__(self, conn) -> None:
        self._conn = conn

    def upsert_mailbox(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_role: str,
        email_address: str,
        provider_credential_id: str,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        role = _mailbox_role(mailbox_role)
        normalized_address = _required(email_address, "email_address").casefold()
        resolved_id = mailbox_account_id(workspace_id=workspace_id, email_address=normalized_address)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM vault_private.local_workspace_memberships m
                JOIN vault_private.local_users u ON u.user_id=m.user_id
                JOIN vault_private.local_workspaces w ON w.workspace_id=m.workspace_id
                WHERE m.workspace_id=%s AND m.user_id=%s AND m.status='active'
                  AND u.status='active' AND w.status='active'
                """,
                (workspace_id, account_id),
            )
            existing_workspace = cur.fetchone()
            if existing_workspace is None:
                raise PermissionError("Workspace scope was not authorized.")
            cur.execute(
                """
                INSERT INTO vault_private.vault_email_mailbox_accounts (
                  vault_email_mailbox_account_id, account_id, workspace_id, mailbox_role,
                  provider_kind, email_address, display_name, provider_credential_id,
                  lifecycle_status, sync_enabled, sync_status, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active', true, 'pending', now())
                ON CONFLICT (workspace_id, email_address) DO UPDATE
                SET account_id = EXCLUDED.account_id,
                    mailbox_role = EXCLUDED.mailbox_role,
                    provider_kind = EXCLUDED.provider_kind,
                    display_name = EXCLUDED.display_name,
                    provider_credential_id = EXCLUDED.provider_credential_id,
                    lifecycle_status = 'active',
                    sync_enabled = true,
                    sync_status = 'pending',
                    sync_error_code = NULL,
                    sync_error_class = NULL,
                    updated_at = now()
                RETURNING vault_email_mailbox_account_id, mailbox_role, email_address,
                          display_name, lifecycle_status, sync_enabled, sync_status
                """,
                (
                    resolved_id,
                    account_id,
                    workspace_id,
                    role,
                    "email",
                    normalized_address,
                    display_name,
                    _required(provider_credential_id, "provider_credential_id"),
                ),
            )
            row = cur.fetchone()
        self._conn.commit()
        return _mailbox_row(row)

    def get_mailbox(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        mailbox_role: str | None = None,
    ) -> dict[str, Any] | None:
        params: list[Any] = [mailbox_id, account_id, workspace_id]
        role_clause = ""
        if mailbox_role:
            role_clause = " AND mailbox_role = %s"
            params.append(_mailbox_role(mailbox_role))
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT vault_email_mailbox_account_id, mailbox_role, email_address,
                       display_name, lifecycle_status, sync_enabled, sync_status
                FROM vault_private.vault_email_mailbox_accounts
                WHERE vault_email_mailbox_account_id = %s
                  AND account_id = %s
                  AND workspace_id = %s
                  {role_clause}
                """,
                tuple(params),
            )
            row = cur.fetchone()
        return _mailbox_row(row) if row else None

    def list_mailboxes(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_role: str | None = None,
        include_removed: bool = False,
    ) -> list[dict[str, Any]]:
        clauses = ["account_id = %s", "workspace_id = %s"]
        params: list[Any] = [account_id, workspace_id]
        if mailbox_role:
            clauses.append("mailbox_role = %s")
            params.append(_mailbox_role(mailbox_role))
        if not include_removed:
            clauses.append("lifecycle_status <> 'removed'")
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT vault_email_mailbox_account_id, mailbox_role, email_address,
                       display_name, lifecycle_status, sync_enabled, sync_status
                FROM vault_private.vault_email_mailbox_accounts
                WHERE {' AND '.join(clauses)}
                ORDER BY email_address
                """,
                tuple(params),
            )
            rows = cur.fetchall()
        return [_mailbox_row(row) for row in rows]

    def list_sync_candidates(
        self, *, due_before: datetime, limit: int
    ) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT account_id, workspace_id, vault_email_mailbox_account_id,
                       mailbox_role, sync_status
                FROM vault_private.vault_email_mailbox_accounts
                WHERE lifecycle_status = 'active'
                  AND sync_enabled = true
                  AND (last_sync_started_at IS NULL OR last_sync_started_at <= %s)
                ORDER BY last_sync_started_at ASC NULLS FIRST, updated_at ASC
                LIMIT %s
                """,
                (due_before, max(1, min(int(limit), 100))),
            )
            rows = cur.fetchall()
        return [
            {
                "accountId": row[0],
                "workspaceId": row[1],
                "mailboxAccountId": row[2],
                "mailboxRole": row[3],
                "syncStatus": row[4],
            }
            for row in rows
        ]

    def set_mailbox_lifecycle(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        lifecycle_status: str,
    ) -> dict[str, Any] | None:
        if lifecycle_status not in {"active", "disabled", "disconnected"}:
            raise ValueError("Unsupported non-destructive mailbox lifecycle state.")
        sync_status = "disconnected" if lifecycle_status == "disconnected" else "stale"
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE vault_private.vault_email_mailbox_accounts
                SET lifecycle_status = %s,
                    sync_enabled = %s,
                    sync_status = %s,
                    updated_at = now()
                WHERE vault_email_mailbox_account_id = %s
                  AND account_id = %s
                  AND workspace_id = %s
                RETURNING vault_email_mailbox_account_id, mailbox_role, email_address,
                          display_name, lifecycle_status, sync_enabled, sync_status
                """,
                (
                    lifecycle_status,
                    lifecycle_status == "active",
                    sync_status,
                    mailbox_id,
                    account_id,
                    workspace_id,
                ),
            )
            row = cur.fetchone()
        self._conn.commit()
        return _mailbox_row(row) if row else None

    def permanently_remove_mailbox_local(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        confirmation_text: str,
    ) -> dict[str, Any] | None:
        if confirmation_text != "REMOVE FROM RESONO":
            raise PermissionError("Permanent local mailbox removal requires exact confirmation.")
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT provider_credential_id
                FROM vault_private.vault_email_mailbox_accounts
                WHERE vault_email_mailbox_account_id = %s
                  AND account_id = %s AND workspace_id = %s
                FOR UPDATE
                """,
                (mailbox_id, account_id, workspace_id),
            )
            row = cur.fetchone()
            if not row:
                return None
            credential_id = str(row[0])
            for statement in (
                "DELETE FROM vault_private.vault_email_attachments WHERE account_id = %s AND workspace_id = %s AND mailbox_account_id = %s",
                "DELETE FROM vault_private.vault_email_send_requests WHERE account_id = %s AND workspace_id = %s AND mailbox_account_id = %s",
                "DELETE FROM vault_private.vault_email_sync_cursors WHERE account_id = %s AND workspace_id = %s AND mailbox_account_id = %s",
                "DELETE FROM vault_private.vault_email_sync_runs WHERE account_id = %s AND workspace_id = %s AND mailbox_account_id = %s",
                "DELETE FROM vault_private.vault_email_messages WHERE account_id = %s AND workspace_id = %s AND mailbox_account_id = %s",
                "DELETE FROM vault_private.vault_email_folders WHERE account_id = %s AND workspace_id = %s AND mailbox_account_id = %s",
            ):
                cur.execute(statement, (account_id, workspace_id, mailbox_id))
            cur.execute(
                """
                UPDATE vault_private.vault_email_mailbox_accounts
                SET lifecycle_status = 'removed', sync_enabled = false,
                    sync_status = 'disconnected', sync_error_code = NULL,
                    sync_error_class = NULL, updated_at = now()
                WHERE vault_email_mailbox_account_id = %s
                  AND account_id = %s AND workspace_id = %s
                RETURNING vault_email_mailbox_account_id, mailbox_role, email_address,
                          display_name, lifecycle_status, sync_enabled, sync_status
                """,
                (mailbox_id, account_id, workspace_id),
            )
            removed = cur.fetchone()
        self._conn.commit()
        result = _mailbox_row(removed)
        result["providerCredentialId"] = credential_id
        return result

    def upsert_folder(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        folder: VaultEmailFolder,
        uid_validity: int | None = None,
        uid_next: int | None = None,
        reconciliation_status: str = "backfilling",
    ) -> str:
        resolved_id = folder_id(mailbox_id=mailbox_id, provider_folder_key=folder.provider_folder_key)
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO vault_private.vault_email_folders (
                  vault_email_folder_id, account_id, workspace_id, mailbox_account_id,
                  provider_folder_key, display_name, delimiter, special_use,
                  provider_flags_jsonb, uid_validity, uid_next, provider_present,
                  provider_last_seen_at, reconciliation_status, updated_at
                )
                SELECT %s, %s, %s, vault_email_mailbox_account_id, %s, %s, %s, %s, %s, %s, %s,
                       true, now(), %s, now()
                FROM vault_private.vault_email_mailbox_accounts
                WHERE vault_email_mailbox_account_id = %s
                  AND account_id = %s AND workspace_id = %s
                  AND lifecycle_status <> 'removed'
                ON CONFLICT (mailbox_account_id, provider_folder_key) DO UPDATE
                SET display_name = EXCLUDED.display_name,
                    delimiter = EXCLUDED.delimiter,
                    special_use = EXCLUDED.special_use,
                    provider_flags_jsonb = EXCLUDED.provider_flags_jsonb,
                    uid_validity = COALESCE(EXCLUDED.uid_validity, vault_email_folders.uid_validity),
                    uid_next = COALESCE(EXCLUDED.uid_next, vault_email_folders.uid_next),
                    provider_present = true,
                    provider_last_seen_at = now(),
                    reconciliation_status = EXCLUDED.reconciliation_status,
                    updated_at = now()
                RETURNING vault_email_folder_id
                """,
                (
                    resolved_id,
                    account_id,
                    workspace_id,
                    folder.provider_folder_key,
                    folder.display_name,
                    folder.delimiter,
                    folder.special_use,
                    Jsonb(list(folder.flags)),
                    uid_validity,
                    uid_next,
                    reconciliation_status,
                    mailbox_id,
                    account_id,
                    workspace_id,
                ),
            )
            row = cur.fetchone()
        self._conn.commit()
        if not row:
            raise PermissionError("Mailbox scope was not authorized.")
        return str(row[0])

    def list_folders(
        self, *, account_id: str, workspace_id: str, mailbox_id: str
    ) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT vault_email_folder_id, provider_folder_key, display_name,
                       delimiter, special_use, provider_flags_jsonb,
                       uid_validity, uid_next, message_count, unread_count,
                       reconciliation_status
                FROM vault_private.vault_email_folders
                WHERE account_id = %s AND workspace_id = %s AND mailbox_account_id = %s
                  AND provider_present = true
                  AND lower(coalesce(special_use, '')) <> %s
                ORDER BY CASE WHEN special_use = 'inbox' THEN 0 ELSE 1 END, display_name
                """,
                (account_id, workspace_id, mailbox_id, TRASH_SPECIAL_USE),
            )
            rows = cur.fetchall()
        return [
            {
                "folderId": row[0],
                "providerFolderKey": row[1],
                "displayName": row[2],
                "delimiter": row[3],
                "specialUse": row[4],
                "flags": list(row[5] or []),
                "uidValidity": row[6],
                "uidNext": row[7],
                "messageCount": row[8],
                "unreadCount": row[9],
                "reconciliationStatus": row[10],
            }
            for row in rows
        ]

    def reconcile_folder_inventory(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        provider_folder_keys: list[str],
    ) -> None:
        normalized_keys = sorted(
            {str(value).strip() for value in provider_folder_keys if str(value).strip()}
        )
        if not normalized_keys:
            raise RuntimeError("Provider returned no mailbox folders to reconcile.")
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE vault_private.vault_email_folders
                SET provider_present = (provider_folder_key = ANY(%s)),
                    provider_last_seen_at = CASE
                      WHEN provider_folder_key = ANY(%s) THEN now()
                      ELSE provider_last_seen_at
                    END,
                    updated_at = now()
                WHERE account_id = %s AND workspace_id = %s
                  AND mailbox_account_id = %s
                """,
                (
                    normalized_keys,
                    normalized_keys,
                    account_id,
                    workspace_id,
                    mailbox_id,
                ),
            )
            cur.execute(
                """
                UPDATE vault_private.vault_email_messages AS message
                SET provider_present = false, updated_at = now()
                FROM vault_private.vault_email_folders AS folder
                WHERE message.folder_id = folder.vault_email_folder_id
                  AND message.account_id = %s AND message.workspace_id = %s
                  AND message.mailbox_account_id = %s
                  AND folder.account_id = %s AND folder.workspace_id = %s
                  AND folder.mailbox_account_id = %s
                  AND folder.provider_present = false
                  AND message.provider_present = true
                """,
                (
                    account_id,
                    workspace_id,
                    mailbox_id,
                    account_id,
                    workspace_id,
                    mailbox_id,
                ),
            )
        self._conn.commit()

    def reconcile_folder_snapshot(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        folder_id: str,
        uid_validity: int,
        provider_uid_flags: tuple[tuple[int, tuple[str, ...]], ...],
    ) -> None:
        snapshots = [
            (list(flags), "\\Seen" not in flags, int(uid))
            for uid, flags in provider_uid_flags
        ]
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE vault_private.vault_email_messages
                SET provider_present = false, updated_at = now()
                WHERE account_id = %s AND workspace_id = %s
                  AND mailbox_account_id = %s AND folder_id = %s
                  AND provider_present = true
                """,
                (account_id, workspace_id, mailbox_id, folder_id),
            )
            if snapshots:
                cur.executemany(
                    """
                    UPDATE vault_private.vault_email_messages
                    SET flags_jsonb = %s,
                        is_unread = %s,
                        provider_present = true,
                        provider_last_seen_at = now(),
                        updated_at = now()
                    WHERE account_id = %s AND workspace_id = %s
                      AND mailbox_account_id = %s AND folder_id = %s
                      AND provider_uid_validity = %s AND provider_uid = %s
                    """,
                    [
                        (
                            Jsonb(flags),
                            is_unread,
                            account_id,
                            workspace_id,
                            mailbox_id,
                            folder_id,
                            int(uid_validity),
                            uid,
                        )
                        for flags, is_unread, uid in snapshots
                    ],
                )
        self._conn.commit()

    def upsert_message(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        folder_record_id: str,
        uid_validity: int,
        provider_uid: int,
        message: VaultEmailMessage,
    ) -> str:
        resolved_id = message_id(
            folder_record_id=folder_record_id,
            uid_validity=uid_validity,
            provider_uid=provider_uid,
        )
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO vault_private.vault_email_messages (
                  vault_email_message_id, account_id, workspace_id, mailbox_account_id,
                  folder_id, provider_uid_validity, provider_uid, provider_message_id,
                  from_jsonb, to_jsonb, subject, snippet, body_text, flags_jsonb,
                  is_unread, is_archived, provider_present, provider_last_seen_at,
                  content_complete, received_at, updated_at
                )
                SELECT %s, %s, %s, %s, vault_email_folder_id, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, %s, %s, true, now(), true, %s, now()
                FROM vault_private.vault_email_folders
                WHERE vault_email_folder_id = %s
                  AND account_id = %s AND workspace_id = %s AND mailbox_account_id = %s
                ON CONFLICT (folder_id, provider_uid_validity, provider_uid) DO UPDATE
                SET provider_message_id = EXCLUDED.provider_message_id,
                    from_jsonb = EXCLUDED.from_jsonb,
                    to_jsonb = EXCLUDED.to_jsonb,
                    subject = EXCLUDED.subject,
                    snippet = EXCLUDED.snippet,
                    body_text = EXCLUDED.body_text,
                    flags_jsonb = EXCLUDED.flags_jsonb,
                    is_unread = EXCLUDED.is_unread,
                    is_archived = EXCLUDED.is_archived,
                    provider_present = true,
                    provider_last_seen_at = now(),
                    content_complete = EXCLUDED.content_complete,
                    received_at = EXCLUDED.received_at,
                    updated_at = now()
                RETURNING vault_email_message_id
                """,
                (
                    resolved_id,
                    account_id,
                    workspace_id,
                    mailbox_id,
                    int(uid_validity),
                    int(provider_uid),
                    message.message_header_id or message.provider_message_id,
                    Jsonb(_address(message.from_display, message.from_email)),
                    Jsonb(_address(message.to_display, message.to_email)),
                    message.subject,
                    message.snippet,
                    message.body_text,
                    Jsonb(["\\Seen"] if not message.is_unread else []),
                    message.is_unread,
                    message.is_archived,
                    message.received_at,
                    folder_record_id,
                    account_id,
                    workspace_id,
                    mailbox_id,
                ),
            )
            row = cur.fetchone()
            if not row:
                raise PermissionError("Folder scope was not authorized.")
            for attachment in message.attachments:
                attachment_id = f"vault-email-attachment-{uuid5(NAMESPACE_URL, f'{resolved_id}:{attachment.provider_part_key}')}"
                cur.execute(
                    """
                    INSERT INTO vault_private.vault_email_attachments (
                      vault_email_attachment_id, account_id, workspace_id, mailbox_account_id,
                      message_id, provider_part_key, file_name, content_type,
                      content_disposition, content_id, size_bytes, sha256,
                      content_bytes, content_complete, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (message_id, provider_part_key) DO UPDATE
                    SET file_name = EXCLUDED.file_name,
                        content_type = EXCLUDED.content_type,
                        content_disposition = EXCLUDED.content_disposition,
                        content_id = EXCLUDED.content_id,
                        size_bytes = EXCLUDED.size_bytes,
                        sha256 = EXCLUDED.sha256,
                        content_bytes = EXCLUDED.content_bytes,
                        content_complete = EXCLUDED.content_complete,
                        updated_at = now()
                    """,
                    (
                        attachment_id,
                        account_id,
                        workspace_id,
                        mailbox_id,
                        resolved_id,
                        attachment.provider_part_key,
                        attachment.file_name,
                        attachment.content_type,
                        attachment.content_disposition,
                        attachment.content_id,
                        attachment.size_bytes,
                        attachment.sha256,
                        attachment.content_bytes,
                        attachment.content_complete,
                    ),
                )
        self._conn.commit()
        return resolved_id

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
        clauses = [
            "message.account_id = %s",
            "message.workspace_id = %s",
            "message.mailbox_account_id = %s",
            "message.provider_present = true",
            """
            EXISTS (
                SELECT 1
                FROM vault_private.vault_email_folders AS folder
                WHERE folder.vault_email_folder_id = message.folder_id
                  AND folder.account_id = message.account_id
                  AND folder.workspace_id = message.workspace_id
                  AND folder.mailbox_account_id = message.mailbox_account_id
                  AND lower(coalesce(folder.special_use, '')) <> %s
            )
            """,
        ]
        params: list[Any] = [account_id, workspace_id, mailbox_id, TRASH_SPECIAL_USE]
        if folder_id:
            clauses.append("message.folder_id = %s")
            params.append(folder_id)
        if unread_only:
            clauses.append("message.is_unread = true")
        if query:
            clauses.append(
                "to_tsvector('simple', coalesce(message.subject, '') || ' ' || coalesce(message.snippet, '') || ' ' || coalesce(message.body_text, '')) "
                "@@ plainto_tsquery('simple', %s)"
            )
            params.append(query)
        params.append(max(1, min(int(limit), 100)))
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT vault_email_message_id, folder_id, provider_uid, provider_message_id,
                       from_jsonb, to_jsonb, subject, snippet, body_text,
                       is_unread, is_archived, received_at
                FROM vault_private.vault_email_messages AS message
                WHERE {' AND '.join(clauses)}
                ORDER BY message.received_at DESC NULLS LAST, message.provider_uid DESC
                LIMIT %s
                """,
                tuple(params),
            )
            rows = cur.fetchall()
        return [_message_row(row) for row in rows]

    def get_message(
        self, *, account_id: str, workspace_id: str, mailbox_id: str, message_id: str
    ) -> dict[str, Any] | None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT vault_email_message_id, folder_id, provider_uid, provider_message_id,
                       from_jsonb, to_jsonb, subject, snippet, body_text,
                       is_unread, is_archived, received_at
                FROM vault_private.vault_email_messages AS message
                WHERE message.vault_email_message_id = %s AND message.account_id = %s
                  AND message.workspace_id = %s AND message.mailbox_account_id = %s
                  AND message.provider_present = true
                  AND EXISTS (
                    SELECT 1
                    FROM vault_private.vault_email_folders AS folder
                    WHERE folder.vault_email_folder_id = message.folder_id
                      AND folder.account_id = message.account_id
                      AND folder.workspace_id = message.workspace_id
                      AND folder.mailbox_account_id = message.mailbox_account_id
                      AND lower(coalesce(folder.special_use, '')) <> %s
                  )
                """,
                (message_id, account_id, workspace_id, mailbox_id, TRASH_SPECIAL_USE),
            )
            row = cur.fetchone()
        return _message_row(row) if row else None

    def get_attachment(
        self, *, account_id: str, workspace_id: str, mailbox_id: str, attachment_id: str
    ) -> dict[str, Any] | None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT vault_email_attachment_id, message_id, file_name, content_type,
                       size_bytes, sha256, content_bytes, content_complete
                FROM vault_private.vault_email_attachments AS attachment
                WHERE vault_email_attachment_id = %s AND account_id = %s
                  AND workspace_id = %s AND mailbox_account_id = %s
                  AND EXISTS (
                    SELECT 1
                    FROM vault_private.vault_email_messages AS message
                    WHERE message.vault_email_message_id = attachment.message_id
                      AND message.account_id = attachment.account_id
                      AND message.workspace_id = attachment.workspace_id
                      AND message.mailbox_account_id = attachment.mailbox_account_id
                      AND message.provider_present = true
                      AND EXISTS (
                        SELECT 1
                        FROM vault_private.vault_email_folders AS folder
                        WHERE folder.vault_email_folder_id = message.folder_id
                          AND folder.account_id = message.account_id
                          AND folder.workspace_id = message.workspace_id
                          AND folder.mailbox_account_id = message.mailbox_account_id
                          AND lower(coalesce(folder.special_use, '')) <> %s
                      )
                  )
                """,
                (attachment_id, account_id, workspace_id, mailbox_id, TRASH_SPECIAL_USE),
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "attachmentId": row[0],
            "messageId": row[1],
            "fileName": row[2],
            "contentType": row[3],
            "sizeBytes": row[4],
            "sha256": row[5],
            "contentBytes": bytes(row[6]) if row[6] is not None else None,
            "contentComplete": row[7],
        }

    def create_send_request(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        idempotency_key: str,
        recipients: list[str],
        subject: str,
        body_text: str,
        expires_in_seconds: int = 600,
    ) -> dict[str, Any]:
        request_id = f"vault-email-send-{uuid5(NAMESPACE_URL, f'{mailbox_id}:{idempotency_key}')}"
        confirmation_hash = sha256(
            f"{request_id}:{mailbox_id}:{idempotency_key}".encode("utf-8")
        ).hexdigest()
        expires_at = datetime.now(UTC) + timedelta(
            seconds=max(60, min(int(expires_in_seconds), 3600))
        )
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO vault_private.vault_email_send_requests (
                  vault_email_send_request_id, account_id, workspace_id, mailbox_account_id,
                  idempotency_key, recipients_jsonb, subject, body_text, status,
                  confirmation_hash, expires_at, updated_at
                )
                SELECT %s, %s, %s, vault_email_mailbox_account_id, %s, %s, %s, %s,
                       'pending_confirmation', %s, %s, now()
                FROM vault_private.vault_email_mailbox_accounts
                WHERE vault_email_mailbox_account_id = %s AND account_id = %s
                  AND workspace_id = %s AND lifecycle_status = 'active'
                ON CONFLICT (mailbox_account_id, idempotency_key) DO UPDATE
                SET updated_at = now()
                RETURNING vault_email_send_request_id, status, expires_at
                """,
                (
                    request_id,
                    account_id,
                    workspace_id,
                    idempotency_key,
                    Jsonb(recipients),
                    subject,
                    body_text,
                    confirmation_hash,
                    expires_at,
                    mailbox_id,
                    account_id,
                    workspace_id,
                ),
            )
            row = cur.fetchone()
        self._conn.commit()
        if not row:
            raise PermissionError("Mailbox scope was not authorized.")
        return {
            "pendingRequestId": row[0],
            "status": row[1],
            "expiresAt": _json_datetime(row[2]),
        }

    def claim_send_request(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        pending_request_id: str,
        approve: bool,
    ) -> dict[str, Any]:
        with self._conn.cursor() as cur:
            if not approve:
                cur.execute(
                    """
                    UPDATE vault_private.vault_email_send_requests
                    SET status = 'cancelled', updated_at = now()
                    WHERE vault_email_send_request_id = %s AND account_id = %s
                      AND workspace_id = %s AND mailbox_account_id = %s
                      AND status = 'pending_confirmation'
                    RETURNING vault_email_send_request_id
                    """,
                    (pending_request_id, account_id, workspace_id, mailbox_id),
                )
                row = cur.fetchone()
                self._conn.commit()
                return {"status": "cancelled", "pendingRequestId": row[0]} if row else {"status": "not_pending"}
            cur.execute(
                """
                UPDATE vault_private.vault_email_send_requests
                SET status = CASE WHEN expires_at > now() THEN 'sending' ELSE 'expired' END,
                    updated_at = now()
                WHERE vault_email_send_request_id = %s AND account_id = %s
                  AND workspace_id = %s AND mailbox_account_id = %s
                  AND status = 'pending_confirmation'
                RETURNING vault_email_send_request_id, status, recipients_jsonb, subject, body_text
                """,
                (pending_request_id, account_id, workspace_id, mailbox_id),
            )
            row = cur.fetchone()
        self._conn.commit()
        if not row:
            return {"status": "not_pending"}
        return {
            "pendingRequestId": row[0],
            "status": row[1],
            "recipients": list(row[2] or []),
            "subject": row[3],
            "bodyText": row[4],
        }

    def finish_send_request(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        pending_request_id: str,
        sent: bool,
        error_code: str | None = None,
    ) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE vault_private.vault_email_send_requests
                SET status = %s, support_safe_error_code = %s, updated_at = now()
                WHERE vault_email_send_request_id = %s AND account_id = %s
                  AND workspace_id = %s AND mailbox_account_id = %s
                  AND status = 'sending'
                """,
                (
                    "sent" if sent else "failed",
                    error_code,
                    pending_request_id,
                    account_id,
                    workspace_id,
                    mailbox_id,
                ),
            )
        self._conn.commit()

    def upsert_cursor(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        folder_id: str,
        cursor_kind: str,
        uid_validity: int,
        last_uid: int | None,
        next_before_uid: int | None,
        backfill_complete: bool,
    ) -> None:
        if cursor_kind not in {"backfill", "incremental"}:
            raise ValueError("Unsupported Email cursor kind.")
        cursor_id = f"vault-email-cursor-{uuid5(NAMESPACE_URL, f'{folder_id}:{cursor_kind}')}"
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO vault_private.vault_email_sync_cursors (
                  vault_email_sync_cursor_id, account_id, workspace_id, mailbox_account_id,
                  folder_id, cursor_kind, uid_validity, last_uid, next_before_uid,
                  backfill_complete, cursor_jsonb, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '{}'::jsonb, now())
                ON CONFLICT (folder_id, cursor_kind) DO UPDATE
                SET uid_validity = EXCLUDED.uid_validity,
                    last_uid = EXCLUDED.last_uid,
                    next_before_uid = EXCLUDED.next_before_uid,
                    backfill_complete = EXCLUDED.backfill_complete,
                    updated_at = now()
                """,
                (
                    cursor_id,
                    account_id,
                    workspace_id,
                    mailbox_id,
                    folder_id,
                    cursor_kind,
                    uid_validity,
                    last_uid,
                    next_before_uid,
                    backfill_complete,
                ),
            )
        self._conn.commit()

    def get_cursor(
        self, *, account_id: str, workspace_id: str, mailbox_id: str, folder_id: str, cursor_kind: str
    ) -> dict[str, Any] | None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT uid_validity, last_uid, next_before_uid, backfill_complete, updated_at
                FROM vault_private.vault_email_sync_cursors
                WHERE account_id = %s AND workspace_id = %s AND mailbox_account_id = %s
                  AND folder_id = %s AND cursor_kind = %s
                """,
                (account_id, workspace_id, mailbox_id, folder_id, cursor_kind),
            )
            row = cur.fetchone()
        return (
            {
                "uidValidity": row[0],
                "lastUid": row[1],
                "nextBeforeUid": row[2],
                "backfillComplete": row[3],
                "updatedAt": _json_datetime(row[4]),
            }
            if row
            else None
        )

    def start_sync_run(
        self, *, account_id: str, workspace_id: str, mailbox_id: str, trigger_kind: str
    ) -> str:
        run_id = f"vault-email-sync-{uuid4()}"
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO vault_private.vault_email_sync_runs (
                  vault_email_sync_run_id, account_id, workspace_id,
                  mailbox_account_id, trigger_kind, status
                )
                VALUES (%s, %s, %s, %s, %s, 'running')
                """,
                (run_id, account_id, workspace_id, mailbox_id, trigger_kind),
            )
            cur.execute(
                """
                UPDATE vault_private.vault_email_mailbox_accounts
                SET sync_status = 'backfilling', last_sync_started_at = now(), updated_at = now()
                WHERE vault_email_mailbox_account_id = %s
                  AND account_id = %s AND workspace_id = %s
                """,
                (mailbox_id, account_id, workspace_id),
            )
        self._conn.commit()
        return run_id

    def finish_sync_run(
        self,
        *,
        account_id: str,
        workspace_id: str,
        mailbox_id: str,
        run_id: str,
        status: str,
        folder_count: int,
        message_count: int,
        attachment_count: int,
        failure_count: int = 0,
        error_code: str | None = None,
        error_class: str | None = None,
    ) -> None:
        if status not in {"complete", "partial", "failed", "cancelled"}:
            raise ValueError("Unsupported Email sync completion state.")
        mailbox_sync_status = {
            "complete": "complete",
            "partial": "partial",
            "failed": "failed",
            "cancelled": "stale",
        }[status]
        with self._conn.cursor() as cur:
            cur.execute(
                """
                UPDATE vault_private.vault_email_sync_runs
                SET status = %s, folder_count = %s, message_count = %s,
                    attachment_count = %s, failure_count = %s,
                    support_safe_error_code = %s, support_safe_error_class = %s,
                    completed_at = now(),
                    duration_ms = (extract(epoch FROM (now() - started_at)) * 1000)::integer
                WHERE vault_email_sync_run_id = %s AND account_id = %s
                  AND workspace_id = %s AND mailbox_account_id = %s
                """,
                (
                    status,
                    folder_count,
                    message_count,
                    attachment_count,
                    failure_count,
                    error_code,
                    error_class,
                    run_id,
                    account_id,
                    workspace_id,
                    mailbox_id,
                ),
            )
            cur.execute(
                """
                UPDATE vault_private.vault_email_mailbox_accounts
                SET sync_status = %s, sync_error_code = %s, sync_error_class = %s,
                    last_sync_completed_at = now(), updated_at = now()
                WHERE vault_email_mailbox_account_id = %s
                  AND account_id = %s AND workspace_id = %s
                """,
                (
                    mailbox_sync_status,
                    error_code,
                    error_class,
                    mailbox_id,
                    account_id,
                    workspace_id,
                ),
            )
        self._conn.commit()


def _required(value: Any, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field} is required.")
    return normalized


def _mailbox_role(value: str) -> str:
    normalized = _required(value, "mailbox_role")
    if normalized not in {"normal_email", "agent_mail"}:
        raise ValueError("Unsupported mailbox role.")
    return normalized


def _address(display: str | None, email: str | None) -> list[dict[str, str | None]]:
    return [{"display": display, "email": email}] if display or email else []


def _mailbox_row(row) -> dict[str, Any]:
    return {
        "mailboxAccountId": row[0],
        "mailboxRole": row[1],
        "emailAddress": row[2],
        "displayName": row[3],
        "lifecycleStatus": row[4],
        "syncEnabled": row[5],
        "syncStatus": row[6],
    }


def _message_row(row) -> dict[str, Any]:
    return {
        "messageId": row[0],
        "folderId": row[1],
        "providerUid": row[2],
        "providerMessageId": row[3],
        "from": list(row[4] or []),
        "to": list(row[5] or []),
        "subject": row[6],
        "snippet": row[7],
        "bodyText": row[8],
        "isUnread": row[9],
        "isArchived": row[10],
        "receivedAt": _json_datetime(row[11]),
    }


def _json_datetime(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


__all__ = [
    "VaultPostgresEmailStore",
    "folder_id",
    "mailbox_account_id",
    "message_id",
]
