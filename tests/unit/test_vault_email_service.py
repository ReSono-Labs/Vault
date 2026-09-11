from contextlib import contextmanager
from datetime import UTC, datetime
import json

import pytest

from app.vault_runtime.email_provider import (
    VaultEmailCredentials,
    VaultEmailFolder,
    VaultEmailMessage,
    VaultEmailMessagePage,
    VaultEmailProviderClient,
)
from app.vault_runtime.email_service import VaultEmailService
from app.vault_runtime.email_store import VaultPostgresEmailStore, _message_row
from app.vault_runtime.signals.email.session_tools import VaultEmailSignalSessionTools


class _EmailStore:
    def __init__(self) -> None:
        self.mailboxes = {}
        self.folders = {}
        self.messages = {}
        self.message_present = {}
        self.message_unread = {}
        self.cursors = {}
        self.send_requests = {}
        self.finished_runs = []
        self.sync_lock_acquired = True
        self.folder_present = {}

    @contextmanager
    def claim_sync(self, **kwargs):
        del kwargs
        yield self.sync_lock_acquired

    def upsert_mailbox(self, **kwargs):
        mailbox_id = kwargs["provider_credential_id"].split(":", 1)[1]
        record = {
            "mailboxAccountId": mailbox_id,
            "mailboxRole": kwargs["mailbox_role"],
            "emailAddress": kwargs["email_address"],
            "lifecycleStatus": "active",
            "syncEnabled": True,
            "syncStatus": "pending",
        }
        self.mailboxes[mailbox_id] = record
        return record

    def get_mailbox(self, **kwargs):
        record = self.mailboxes.get(kwargs["mailbox_id"])
        if not record or kwargs["account_id"] != "account-1" or kwargs["workspace_id"] != "workspace-1":
            return None
        role = kwargs.get("mailbox_role")
        return record if not role or record["mailboxRole"] == role else None

    def list_mailboxes(self, **kwargs):
        role = kwargs.get("mailbox_role")
        return [record for record in self.mailboxes.values() if not role or record["mailboxRole"] == role]

    def upsert_folder(self, **kwargs):
        folder = kwargs["folder"]
        folder_id = f"folder:{folder.provider_folder_key}"
        self.folders[folder_id] = {
            "folderId": folder_id,
            "providerFolderKey": folder.provider_folder_key,
            "displayName": folder.display_name,
            "specialUse": folder.special_use,
        }
        self.folder_present[folder_id] = True
        return folder_id

    def list_folders(self, **kwargs):
        return [
            record
            for folder_id, record in self.folders.items()
            if self.folder_present.get(folder_id, True)
        ]

    def reconcile_folder_inventory(self, **kwargs):
        present_keys = set(kwargs["provider_folder_keys"])
        for folder_id, record in self.folders.items():
            present = record["providerFolderKey"] in present_keys
            self.folder_present[folder_id] = present
            if not present:
                for key in self.messages:
                    if key[0] == folder_id:
                        self.message_present[key] = False

    def reconcile_folder_snapshot(self, **kwargs):
        folder_id = kwargs["folder_id"]
        uid_validity = kwargs["uid_validity"]
        snapshot = dict(kwargs["provider_uid_flags"])
        for key in self.messages:
            if key[0] != folder_id:
                continue
            self.message_present[key] = key[1] == uid_validity and key[2] in snapshot
            if self.message_present[key]:
                self.message_unread[key] = "\\Seen" not in snapshot[key[2]]

    def upsert_message(self, **kwargs):
        key = (kwargs["folder_record_id"], kwargs["uid_validity"], kwargs["provider_uid"])
        self.messages[key] = kwargs["message"]
        self.message_present[key] = True
        self.message_unread[key] = kwargs["message"].is_unread
        return f"message:{key}"

    def list_messages(self, **kwargs):
        return [{"messageId": str(key), "subject": value.subject} for key, value in self.messages.items()]

    def get_message(self, **kwargs):
        return None

    def get_attachment(self, **kwargs):
        return None

    def get_cursor(self, **kwargs):
        return self.cursors.get((kwargs["folder_id"], kwargs["cursor_kind"]))

    def upsert_cursor(self, **kwargs):
        self.cursors[(kwargs["folder_id"], kwargs["cursor_kind"])] = {
            "uidValidity": kwargs["uid_validity"],
            "lastUid": kwargs["last_uid"],
            "nextBeforeUid": kwargs["next_before_uid"],
            "backfillComplete": kwargs["backfill_complete"],
        }

    def start_sync_run(self, **kwargs):
        return "sync-run-1"

    def finish_sync_run(self, **kwargs):
        self.finished_runs.append(kwargs)
        self.mailboxes[kwargs["mailbox_id"]]["syncStatus"] = kwargs["status"]

    def create_send_request(self, **kwargs):
        request = {
            "pendingRequestId": "send-1",
            "status": "pending_confirmation",
            "expiresAt": datetime.now(UTC),
            **kwargs,
        }
        self.send_requests["send-1"] = request
        return {key: request[key] for key in ("pendingRequestId", "status", "expiresAt")}

    def claim_send_request(self, **kwargs):
        request = self.send_requests[kwargs["pending_request_id"]]
        if not kwargs["approve"]:
            return {"status": "cancelled", "pendingRequestId": kwargs["pending_request_id"]}
        return {
            "status": "sending",
            "pendingRequestId": kwargs["pending_request_id"],
            "recipients": request["recipients"],
            "subject": request["subject"],
            "bodyText": request["body_text"],
        }

    def finish_send_request(self, **kwargs):
        self.send_requests[kwargs["pending_request_id"]]["status"] = "sent" if kwargs["sent"] else "failed"

    def set_mailbox_lifecycle(self, **kwargs):
        self.mailboxes[kwargs["mailbox_id"]]["lifecycleStatus"] = kwargs["lifecycle_status"]
        return self.mailboxes[kwargs["mailbox_id"]]


class _RootStore:
    def __init__(self) -> None:
        self.email = _EmailStore()
        self.credentials = {}

    def email_store(self):
        return self.email

    def upsert_provider_credential(self, payload, *, account_id, workspace_id):
        self.credentials[payload["providerCredentialId"]] = {
            "sourcePayload": payload,
            "accountId": account_id,
            "workspaceId": workspace_id,
        }
        return {"providerCredentialId": payload["providerCredentialId"]}

    def get_provider_credential_by_id(self, *, account_id, workspace_id, provider_credential_id):
        return self.credentials.get(provider_credential_id)


class _Provider:
    def __init__(self) -> None:
        self.validated = 0
        self.page_calls = 0
        self.sent = []
        self.sync_sessions = 0
        self.provider_mutations = []

    @contextmanager
    def sync_session(self, **kwargs):
        del kwargs
        self.sync_sessions += 1
        yield self

    def validate_credentials(self, **kwargs):
        self.validated += 1

    def set_read_state(self, **kwargs):
        self.provider_mutations.append(("read_state", kwargs))

    def archive_message(self, **kwargs):
        self.provider_mutations.append(("archive", kwargs))

    def move_message(self, **kwargs):
        self.provider_mutations.append(("move", kwargs))

    def list_folders(self, **kwargs):
        return [VaultEmailFolder("INBOX", "INBOX", "/", ("\\Inbox",), "inbox")]

    def fetch_message_page(self, **kwargs):
        self.page_calls += 1
        if self.page_calls == 1:
            uids, next_before, complete = (3, 2), 2, False
        elif self.page_calls == 2:
            uids, next_before, complete = (1,), None, True
        else:
            uids, next_before, complete = (), None, True
        messages = tuple(
            VaultEmailMessage(
                provider_message_id=str(uid),
                folder="INBOX",
                from_display="Sender",
                from_email="sender@example.test",
                subject=f"Message {uid}",
                snippet="Body",
                body_text="Body",
                to_display="Owner",
                to_email="owner@example.test",
                is_unread=True,
                is_archived=False,
                received_at=datetime.now(UTC),
            )
            for uid in uids
        )
        return VaultEmailMessagePage(
            folder=kwargs["folder"],
            uid_validity=9,
            uid_next=4,
            messages=messages,
            provider_uids=uids,
            next_before_uid=next_before,
            complete=complete,
            provider_uid_flags=(
                ((1, ("\\Seen",)), (2, ()), (3, ()))
                if self.page_calls > 2
                else None
            ),
        )

    def send_message(self, **kwargs):
        self.sent.append(kwargs)


def _credentials():
    return {
        "emailAddress": "owner@example.test",
        "imap": {"host": "imap.example.test", "port": 993, "username": "owner", "password": "secret", "useTls": True},
        "smtp": {"host": "smtp.example.test", "port": 465, "username": "owner", "password": "secret", "useTls": True},
    }


def test_postgres_message_rows_are_strict_json_serializable() -> None:
    received_at = datetime(2026, 7, 31, 11, 20, tzinfo=UTC)
    result = _message_row(
        (
            "message-1",
            "folder-1",
            1,
            "provider-message-1",
            [],
            [],
            "Subject",
            "Snippet",
            "Body",
            True,
            False,
            received_at,
        )
    )

    assert result["receivedAt"] == "2026-07-31T11:20:00+00:00"
    assert json.loads(json.dumps(result))["receivedAt"] == result["receivedAt"]


def test_connect_and_resumable_full_sync_do_not_return_credentials() -> None:
    store = _RootStore()
    provider = _Provider()
    service = VaultEmailService(store=store, provider=provider)  # type: ignore[arg-type]

    mailbox = service.connect_mailbox(
        account_id="account-1",
        workspace_id="workspace-1",
        mailbox_role="normal_email",
        credentials_payload=_credentials(),
    )
    first = service.sync_mailbox(
        account_id="account-1",
        workspace_id="workspace-1",
        mailbox_id=mailbox["mailboxAccountId"],
        max_pages_per_folder=1,
    )
    second = service.sync_mailbox(
        account_id="account-1",
        workspace_id="workspace-1",
        mailbox_id=mailbox["mailboxAccountId"],
        max_pages_per_folder=2,
    )

    assert provider.validated == 1
    assert "credentials" not in mailbox
    assert "password" not in repr(mailbox)
    assert first.status == "partial"
    assert second.status == "complete"
    assert len(store.email.messages) == 3
    assert provider.sync_sessions == 2


def test_due_mailbox_schedule_uses_prior_start_for_fixed_cadence() -> None:
    class Cursor:
        def __init__(self) -> None:
            self.query = ""

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params):
            del params
            self.query = query

        def fetchall(self):
            return []

    class Connection:
        def __init__(self) -> None:
            self.last_cursor = None

        def cursor(self):
            self.last_cursor = Cursor()
            return self.last_cursor

    connection = Connection()

    assert VaultPostgresEmailStore(connection).list_sync_candidates(
        due_before=datetime.now(UTC), limit=5
    ) == []
    assert "last_sync_started_at <= %s" in connection.last_cursor.query
    assert "ORDER BY last_sync_started_at" in connection.last_cursor.query
    assert "last_sync_completed_at <= %s" not in connection.last_cursor.query


def test_competing_mailbox_sync_returns_without_provider_work() -> None:
    store = _RootStore()
    provider = _Provider()
    service = VaultEmailService(store=store, provider=provider)  # type: ignore[arg-type]
    mailbox = service.connect_mailbox(
        account_id="account-1",
        workspace_id="workspace-1",
        mailbox_role="normal_email",
        credentials_payload=_credentials(),
    )
    store.email.sync_lock_acquired = False

    result = service.sync_mailbox(
        account_id="account-1",
        workspace_id="workspace-1",
        mailbox_id=mailbox["mailboxAccountId"],
    )

    assert result.status == "already_running"
    assert provider.page_calls == 0
    assert store.email.finished_runs == []


def test_incremental_sync_reconciles_existing_flags_and_missing_uids() -> None:
    store = _RootStore()
    provider = _Provider()
    service = VaultEmailService(store=store, provider=provider)  # type: ignore[arg-type]
    mailbox = service.connect_mailbox(
        account_id="account-1",
        workspace_id="workspace-1",
        mailbox_role="normal_email",
        credentials_payload=_credentials(),
    )
    service.sync_mailbox(
        account_id="account-1",
        workspace_id="workspace-1",
        mailbox_id=mailbox["mailboxAccountId"],
        max_pages_per_folder=1,
    )
    service.sync_mailbox(
        account_id="account-1",
        workspace_id="workspace-1",
        mailbox_id=mailbox["mailboxAccountId"],
        max_pages_per_folder=2,
    )

    provider.fetch_message_page = lambda **kwargs: VaultEmailMessagePage(
        folder=kwargs["folder"],
        uid_validity=9,
        uid_next=4,
        messages=(),
        provider_uids=(),
        next_before_uid=None,
        complete=True,
        provider_uid_flags=((1, ("\\Seen",)), (3, ())),
    )
    result = service.sync_mailbox(
        account_id="account-1",
        workspace_id="workspace-1",
        mailbox_id=mailbox["mailboxAccountId"],
    )

    assert result.status == "complete"
    assert result.message_count == 0
    assert store.email.message_present[("folder:INBOX", 9, 1)] is True
    assert store.email.message_unread[("folder:INBOX", 9, 1)] is False
    assert store.email.message_present[("folder:INBOX", 9, 2)] is False
    assert store.email.message_present[("folder:INBOX", 9, 3)] is True


def test_canonical_voice_read_never_runs_inline_provider_refresh() -> None:
    store = _RootStore()
    provider = _Provider()
    service = VaultEmailService(store=store, provider=provider)  # type: ignore[arg-type]
    mailbox = service.connect_mailbox(
        account_id="account-1",
        workspace_id="workspace-1",
        mailbox_role="normal_email",
        credentials_payload=_credentials(),
    )
    service.sync_mailbox(
        account_id="account-1",
        workspace_id="workspace-1",
        mailbox_id=mailbox["mailboxAccountId"],
        max_pages_per_folder=2,
    )
    page_calls_before_read = provider.page_calls

    result = VaultEmailSignalSessionTools(store=store).execute_cache_tool(
        account_id="account-1",
        workspace_id="workspace-1",
        voice_realtime_session_id="voice-session-1",
        tool_call_id="tool-call-1",
        tool_name="email_check",
        arguments={"freshness": "live", "limit": 5},
    )

    assert result["status"] == "completed"
    assert result["freshness"] == {
        "source": "vault_email_canonical",
        "syncStatus": "complete",
        "resultsMayBePartial": False,
        "refreshMode": "background_sync",
    }
    assert provider.page_calls == page_calls_before_read


def test_send_is_not_executed_until_confirmation() -> None:
    store = _RootStore()
    provider = _Provider()
    service = VaultEmailService(store=store, provider=provider)  # type: ignore[arg-type]
    mailbox = service.connect_mailbox(
        account_id="account-1",
        workspace_id="workspace-1",
        mailbox_role="normal_email",
        credentials_payload=_credentials(),
    )

    pending = service.prepare_send(
        account_id="account-1",
        workspace_id="workspace-1",
        mailbox_id=mailbox["mailboxAccountId"],
        idempotency_key="tool-call-1",
        to_recipients=["recipient@example.test"],
        subject="Test",
        body="Body",
    )
    assert provider.sent == []

    result = service.confirm_send(
        account_id="account-1",
        workspace_id="workspace-1",
        mailbox_id=mailbox["mailboxAccountId"],
        pending_request_id=pending["pendingRequestId"],
        approve=True,
    )
    assert result["status"] == "sent"
    assert len(provider.sent) == 1


def test_message_mutations_resolve_vault_message_id_to_scoped_uid_and_folder() -> None:
    store = _RootStore()
    provider = _Provider()
    service = VaultEmailService(store=store, provider=provider)  # type: ignore[arg-type]
    mailbox = service.connect_mailbox(
        account_id="account-1",
        workspace_id="workspace-1",
        mailbox_role="normal_email",
        credentials_payload=_credentials(),
    )
    mailbox_id = mailbox["mailboxAccountId"]
    store.email.folders["folder:INBOX"] = {
        "folderId": "folder:INBOX",
        "providerFolderKey": "INBOX",
        "displayName": "INBOX",
        "specialUse": "inbox",
    }
    store.email.get_message = lambda **kwargs: (
        {"messageId": "message-local-1", "folderId": "folder:INBOX", "providerUid": 427}
        if kwargs["message_id"] == "message-local-1"
        else None
    )

    service.set_read_state(
        account_id="account-1",
        workspace_id="workspace-1",
        mailbox_id=mailbox_id,
        provider_message_id="message-local-1",
        source_folder="caller-supplied-wrong-folder",
        is_read=True,
    )
    service.move_message(
        account_id="account-1",
        workspace_id="workspace-1",
        mailbox_id=mailbox_id,
        provider_message_id="message-local-1",
        source_folder="caller-supplied-wrong-folder",
        destination_folder="Archive",
    )

    assert provider.provider_mutations[0][1]["message_id"] == "427"
    assert provider.provider_mutations[0][1]["source_folder"] == "INBOX"
    assert provider.provider_mutations[1][1]["message_id"] == "427"
    assert provider.provider_mutations[1][1]["source_folder"] == "INBOX"


def test_provider_has_no_delete_tool_and_rejects_trash_move() -> None:
    client = VaultEmailProviderClient()
    credentials = VaultEmailCredentials(
        "owner@example.test",
        "imap.example.test",
        993,
        "owner",
        "secret",
        True,
        "smtp.example.test",
        465,
        "owner",
        "secret",
        True,
    )

    assert not hasattr(client, "delete_message")
    assert not hasattr(client, "delete_folder")
    with pytest.raises(ValueError):
        client.move_message(
            credentials=credentials,
            message_id="1",
            source_folder="INBOX",
            destination_folder="Trash",
        )
