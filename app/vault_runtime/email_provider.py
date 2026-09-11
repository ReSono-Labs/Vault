from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from email.parser import BytesParser
from email.policy import default as email_policy_default
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import format_datetime, getaddresses, make_msgid, parsedate_to_datetime
from html import unescape
from hashlib import sha256
import imaplib
import logging
import re
import socket
import smtplib
from time import monotonic
from typing import Callable, Iterator

from app.core.security.outbound import validate_public_host


logger = logging.getLogger(__name__)

DEFAULT_EMAIL_PROVIDER_TIMEOUT_SECONDS = 20.0


def _create_connection_ipv4_preferred(
    address: tuple[str, int], timeout: float | None
):
    """Connect to a dual-stack provider without waiting on broken IPv6 first."""

    host, port = address
    candidates = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    candidates.sort(key=lambda candidate: candidate[0] != socket.AF_INET)
    last_error: OSError | None = None
    for family, socket_type, protocol, _, socket_address in candidates:
        connection = socket.socket(family, socket_type, protocol)
        try:
            if timeout is not None:
                connection.settimeout(timeout)
            connection.connect(socket_address)
            return connection
        except OSError as exc:
            last_error = exc
            connection.close()
    if last_error is not None:
        raise last_error
    raise OSError("No provider network address was available.")


class _IPv4PreferredIMAP4(imaplib.IMAP4):
    def _create_socket(self, timeout):
        return _create_connection_ipv4_preferred((self.host, self.port), timeout)


class _IPv4PreferredIMAP4SSL(imaplib.IMAP4_SSL):
    def _create_socket(self, timeout):
        raw_socket = _create_connection_ipv4_preferred(
            (self.host, self.port), timeout
        )
        try:
            return self.ssl_context.wrap_socket(
                raw_socket,
                server_hostname=self.host,
            )
        except Exception:
            raw_socket.close()
            raise


def _open_imap_connection(
    *, host: str, port: int, use_tls: bool, timeout: float
):
    return (
        _IPv4PreferredIMAP4SSL(host, port, timeout=timeout)
        if use_tls
        else _IPv4PreferredIMAP4(host, port, timeout=timeout)
    )


@dataclass(slots=True, frozen=True)
class CustomEmailCredentials:
    email_address: str
    imap_host: str
    imap_port: int
    imap_username: str
    imap_password: str
    imap_use_tls: bool
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    smtp_use_tls: bool


@dataclass(slots=True, frozen=True)
class CustomEmailMessage:
    provider_message_id: str
    folder: str
    from_display: str
    from_email: str | None
    subject: str
    snippet: str | None
    body_text: str | None
    to_display: str | None
    to_email: str | None
    is_unread: bool
    is_archived: bool
    received_at: datetime
    message_header_id: str | None = None
    attachments: tuple["VaultEmailAttachment", ...] = ()


@dataclass(slots=True, frozen=True)
class VaultEmailAttachment:
    provider_part_key: str
    file_name: str | None
    content_type: str
    content_disposition: str | None
    content_id: str | None
    size_bytes: int
    sha256: str | None
    content_bytes: bytes | None
    content_complete: bool


@dataclass(slots=True, frozen=True)
class VaultEmailFolder:
    provider_folder_key: str
    display_name: str
    delimiter: str | None
    flags: tuple[str, ...]
    special_use: str | None


@dataclass(slots=True, frozen=True)
class VaultEmailMessagePage:
    folder: VaultEmailFolder
    uid_validity: int
    uid_next: int | None
    messages: tuple[CustomEmailMessage, ...]
    provider_uids: tuple[int, ...]
    next_before_uid: int | None
    complete: bool
    provider_uid_flags: tuple[tuple[int, tuple[str, ...]], ...] | None = None


@dataclass(slots=True, frozen=True)
class CustomEmailSearchResult:
    messages: list[CustomEmailMessage]
    folders_searched: list[str]
    results_may_be_partial: bool


class VaultEmailProviderSyncSession:
    """One authenticated IMAP connection reused for one mailbox sync pass."""

    def __init__(self, *, client: "CustomEmailProviderClient", mailbox) -> None:
        self._client = client
        self._mailbox = mailbox

    def list_folders(
        self, *, credentials: CustomEmailCredentials | None = None
    ) -> list[VaultEmailFolder]:
        del credentials
        return self._client._list_folders_from_mailbox(mailbox=self._mailbox)

    def fetch_message_page(
        self,
        *,
        credentials: CustomEmailCredentials | None = None,
        folder: VaultEmailFolder,
        before_uid: int | None = None,
        after_uid: int | None = None,
        limit: int = 100,
        max_attachment_bytes: int = 10 * 1024 * 1024,
    ) -> VaultEmailMessagePage:
        del credentials
        return self._client._fetch_message_page_from_mailbox(
            mailbox=self._mailbox,
            folder=folder,
            before_uid=before_uid,
            after_uid=after_uid,
            limit=limit,
            max_attachment_bytes=max_attachment_bytes,
        )


class CustomEmailProviderClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_EMAIL_PROVIDER_TIMEOUT_SECONDS,
        host_validator: Callable[..., str] | None = None,
    ) -> None:
        self._timeout_seconds = max(1.0, float(timeout_seconds or DEFAULT_EMAIL_PROVIDER_TIMEOUT_SECONDS))
        self._host_validator = host_validator or validate_public_host

    def validate_credentials(self, *, credentials: CustomEmailCredentials) -> None:
        mailbox = self._imap_connect(credentials=credentials)
        self._safe_logout(mailbox)
        self._smtp_connect(credentials=credentials)

    @contextmanager
    def sync_session(
        self, *, credentials: CustomEmailCredentials
    ) -> Iterator[VaultEmailProviderSyncSession]:
        mailbox = self._imap_connect(credentials=credentials)
        try:
            yield VaultEmailProviderSyncSession(client=self, mailbox=mailbox)
        finally:
            self._safe_logout(mailbox)

    def list_folders(self, *, credentials: CustomEmailCredentials) -> list[VaultEmailFolder]:
        with self.sync_session(credentials=credentials) as session:
            return session.list_folders()

    def _list_folders_from_mailbox(self, *, mailbox) -> list[VaultEmailFolder]:
        status, data = self._timed_imap_step(operation="list", action=mailbox.list)
        if status != "OK" or not data:
            raise RuntimeError("Provider returned no mailbox folders.")
        folders: list[VaultEmailFolder] = []
        for raw_entry in data:
            if not raw_entry:
                continue
            entry = raw_entry.decode("utf-8", errors="ignore")
            folder_name = self._folder_name_from_list_entry(entry)
            if not folder_name:
                continue
            flags_match = re.match(r"^\(([^)]*)\)", entry)
            flags = tuple(flags_match.group(1).split()) if flags_match else ()
            delimiter_match = re.match(r'^\([^)]*\)\s+(?:"([^"]*)"|NIL)\s+', entry, flags=re.IGNORECASE)
            delimiter = delimiter_match.group(1) if delimiter_match else None
            folders.append(
                VaultEmailFolder(
                    provider_folder_key=folder_name,
                    display_name=folder_name,
                    delimiter=delimiter,
                    flags=flags,
                    special_use=self._special_use_from_flags(flags=flags, folder_name=folder_name),
                )
            )
        return folders

    def fetch_message_page(
        self,
        *,
        credentials: CustomEmailCredentials,
        folder: VaultEmailFolder,
        before_uid: int | None = None,
        after_uid: int | None = None,
        limit: int = 100,
        max_attachment_bytes: int = 10 * 1024 * 1024,
    ) -> VaultEmailMessagePage:
        with self.sync_session(credentials=credentials) as session:
            return session.fetch_message_page(
                folder=folder,
                before_uid=before_uid,
                after_uid=after_uid,
                limit=limit,
                max_attachment_bytes=max_attachment_bytes,
            )

    def _fetch_message_page_from_mailbox(
        self,
        *,
        mailbox,
        folder: VaultEmailFolder,
        before_uid: int | None = None,
        after_uid: int | None = None,
        limit: int = 100,
        max_attachment_bytes: int = 10 * 1024 * 1024,
    ) -> VaultEmailMessagePage:
        status, _ = self._timed_imap_step(
            operation="select",
            action=lambda: mailbox.select(folder.provider_folder_key, readonly=True),
        )
        if status != "OK":
            raise RuntimeError("Unable to open the requested mailbox folder.")
        uid_validity = self._response_int(mailbox=mailbox, key="UIDVALIDITY") or 1
        uid_next = self._response_int(mailbox=mailbox, key="UIDNEXT")
        provider_uid_flags = None
        if after_uid is not None:
            flags_status, flags_data = self._timed_imap_step(
                operation="flags",
                action=lambda: mailbox.uid("FETCH", "1:*", "(UID FLAGS)"),
            )
            if flags_status != "OK":
                raise RuntimeError("Unable to reconcile mailbox message state.")
            provider_uid_flags = self._uid_flags_from_fetch_payload(flags_data)
        if after_uid is not None:
            uid_range = f"{max(1, int(after_uid) + 1)}:*"
        elif before_uid is not None:
            uid_range = f"1:{max(1, int(before_uid) - 1)}"
        else:
            uid_range = "1:*"
        search_status, search_data = self._timed_imap_step(
            operation="search",
            action=lambda: mailbox.uid("SEARCH", None, "UID", uid_range),
        )
        if search_status != "OK" or not search_data:
            return VaultEmailMessagePage(
                folder,
                uid_validity,
                uid_next,
                (),
                (),
                None,
                True,
                provider_uid_flags,
            )
        all_uids = [int(item) for item in search_data[0].split() if item]
        if after_uid is not None:
            all_uids = [uid for uid in all_uids if uid > int(after_uid)]
        elif before_uid is not None:
            all_uids = [uid for uid in all_uids if uid < int(before_uid)]
        selected = all_uids[-max(1, min(int(limit), 500)) :]
        selected.reverse()
        messages: list[CustomEmailMessage] = []
        provider_uids: list[int] = []
        fetch_started = monotonic()
        fetch_outcome = "succeeded"
        try:
            for uid in selected:
                fetch_status, payload = mailbox.uid("FETCH", str(uid), "(RFC822 FLAGS)")
                parsed = self._message_from_fetch_payload(
                    payload=payload,
                    fetch_status=fetch_status,
                    folder=folder.provider_folder_key,
                    provider_message_id=str(uid),
                    max_attachment_bytes=max_attachment_bytes,
                )
                if parsed is not None:
                    messages.append(parsed)
                    provider_uids.append(uid)
        except Exception:
            fetch_outcome = "failed"
            raise
        finally:
            self._log_imap_timing(
                operation="fetch",
                started_at=fetch_started,
                outcome=fetch_outcome,
            )
        smallest_uid = min(selected) if selected else None
        next_before_uid = smallest_uid if smallest_uid and any(uid < smallest_uid for uid in all_uids) else None
        return VaultEmailMessagePage(
            folder=folder,
            uid_validity=uid_validity,
            uid_next=uid_next,
            messages=tuple(messages),
            provider_uids=tuple(provider_uids),
            next_before_uid=next_before_uid,
            complete=next_before_uid is None,
            provider_uid_flags=provider_uid_flags,
        )

    def fetch_recent_messages(
        self,
        *,
        credentials: CustomEmailCredentials,
        folder: str = "INBOX",
        limit: int = 10,
    ) -> list[CustomEmailMessage]:
        mailbox = self._imap_connect(credentials=credentials)
        try:
            status, _ = mailbox.select(folder, readonly=True)
            if status != "OK":
                return []
            status, data = mailbox.search(None, "ALL")
            if status != "OK" or not data:
                return []
            message_ids = [item for item in data[0].split() if item][-limit:]
            return self._fetch_messages_by_ids(mailbox=mailbox, folder=folder, message_ids=list(reversed(message_ids)), limit=limit)
        finally:
            self._safe_logout(mailbox)

    def search_messages(
        self,
        *,
        credentials: CustomEmailCredentials,
        query: str | None = None,
        folders: list[str] | tuple[str, ...] | None = None,
        unread_only: bool = False,
        limit: int = 10,
    ) -> CustomEmailSearchResult:
        mailbox = self._imap_connect(credentials=credentials)
        resolved_folders: list[str] = []
        results: list[CustomEmailMessage] = []
        seen: set[tuple[str, str]] = set()
        results_may_be_partial = False
        try:
            for folder in self._resolve_search_folders(mailbox=mailbox, folders=folders):
                if len(results) >= limit:
                    results_may_be_partial = True
                    break
                status, _ = mailbox.select(folder, readonly=True)
                if status != "OK":
                    continue
                resolved_folders.append(folder)
                message_ids, partial = self._search_message_ids(
                    mailbox=mailbox,
                    query=query,
                    unread_only=unread_only,
                    limit=max(limit * 4, 50),
                )
                results_may_be_partial = results_may_be_partial or partial
                messages = self._fetch_messages_by_ids(
                    mailbox=mailbox,
                    folder=folder,
                    message_ids=list(reversed(message_ids)),
                    limit=max(limit * 2, 25),
                )
                for message in messages:
                    if query and not self._message_matches_query(message=message, query=query):
                        continue
                    if unread_only and not message.is_unread:
                        continue
                    key = (message.folder, message.provider_message_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(message)
                    if len(results) >= limit:
                        break
            return CustomEmailSearchResult(
                messages=results[:limit],
                folders_searched=resolved_folders,
                results_may_be_partial=results_may_be_partial or len(results) > limit,
            )
        finally:
            self._safe_logout(mailbox)

    def fetch_message(
        self,
        *,
        credentials: CustomEmailCredentials,
        message_id: str,
        folder: str = "INBOX",
    ) -> CustomEmailMessage | None:
        mailbox = self._imap_connect(credentials=credentials)
        try:
            status, _ = mailbox.select(folder, readonly=True)
            if status != "OK":
                return None
            fetch_status, payload = mailbox.fetch(message_id.encode("utf-8"), "(RFC822 FLAGS)")
            if fetch_status != "OK" or not payload:
                return None
            raw_message = next(
                (
                    chunk[1]
                    for chunk in payload
                    if isinstance(chunk, tuple) and len(chunk) > 1 and isinstance(chunk[1], (bytes, bytearray))
                ),
                None,
            )
            flags_text = " ".join(
                chunk[0].decode("utf-8", errors="ignore")
                for chunk in payload
                if isinstance(chunk, tuple) and len(chunk) > 0 and isinstance(chunk[0], (bytes, bytearray))
            )
            if raw_message is None:
                return None
            parsed = self._parse_message(
                raw_message=bytes(raw_message),
                folder=folder,
                is_unread="\\\\Seen" not in flags_text and "\\Seen" not in flags_text,
            )
            return CustomEmailMessage(
                provider_message_id=message_id,
                folder=parsed.folder,
                from_display=parsed.from_display,
                from_email=parsed.from_email,
                subject=parsed.subject,
                snippet=parsed.snippet,
                body_text=parsed.body_text,
                to_display=parsed.to_display,
                to_email=parsed.to_email,
                is_unread=parsed.is_unread,
                is_archived=parsed.is_archived,
                received_at=parsed.received_at,
            )
        finally:
            self._safe_logout(mailbox)

    def _fetch_messages_by_ids(
        self,
        *,
        mailbox,
        folder: str,
        message_ids: list[bytes],
        limit: int,
    ) -> list[CustomEmailMessage]:
        results: list[CustomEmailMessage] = []
        for message_id in message_ids[: max(1, limit)]:
            fetch_status, payload = mailbox.fetch(message_id, "(RFC822 FLAGS)")
            if fetch_status != "OK" or not payload:
                continue
            raw_message = next(
                (
                    chunk[1]
                    for chunk in payload
                    if isinstance(chunk, tuple) and len(chunk) > 1 and isinstance(chunk[1], (bytes, bytearray))
                ),
                None,
            )
            flags_text = " ".join(
                chunk[0].decode("utf-8", errors="ignore")
                for chunk in payload
                if isinstance(chunk, tuple) and len(chunk) > 0 and isinstance(chunk[0], (bytes, bytearray))
            )
            if raw_message is None:
                continue
            parsed = self._parse_message(
                raw_message=bytes(raw_message),
                folder=folder,
                is_unread="\\\\Seen" not in flags_text and "\\Seen" not in flags_text,
            )
            results.append(
                CustomEmailMessage(
                    provider_message_id=message_id.decode("utf-8", errors="ignore"),
                    folder=parsed.folder,
                    from_display=parsed.from_display,
                    from_email=parsed.from_email,
                    subject=parsed.subject,
                    snippet=parsed.snippet,
                    body_text=parsed.body_text,
                    to_display=parsed.to_display,
                    to_email=parsed.to_email,
                    is_unread=parsed.is_unread,
                    is_archived=parsed.is_archived,
                    received_at=parsed.received_at,
                )
            )
        return results

    def _search_message_ids(
        self,
        *,
        mailbox,
        query: str | None,
        unread_only: bool,
        limit: int,
    ) -> tuple[list[bytes], bool]:
        criteria: list[str] = []
        if unread_only:
            criteria.append("UNSEEN")
        normalized_query = (query or "").strip()
        if normalized_query:
            criteria.extend(("TEXT", self._quote_search_text(normalized_query)))
        if not criteria:
            criteria.append("ALL")
        try:
            status, data = mailbox.search("UTF-8" if normalized_query else None, *criteria)
        except Exception:
            status, data = ("NO", [])
        if status != "OK" or not data:
            fallback_criteria = ["UNSEEN"] if unread_only else ["ALL"]
            status, data = mailbox.search(None, *fallback_criteria)
        if status != "OK" or not data:
            return [], False
        message_ids = [item for item in data[0].split() if item]
        return message_ids[-limit:], len(message_ids) > limit

    @staticmethod
    def _resolve_search_folders(
        *,
        mailbox,
        folders: list[str] | tuple[str, ...] | None,
    ) -> list[str]:
        if folders:
            return CustomEmailProviderClient._dedupe_folder_names(folders)
        candidates = ["INBOX"]
        status, data = mailbox.list()
        if status != "OK" or not data:
            return candidates
        for entry in data:
            if not entry:
                continue
            folder_name = CustomEmailProviderClient._folder_name_from_list_entry(entry.decode("utf-8", errors="ignore"))
            if not folder_name:
                continue
            normalized = folder_name.replace(".", " ").replace("/", " ").lower()
            if folder_name.upper() == "INBOX" or any(
                token in normalized
                for token in ("archive", "all mail", "sent", "sent items", "sent messages")
            ):
                candidates.append(folder_name)
        return CustomEmailProviderClient._dedupe_folder_names(candidates)

    @staticmethod
    def _dedupe_folder_names(folders: list[str] | tuple[str, ...]) -> list[str]:
        resolved: list[str] = []
        seen: set[str] = set()
        for folder in folders:
            if not isinstance(folder, str):
                continue
            stripped = folder.strip()
            if not stripped:
                continue
            normalized = stripped.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            resolved.append(stripped)
        return resolved or ["INBOX"]

    @staticmethod
    def _quote_search_text(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', r"\"")
        return f'"{escaped}"'

    @staticmethod
    def _message_matches_query(*, message: CustomEmailMessage, query: str) -> bool:
        lowered = query.strip().lower()
        if not lowered:
            return True
        haystacks = (
            message.from_display,
            message.from_email,
            message.to_display,
            message.to_email,
            message.subject,
            message.snippet,
            message.body_text,
        )
        return any(lowered in (value or "").lower() for value in haystacks)

    def send_message(
        self,
        *,
        credentials: CustomEmailCredentials,
        to_recipients: list[str],
        subject: str,
        body: str,
    ) -> None:
        message = self._build_outgoing_message(
            credentials=credentials,
            to_recipients=to_recipients,
            subject=subject,
            body=body,
        )
        self._host_validator(credentials.smtp_host, target="smtpHost")
        if credentials.smtp_use_tls:
            with smtplib.SMTP_SSL(
                credentials.smtp_host,
                credentials.smtp_port,
                timeout=self._timeout_seconds,
            ) as client:
                client.login(credentials.smtp_username, credentials.smtp_password)
                client.send_message(message)
        else:
            with smtplib.SMTP(
                credentials.smtp_host,
                credentials.smtp_port,
                timeout=self._timeout_seconds,
            ) as client:
                client.ehlo()
                if client.has_extn("starttls"):
                    client.starttls()
                    client.ehlo()
                client.login(credentials.smtp_username, credentials.smtp_password)
                client.send_message(message)
        self._append_sent_copy(credentials=credentials, message=message)

    def archive_message(
        self,
        *,
        credentials: CustomEmailCredentials,
        message_id: str,
        source_folder: str = "INBOX",
    ) -> None:
        mailbox = self._imap_connect(credentials=credentials)
        try:
            select_status, _ = mailbox.select(source_folder)
            if select_status != "OK":
                raise RuntimeError("Unable to open the source mailbox folder.")
            archive_folder = self._resolve_archive_folder(mailbox)
            copy_status, _ = mailbox.uid("COPY", str(message_id), archive_folder)
            if copy_status != "OK":
                raise RuntimeError("Unable to copy message to archive.")
            store_status, _ = mailbox.uid(
                "STORE", str(message_id), "+FLAGS", "\\Deleted"
            )
            if store_status != "OK":
                raise RuntimeError("Unable to mark source message deleted after archive copy.")
            mailbox.expunge()
        finally:
            self._safe_logout(mailbox)

    def create_folder(self, *, credentials: CustomEmailCredentials, folder_name: str) -> None:
        normalized = self._validated_ordinary_folder_name(folder_name)
        mailbox = self._imap_connect(credentials=credentials)
        try:
            status, _ = mailbox.create(normalized)
            if status != "OK":
                raise RuntimeError("Unable to create the requested mailbox folder.")
        finally:
            self._safe_logout(mailbox)

    def rename_folder(
        self,
        *,
        credentials: CustomEmailCredentials,
        source_folder: str,
        destination_folder: str,
    ) -> None:
        source = self._validated_ordinary_folder_name(source_folder)
        destination = self._validated_ordinary_folder_name(destination_folder)
        mailbox = self._imap_connect(credentials=credentials)
        try:
            status, _ = mailbox.rename(source, destination)
            if status != "OK":
                raise RuntimeError("Unable to rename the requested mailbox folder.")
        finally:
            self._safe_logout(mailbox)

    def move_message(
        self,
        *,
        credentials: CustomEmailCredentials,
        message_id: str,
        source_folder: str,
        destination_folder: str,
    ) -> None:
        source = self._validated_ordinary_folder_name(
            source_folder,
            allow_inbox=True,
            allow_archive=True,
        )
        destination = self._validated_ordinary_folder_name(
            destination_folder,
            allow_inbox=True,
            allow_archive=True,
        )
        if source.casefold() == destination.casefold():
            return
        mailbox = self._imap_connect(credentials=credentials)
        try:
            status, _ = mailbox.select(source)
            if status != "OK":
                raise RuntimeError("Unable to open the source mailbox folder.")
            if "MOVE" in getattr(mailbox, "capabilities", ()):
                move_status, _ = mailbox.uid("MOVE", str(message_id), destination)
                if move_status == "OK":
                    return
            copy_status, _ = mailbox.uid("COPY", str(message_id), destination)
            if copy_status != "OK":
                raise RuntimeError("Unable to copy the message to the destination folder.")
            store_status, _ = mailbox.uid(
                "STORE", str(message_id), "+FLAGS", "\\Deleted"
            )
            if store_status != "OK":
                raise RuntimeError("Unable to finish moving the message.")
            mailbox.expunge()
        finally:
            self._safe_logout(mailbox)

    def set_read_state(
        self,
        *,
        credentials: CustomEmailCredentials,
        message_id: str,
        is_read: bool,
        source_folder: str = "INBOX",
    ) -> None:
        mailbox = self._imap_connect(credentials=credentials)
        try:
            status, _ = mailbox.select(source_folder)
            if status != "OK":
                raise RuntimeError("Unable to open the requested mailbox folder.")
            command = "+FLAGS" if is_read else "-FLAGS"
            store_status, _ = mailbox.uid(
                "STORE", str(message_id), command, "\\Seen"
            )
            if store_status != "OK":
                raise RuntimeError("Unable to update the read state for that message.")
        finally:
            self._safe_logout(mailbox)

    def _imap_connect(self, *, credentials: CustomEmailCredentials):
        self._host_validator(credentials.imap_host, target="imapHost")
        connect_started = monotonic()
        connect_outcome = "succeeded"
        try:
            mailbox = _open_imap_connection(
                host=credentials.imap_host,
                port=credentials.imap_port,
                use_tls=credentials.imap_use_tls,
                timeout=self._timeout_seconds,
            )
        except Exception:
            connect_outcome = "failed"
            raise
        finally:
            self._log_imap_timing(
                operation="connect",
                started_at=connect_started,
                outcome=connect_outcome,
            )
        try:
            self._timed_imap_step(
                operation="login",
                action=lambda: mailbox.login(
                    credentials.imap_username, credentials.imap_password
                ),
            )
            return mailbox
        except Exception:
            self._safe_logout(mailbox)
            raise

    def _smtp_connect(self, *, credentials: CustomEmailCredentials) -> None:
        self._host_validator(credentials.smtp_host, target="smtpHost")
        if credentials.smtp_use_tls:
            with smtplib.SMTP_SSL(credentials.smtp_host, credentials.smtp_port, timeout=self._timeout_seconds) as client:
                client.login(credentials.smtp_username, credentials.smtp_password)
            return
        with smtplib.SMTP(credentials.smtp_host, credentials.smtp_port, timeout=self._timeout_seconds) as client:
            client.ehlo()
            if client.has_extn("starttls"):
                client.starttls()
                client.ehlo()
            client.login(credentials.smtp_username, credentials.smtp_password)

    def _append_sent_copy(self, *, credentials: CustomEmailCredentials, message: EmailMessage) -> None:
        mailbox = self._imap_connect(credentials=credentials)
        try:
            sent_folder = self._resolve_sent_folder(mailbox)
            status, _ = mailbox.append(
                sent_folder,
                "\\Seen",
                imaplib.Time2Internaldate(datetime.now(UTC).timestamp()),
                message.as_bytes(),
            )
            if status != "OK":
                logger.warning("custom_email_sent_append_failed", extra={"folder": sent_folder, "status": status})
        except Exception:
            logger.warning("custom_email_sent_append_failed", exc_info=True)
        finally:
            self._safe_logout(mailbox)

    @staticmethod
    def _build_outgoing_message(
        *,
        credentials: CustomEmailCredentials,
        to_recipients: list[str],
        subject: str,
        body: str,
    ) -> EmailMessage:
        message = EmailMessage()
        message["From"] = credentials.email_address
        message["To"] = ", ".join(to_recipients)
        message["Subject"] = subject
        message["Date"] = format_datetime(datetime.now(UTC))
        domain = credentials.email_address.rsplit("@", 1)[1] if "@" in credentials.email_address else None
        message["Message-ID"] = make_msgid(domain=domain)
        message.set_content(body)
        return message

    def _safe_logout(self, mailbox) -> None:
        started_at = monotonic()
        outcome = "succeeded"
        try:
            mailbox.logout()
        except Exception:
            outcome = "failed"
        finally:
            self._log_imap_timing(
                operation="logout",
                started_at=started_at,
                outcome=outcome,
            )

    def _timed_imap_step(self, *, operation: str, action):
        started_at = monotonic()
        outcome = "succeeded"
        try:
            return action()
        except Exception:
            outcome = "failed"
            raise
        finally:
            self._log_imap_timing(
                operation=operation,
                started_at=started_at,
                outcome=outcome,
            )

    @staticmethod
    def _log_imap_timing(*, operation: str, started_at: float, outcome: str) -> None:
        logger.info(
            "vault_email_imap_step operation=%s duration_ms=%s outcome=%s",
            operation,
            max(0, round((monotonic() - started_at) * 1000)),
            outcome,
        )

    @staticmethod
    def _parse_message(*, raw_message: bytes, folder: str, is_unread: bool) -> CustomEmailMessage:
        message = BytesParser(policy=email_policy_default).parsebytes(raw_message)
        subject = str(make_header(decode_header(message.get("Subject", "")))).strip() or "(no subject)"
        sender_pairs = getaddresses(message.get_all("From", []))
        sender_name, sender_email = sender_pairs[0] if sender_pairs else ("Unknown sender", "")
        from_display = sender_name or sender_email or "Unknown sender"
        recipient_pairs = getaddresses(message.get_all("To", []))
        recipient_name, recipient_email = recipient_pairs[0] if recipient_pairs else ("", "")
        to_display = recipient_name or recipient_email or None
        received_at = datetime.now(UTC)
        date_header = message.get("Date")
        if date_header:
            try:
                parsed = parsedate_to_datetime(date_header)
                received_at = parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
            except Exception:
                received_at = datetime.now(UTC)
        body_text = CustomEmailProviderClient._body_from_message(message)
        snippet = body_text[:280] if body_text else None
        return CustomEmailMessage(
            provider_message_id="",
            folder=folder,
            from_display=from_display,
            from_email=sender_email or None,
            subject=subject,
            snippet=snippet,
            body_text=body_text,
            to_display=to_display,
            to_email=recipient_email or None,
            is_unread=is_unread,
            is_archived="archive" in folder.lower(),
            received_at=received_at,
            message_header_id=(message.get("Message-ID") or "").strip() or None,
            attachments=CustomEmailProviderClient._attachments_from_message(message),
        )

    @staticmethod
    def _attachments_from_message(message, *, max_attachment_bytes: int = 10 * 1024 * 1024) -> tuple[VaultEmailAttachment, ...]:
        attachments: list[VaultEmailAttachment] = []
        for part_index, part in enumerate(message.walk()):
            if not CustomEmailProviderClient._is_attachment(part):
                continue
            payload = part.get_payload(decode=True) or b""
            within_limit = len(payload) <= max(0, int(max_attachment_bytes))
            attachments.append(
                VaultEmailAttachment(
                    provider_part_key=str(part_index),
                    file_name=part.get_filename(),
                    content_type=part.get_content_type() or "application/octet-stream",
                    content_disposition=part.get_content_disposition(),
                    content_id=(part.get("Content-ID") or "").strip("<>") or None,
                    size_bytes=len(payload),
                    sha256=sha256(payload).hexdigest() if within_limit else None,
                    content_bytes=payload if within_limit else None,
                    content_complete=within_limit,
                )
            )
        return tuple(attachments)

    @staticmethod
    def _message_from_fetch_payload(
        *,
        payload,
        fetch_status: str,
        folder: str,
        provider_message_id: str,
        max_attachment_bytes: int,
    ) -> CustomEmailMessage | None:
        if fetch_status != "OK" or not payload:
            return None
        raw_message = next(
            (
                chunk[1]
                for chunk in payload
                if isinstance(chunk, tuple) and len(chunk) > 1 and isinstance(chunk[1], (bytes, bytearray))
            ),
            None,
        )
        if raw_message is None:
            return None
        flags_text = " ".join(
            chunk[0].decode("utf-8", errors="ignore")
            for chunk in payload
            if isinstance(chunk, tuple) and chunk and isinstance(chunk[0], (bytes, bytearray))
        )
        parsed = CustomEmailProviderClient._parse_message(
            raw_message=bytes(raw_message),
            folder=folder,
            is_unread="\\Seen" not in flags_text,
        )
        return CustomEmailMessage(
            provider_message_id=provider_message_id,
            folder=parsed.folder,
            from_display=parsed.from_display,
            from_email=parsed.from_email,
            subject=parsed.subject,
            snippet=parsed.snippet,
            body_text=parsed.body_text,
            to_display=parsed.to_display,
            to_email=parsed.to_email,
            is_unread=parsed.is_unread,
            is_archived=parsed.is_archived,
            received_at=parsed.received_at,
            message_header_id=parsed.message_header_id,
            attachments=tuple(
                attachment
                if attachment.size_bytes <= max_attachment_bytes
                else VaultEmailAttachment(
                    provider_part_key=attachment.provider_part_key,
                    file_name=attachment.file_name,
                    content_type=attachment.content_type,
                    content_disposition=attachment.content_disposition,
                    content_id=attachment.content_id,
                    size_bytes=attachment.size_bytes,
                    sha256=None,
                    content_bytes=None,
                    content_complete=False,
                )
                for attachment in parsed.attachments
            ),
        )

    @staticmethod
    def _response_int(*, mailbox, key: str) -> int | None:
        try:
            status, values = mailbox.response(key)
            if status != "OK" or not values:
                return None
            raw = values[0]
            return int(raw.decode("ascii") if isinstance(raw, bytes) else raw)
        except (AttributeError, TypeError, ValueError):
            return None

    @staticmethod
    def _uid_flags_from_fetch_payload(
        payload,
    ) -> tuple[tuple[int, tuple[str, ...]], ...]:
        snapshots: dict[int, tuple[str, ...]] = {}
        for item in payload or ():
            chunks = item if isinstance(item, tuple) else (item,)
            for chunk in chunks:
                if not isinstance(chunk, (bytes, bytearray)):
                    continue
                text = bytes(chunk).decode("utf-8", errors="ignore")
                uid_match = re.search(r"\bUID\s+(\d+)\b", text, re.IGNORECASE)
                flags_match = re.search(r"\bFLAGS\s+\(([^)]*)\)", text, re.IGNORECASE)
                if uid_match is None or flags_match is None:
                    continue
                snapshots[int(uid_match.group(1))] = tuple(
                    flag for flag in flags_match.group(1).split() if flag
                )
        return tuple(sorted(snapshots.items()))

    @staticmethod
    def _special_use_from_flags(*, flags: tuple[str, ...], folder_name: str) -> str | None:
        normalized_flags = {flag.casefold() for flag in flags}
        for flag, special_use in (
            ("\\inbox", "inbox"),
            ("\\sent", "sent"),
            ("\\drafts", "drafts"),
            ("\\archive", "archive"),
            ("\\junk", "junk"),
            ("\\trash", "trash"),
        ):
            if flag in normalized_flags:
                return special_use
        normalized_name = folder_name.replace(".", " ").replace("/", " ").casefold()
        if folder_name.upper() == "INBOX":
            return "inbox"
        for token, special_use in (
            ("sent", "sent"),
            ("draft", "drafts"),
            ("archive", "archive"),
            ("junk", "junk"),
            ("spam", "junk"),
            ("trash", "trash"),
            ("deleted", "trash"),
        ):
            if token in normalized_name:
                return special_use
        return None

    @staticmethod
    def _validated_ordinary_folder_name(
        folder_name: str,
        *,
        allow_inbox: bool = False,
        allow_archive: bool = False,
    ) -> str:
        normalized = str(folder_name or "").strip()
        if not normalized or any(character in normalized for character in ("\x00", "\r", "\n")):
            raise ValueError("A valid mailbox folder name is required.")
        special_use = CustomEmailProviderClient._special_use_from_flags(flags=(), folder_name=normalized)
        allowed = {"inbox"} if allow_inbox else set()
        if allow_archive:
            allowed.add("archive")
        if special_use and special_use not in allowed:
            raise ValueError("That protected provider folder cannot be used for this operation.")
        return normalized

    @staticmethod
    def _body_from_message(message) -> str | None:
        body_candidate = CustomEmailProviderClient._select_body_candidate(message)
        if body_candidate is not None:
            text = CustomEmailProviderClient._extract_text_from_part(body_candidate)
            if text:
                return text
        for part in message.walk():
            if CustomEmailProviderClient._is_attachment(part):
                continue
            text = CustomEmailProviderClient._extract_text_from_part(part)
            if text:
                return text
        return None

    @staticmethod
    def _select_body_candidate(message):
        get_body = getattr(message, "get_body", None)
        if callable(get_body):
            candidate = get_body(preferencelist=("plain", "html"))
            if candidate is not None and not CustomEmailProviderClient._is_attachment(candidate):
                return candidate
            candidate = get_body(preferencelist=("html", "plain"))
            if candidate is not None and not CustomEmailProviderClient._is_attachment(candidate):
                return candidate
        return None

    @staticmethod
    def _is_attachment(part) -> bool:
        disposition = (part.get("Content-Disposition") or "").lower()
        return "attachment" in disposition

    @staticmethod
    def _extract_text_from_part(part) -> str | None:
        content_type = part.get_content_type()
        if content_type not in {"text/plain", "text/html"}:
            return None
        try:
            text = part.get_content()
        except Exception:
            payload = part.get_payload(decode=True)
            if not payload:
                return None
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="ignore")
        if not isinstance(text, str):
            return None
        normalized = (
            CustomEmailProviderClient._html_to_text(text)
            if content_type == "text/html"
            else CustomEmailProviderClient._normalize_text(text)
        )
        return normalized or None

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

    @staticmethod
    def _html_to_text(html: str) -> str:
        cleaned = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
        cleaned = re.sub(r"(?i)<br\s*/?>", "\n", cleaned)
        cleaned = re.sub(r"(?i)</p\s*>", "\n\n", cleaned)
        cleaned = re.sub(r"(?i)</div\s*>", "\n", cleaned)
        cleaned = re.sub(r"(?i)</li\s*>", "\n", cleaned)
        cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
        cleaned = unescape(cleaned)
        cleaned = cleaned.replace("\xa0", " ")
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r" +([.,!?;:])", r"\1", cleaned)
        cleaned = re.sub(r" *\n *", "\n", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    @staticmethod
    def _resolve_archive_folder(mailbox) -> str:
        return CustomEmailProviderClient._resolve_special_folder(
            mailbox,
            flag="\\Archive",
            name_candidates=("archive", "archives"),
            fallback="Archive",
        )

    @staticmethod
    def _resolve_sent_folder(mailbox) -> str:
        return CustomEmailProviderClient._resolve_special_folder(
            mailbox,
            flag="\\Sent",
            name_candidates=("sent", "sent items", "sent messages"),
            fallback="Sent",
        )

    @staticmethod
    def _resolve_special_folder(
        mailbox,
        *,
        flag: str,
        name_candidates: tuple[str, ...],
        fallback: str,
    ) -> str:
        status, data = mailbox.list()
        if status != "OK" or not data:
            return fallback
        entries = [entry.decode("utf-8", errors="ignore") for entry in data if entry]
        lowered_flag = flag.lower()
        for entry in entries:
            if lowered_flag in entry.lower():
                return CustomEmailProviderClient._folder_name_from_list_entry(entry) or fallback
        for entry in entries:
            folder_name = CustomEmailProviderClient._folder_name_from_list_entry(entry)
            normalized = (folder_name or "").replace(".", " ").replace("/", " ").lower()
            if any(normalized == candidate or normalized.endswith(f" {candidate}") for candidate in name_candidates):
                return folder_name or fallback
        return fallback

    @staticmethod
    def _folder_name_from_list_entry(entry: str) -> str | None:
        match = re.search(r'\s"[^"]*"\s(.+)$', entry)
        if match:
            return match.group(1).strip().strip('"') or None
        parts = entry.rsplit(" ", 1)
        if len(parts) == 2:
            return parts[1].strip().strip('"') or None
        return None


# Canonical Vault names. The CustomEmail aliases remain temporarily for legacy
# compatibility imports while Cloud Email callers are retired.
VaultEmailCredentials = CustomEmailCredentials
VaultEmailMessage = CustomEmailMessage
VaultEmailProviderClient = CustomEmailProviderClient
VaultEmailSearchResult = CustomEmailSearchResult

__all__ = [
    "CustomEmailCredentials",
    "CustomEmailMessage",
    "CustomEmailProviderClient",
    "CustomEmailSearchResult",
    "VaultEmailCredentials",
    "VaultEmailAttachment",
    "VaultEmailFolder",
    "VaultEmailMessage",
    "VaultEmailMessagePage",
    "VaultEmailProviderClient",
    "VaultEmailProviderSyncSession",
    "VaultEmailSearchResult",
]
