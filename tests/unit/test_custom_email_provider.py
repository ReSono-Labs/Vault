from email.message import EmailMessage
import logging

from app.vault_runtime import email_provider as custom_email_provider
from app.vault_runtime.email_provider import VaultEmailCredentials as CustomEmailCredentials
from app.vault_runtime.email_provider import VaultEmailProviderClient as CustomEmailProviderClient


def _raw_message(message: EmailMessage) -> bytes:
    return message.as_bytes()


def test_body_from_plain_text_message() -> None:
    message = EmailMessage()
    message["Subject"] = "Plain"
    message["From"] = "sender@example.com"
    message["To"] = "user@example.com"
    message.set_content("Hello from plain text.")

    parsed = CustomEmailProviderClient._parse_message(raw_message=_raw_message(message), folder="INBOX", is_unread=True)

    assert parsed.body_text == "Hello from plain text."
    assert parsed.snippet == "Hello from plain text."


def test_body_from_html_only_message() -> None:
    message = EmailMessage()
    message["Subject"] = "HTML"
    message["From"] = "sender@example.com"
    message["To"] = "user@example.com"
    message.add_alternative(
        "<html><body><p>Hello <strong>Christian</strong>.</p><p>Your order is complete.</p></body></html>",
        subtype="html",
    )

    parsed = CustomEmailProviderClient._parse_message(raw_message=_raw_message(message), folder="INBOX", is_unread=True)

    assert parsed.body_text == "Hello Christian.\n\nYour order is complete."
    assert parsed.snippet == "Hello Christian.\n\nYour order is complete."


def test_body_prefers_plain_text_over_html_when_both_exist() -> None:
    message = EmailMessage()
    message["Subject"] = "Multipart"
    message["From"] = "sender@example.com"
    message["To"] = "user@example.com"
    message.set_content("Readable plain text body.")
    message.add_alternative("<html><body><p>HTML body.</p></body></html>", subtype="html")

    parsed = CustomEmailProviderClient._parse_message(raw_message=_raw_message(message), folder="INBOX", is_unread=True)

    assert parsed.body_text == "Readable plain text body."


def test_body_ignores_attachments_and_reads_inline_html() -> None:
    message = EmailMessage()
    message["Subject"] = "Attachment"
    message["From"] = "sender@example.com"
    message["To"] = "user@example.com"
    message.make_mixed()

    body = EmailMessage()
    body.add_alternative("<html><body><div>Status update</div><div>Attachment included</div></body></html>", subtype="html")
    message.attach(body)

    attachment = EmailMessage()
    attachment.set_content("not the body")
    attachment.add_header("Content-Disposition", "attachment", filename="note.txt")
    message.attach(attachment)

    parsed = CustomEmailProviderClient._parse_message(raw_message=_raw_message(message), folder="INBOX", is_unread=True)

    assert parsed.body_text == "Status update\nAttachment included"


def test_sent_folder_resolves_hostinger_inbox_sent() -> None:
    class FakeMailbox:
        def list(self):
            return (
                "OK",
                [
                    b'(\\HasChildren) "." INBOX',
                    b'(\\HasNoChildren \\UnMarked \\Sent) "." INBOX.Sent',
                    b'(\\HasNoChildren \\UnMarked \\Drafts) "." INBOX.Drafts',
                ],
            )

    assert CustomEmailProviderClient._resolve_sent_folder(FakeMailbox()) == "INBOX.Sent"


def test_send_message_appends_copy_to_sent_folder(monkeypatch) -> None:
    sent_messages: list[EmailMessage] = []
    appended: list[dict] = []

    class FakeSmtp:
        def __init__(self, host, port, timeout=None):
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def login(self, username, password):
            return None

        def send_message(self, message):
            sent_messages.append(message)

    class FakeMailbox:
        def __init__(self, host, port, timeout=None):
            self.host = host
            self.port = port
            self.timeout = timeout

        def login(self, username, password):
            return None

        def list(self):
            return ("OK", [b'(\\HasNoChildren \\UnMarked \\Sent) "." INBOX.Sent'])

        def append(self, folder, flags, date_time, message):
            appended.append({"folder": folder, "flags": flags, "date_time": date_time, "message": message})
            return "OK", []

        def logout(self):
            return None

    monkeypatch.setattr(custom_email_provider, "validate_public_host", lambda host, target: host)
    monkeypatch.setattr(custom_email_provider.smtplib, "SMTP_SSL", FakeSmtp)
    monkeypatch.setattr(
        custom_email_provider,
        "_open_imap_connection",
        lambda **kwargs: FakeMailbox(
            kwargs["host"], kwargs["port"], timeout=kwargs["timeout"]
        ),
    )

    CustomEmailProviderClient().send_message(
        credentials=CustomEmailCredentials(
            email_address="owner@example.com",
            imap_host="imap.example.com",
            imap_port=993,
            imap_username="owner@example.com",
            imap_password="secret",
            imap_use_tls=True,
            smtp_host="smtp.example.com",
            smtp_port=465,
            smtp_username="owner@example.com",
            smtp_password="secret",
            smtp_use_tls=True,
        ),
        to_recipients=["recipient@example.com"],
        subject="Sent copy",
        body="Body text",
    )

    assert sent_messages[0]["Subject"] == "Sent copy"
    assert appended[0]["folder"] == "INBOX.Sent"
    assert appended[0]["flags"] == "\\Seen"
    assert b"Subject: Sent copy" in appended[0]["message"]


def test_provider_applies_explicit_timeouts_to_imap_and_smtp(monkeypatch) -> None:
    imap_timeouts: list[float] = []
    smtp_timeouts: list[float] = []

    class FakeSmtp:
        def __init__(self, host, port, timeout=None):
            smtp_timeouts.append(timeout)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def login(self, username, password):
            return None

    class FakeMailbox:
        def __init__(self, host, port, timeout=None):
            imap_timeouts.append(timeout)

        def login(self, username, password):
            return None

        def logout(self):
            return None

    monkeypatch.setattr(custom_email_provider, "validate_public_host", lambda host, target: host)
    monkeypatch.setattr(custom_email_provider.smtplib, "SMTP_SSL", FakeSmtp)
    monkeypatch.setattr(
        custom_email_provider,
        "_open_imap_connection",
        lambda **kwargs: FakeMailbox(
            kwargs["host"], kwargs["port"], timeout=kwargs["timeout"]
        ),
    )

    CustomEmailProviderClient(timeout_seconds=7).validate_credentials(
        credentials=CustomEmailCredentials(
            email_address="owner@example.com",
            imap_host="imap.example.com",
            imap_port=993,
            imap_username="owner@example.com",
            imap_password="secret",
            imap_use_tls=True,
            smtp_host="smtp.example.com",
            smtp_port=465,
            smtp_username="owner@example.com",
            smtp_password="secret",
            smtp_use_tls=True,
        )
    )

    assert imap_timeouts == [7.0]
    assert smtp_timeouts == [7.0]


def test_sync_session_reuses_one_connection_and_logs_support_safe_timings(
    monkeypatch, caplog
) -> None:
    connection_count = 0
    login_count = 0
    logout_count = 0
    fetch_count = 0

    class FakeMailbox:
        def __init__(self, host, port, timeout=None):
            nonlocal connection_count
            del host, port, timeout
            connection_count += 1

        def login(self, username, password):
            nonlocal login_count
            del username, password
            login_count += 1
            return "OK", []

        def list(self):
            return "OK", [
                b'(\\HasNoChildren \\Inbox) "." INBOX',
                b'(\\HasNoChildren \\Sent) "." INBOX.Sent',
            ]

        def select(self, folder, readonly=False):
            del folder, readonly
            return "OK", [b"0"]

        def response(self, key):
            return "OK", [b"1" if key == "UIDVALIDITY" else b"10"]

        def uid(self, command, *args):
            nonlocal fetch_count
            if command == "SEARCH":
                return "OK", [b""]
            if command == "FETCH" and args[-1] == "(UID FLAGS)":
                return "OK", []
            fetch_count += 1
            return "OK", []

        def logout(self):
            nonlocal logout_count
            logout_count += 1
            return "BYE", []

    credentials = CustomEmailCredentials(
        email_address="owner@example.com",
        imap_host="imap.example.com",
        imap_port=993,
        imap_username="owner@example.com",
        imap_password="secret-value",
        imap_use_tls=True,
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_username="owner@example.com",
        smtp_password="secret-value",
        smtp_use_tls=True,
    )
    monkeypatch.setattr(custom_email_provider, "validate_public_host", lambda host, target: host)
    monkeypatch.setattr(
        custom_email_provider,
        "_open_imap_connection",
        lambda **kwargs: FakeMailbox(
            kwargs["host"], kwargs["port"], timeout=kwargs["timeout"]
        ),
    )

    with caplog.at_level(logging.INFO, logger=custom_email_provider.__name__):
        with CustomEmailProviderClient().sync_session(credentials=credentials) as session:
            folders = session.list_folders()
            for folder in folders:
                page = session.fetch_message_page(folder=folder, after_uid=9)
                assert page.messages == ()

    assert connection_count == 1
    assert login_count == 1
    assert logout_count == 1
    assert fetch_count == 0
    assert {"connect", "login", "list", "select", "flags", "search", "fetch", "logout"} <= {
        record.getMessage().split("operation=", 1)[1].split(" ", 1)[0]
        for record in caplog.records
        if "operation=" in record.getMessage()
    }
    combined_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "owner@example.com" not in combined_logs
    assert "imap.example.com" not in combined_logs
    assert "secret-value" not in combined_logs


def test_uid_flag_snapshot_parses_existing_message_state() -> None:
    assert CustomEmailProviderClient._uid_flags_from_fetch_payload(
        [
            b"1 (UID 7 FLAGS (\\Seen))",
            (b"2 (UID 9 FLAGS (\\Flagged custom))", b")"),
            None,
        ]
    ) == (
        (7, ("\\Seen",)),
        (9, ("\\Flagged", "custom")),
    )


def test_existing_message_mutations_use_stable_imap_uids(monkeypatch) -> None:
    calls: list[tuple] = []

    class FakeMailbox:
        capabilities = ("IMAP4REV1", "MOVE")

        def login(self, username, password):
            del username, password
            return "OK", []

        def select(self, folder):
            calls.append(("select", folder))
            return "OK", []

        def uid(self, command, *args):
            calls.append(("uid", command, *args))
            return "OK", []

        def logout(self):
            return "BYE", []

    mailbox = FakeMailbox()
    monkeypatch.setattr(
        custom_email_provider,
        "_open_imap_connection",
        lambda **kwargs: mailbox,
    )
    monkeypatch.setattr(
        custom_email_provider, "validate_public_host", lambda host, target: host
    )
    credentials = CustomEmailCredentials(
        email_address="owner@example.com",
        imap_host="imap.example.com",
        imap_port=993,
        imap_username="owner@example.com",
        imap_password="secret",
        imap_use_tls=True,
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_username="owner@example.com",
        smtp_password="secret",
        smtp_use_tls=True,
    )
    client = CustomEmailProviderClient()

    client.set_read_state(
        credentials=credentials,
        message_id="427",
        source_folder="INBOX",
        is_read=True,
    )
    client.move_message(
        credentials=credentials,
        message_id="427",
        source_folder="INBOX",
        destination_folder="Archive",
    )
    client.move_message(
        credentials=credentials,
        message_id="428",
        source_folder="Archive",
        destination_folder="INBOX",
    )

    assert ("uid", "STORE", "427", "+FLAGS", "\\Seen") in calls
    assert ("uid", "MOVE", "427", "Archive") in calls
    assert ("uid", "MOVE", "428", "INBOX") in calls
    assert not any(call[0] in {"store", "copy", "move"} for call in calls)


def test_dual_stack_connection_prefers_ipv4_without_hardcoding_provider_ip(
    monkeypatch,
) -> None:
    attempts: list[int] = []

    class FakeSocket:
        def __init__(self, family, socket_type, protocol):
            del socket_type, protocol
            self.family = family

        def settimeout(self, timeout):
            assert timeout == 7

        def connect(self, address):
            del address
            attempts.append(self.family)

        def close(self):
            return None

    monkeypatch.setattr(
        custom_email_provider.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (custom_email_provider.socket.AF_INET6, custom_email_provider.socket.SOCK_STREAM, 6, "", ("2001:db8::1", 993, 0, 0)),
            (custom_email_provider.socket.AF_INET, custom_email_provider.socket.SOCK_STREAM, 6, "", ("192.0.2.1", 993)),
        ],
    )
    monkeypatch.setattr(custom_email_provider.socket, "socket", FakeSocket)

    connection = custom_email_provider._create_connection_ipv4_preferred(
        ("imap.example.test", 993), 7
    )

    assert connection.family == custom_email_provider.socket.AF_INET
    assert attempts == [custom_email_provider.socket.AF_INET]


def test_dual_stack_connection_falls_back_to_ipv6_when_ipv4_fails(
    monkeypatch,
) -> None:
    attempts: list[int] = []

    class FakeSocket:
        def __init__(self, family, socket_type, protocol):
            del socket_type, protocol
            self.family = family

        def settimeout(self, timeout):
            del timeout

        def connect(self, address):
            del address
            attempts.append(self.family)
            if self.family == custom_email_provider.socket.AF_INET:
                raise OSError("ipv4 unavailable")

        def close(self):
            return None

    monkeypatch.setattr(
        custom_email_provider.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (custom_email_provider.socket.AF_INET6, custom_email_provider.socket.SOCK_STREAM, 6, "", ("2001:db8::1", 993, 0, 0)),
            (custom_email_provider.socket.AF_INET, custom_email_provider.socket.SOCK_STREAM, 6, "", ("192.0.2.1", 993)),
        ],
    )
    monkeypatch.setattr(custom_email_provider.socket, "socket", FakeSocket)

    connection = custom_email_provider._create_connection_ipv4_preferred(
        ("imap.example.test", 993), 7
    )

    assert connection.family == custom_email_provider.socket.AF_INET6
    assert attempts == [
        custom_email_provider.socket.AF_INET,
        custom_email_provider.socket.AF_INET6,
    ]


def test_search_messages_uses_live_imap_search_and_returns_freshness_metadata(monkeypatch) -> None:
    first = EmailMessage()
    first["Subject"] = "Old status"
    first["From"] = "old@example.com"
    first["To"] = "owner@example.com"
    first.set_content("Older message.")

    second = EmailMessage()
    second["Subject"] = "Fresh launch status"
    second["From"] = "alex@example.com"
    second["To"] = "owner@example.com"
    second.set_content("Fresh launch update.")

    raw_messages = {
        b"1": _raw_message(first),
        b"2": _raw_message(second),
    }
    search_calls: list[tuple] = []

    class FakeMailbox:
        def __init__(self, host, port, timeout=None):
            self.host = host
            self.port = port
            self.timeout = timeout
            self.selected_folder = "INBOX"

        def login(self, username, password):
            return None

        def list(self):
            return ("OK", [b'(\\HasNoChildren) "." INBOX'])

        def select(self, folder, readonly=False):
            self.selected_folder = folder
            return "OK", []

        def search(self, charset, *criteria):
            search_calls.append((charset, criteria))
            return "OK", [b"1 2"]

        def fetch(self, message_id, query):
            return "OK", [(b"FLAGS (\\Seen)", raw_messages[message_id])]

        def logout(self):
            return None

    monkeypatch.setattr(custom_email_provider, "validate_public_host", lambda host, target: host)
    monkeypatch.setattr(
        custom_email_provider,
        "_open_imap_connection",
        lambda **kwargs: FakeMailbox(
            kwargs["host"], kwargs["port"], timeout=kwargs["timeout"]
        ),
    )

    result = CustomEmailProviderClient().search_messages(
        credentials=CustomEmailCredentials(
            email_address="owner@example.com",
            imap_host="imap.example.com",
            imap_port=993,
            imap_username="owner@example.com",
            imap_password="secret",
            imap_use_tls=True,
            smtp_host="smtp.example.com",
            smtp_port=465,
            smtp_username="owner@example.com",
            smtp_password="secret",
            smtp_use_tls=True,
        ),
        query="fresh",
        limit=5,
    )

    assert result.folders_searched == ["INBOX"]
    assert result.results_may_be_partial is False
    assert [message.subject for message in result.messages] == ["Fresh launch status"]
    assert search_calls[0][0] == "UTF-8"
    assert search_calls[0][1] == ("TEXT", '"fresh"')
