from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

from app.core.security.tokens import hash_token
from app.vault_runtime.email_runtime import LocalEmailRuntime
from app.vault_runtime.email_tools import register_email_tools
from app.vault_runtime.email_schema import ensure_email_schema
from app.vault_runtime.extensions.secrets import LocalMasterKey
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.local_identity.service import LocalIdentityService
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolInvocationContext


def _credentials(address: str, suffix: str) -> dict[str, object]:
    return {
        "emailAddress": address,
        "imap": {"host": "imap.example.com", "port": 993, "username": address, "password": f"imap-{suffix}", "useTls": True},
        "smtp": {"host": "smtp.example.com", "port": 465, "username": address, "password": f"smtp-{suffix}", "useTls": True},
    }


def test_mail_is_multi_account_encrypted_and_principal_scoped(tmp_path: Path) -> None:
    database_url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("VAULT_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
    identities = LocalIdentityService(
        repository=LocalIdentityRepository(database_url=database_url),
        setup_credential_hash=hash_token("setup"),
    )
    identities.ensure_schema()
    owner = identities.bootstrap_owner(
        setup_credential="setup", username="owner", password="owner-password",
        display_name="Owner", experience_style="strict",
    )
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            ensure_email_schema(cursor)
    runtime = LocalEmailRuntime(
        database_url=database_url,
        master_key=LocalMasterKey(tmp_path / "mail-credentials.key"),
    )
    with runtime.service(owner.principal) as mail:
        first = mail.connect_mailbox(
            account_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
            mailbox_role="normal_email", credentials_payload=_credentials("first@example.com", "one"),
            display_name="Personal", validate_connection=False,
        )
        second = mail.connect_mailbox(
            account_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
            mailbox_role="normal_email", credentials_payload=_credentials("second@example.com", "two"),
            display_name="Work", validate_connection=False,
        )
        listed = mail.list_mailboxes(
            account_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        )
        assert {item["mailboxAccountId"] for item in listed} == {
            first["mailboxAccountId"], second["mailboxAccountId"],
        }
        assert {item["displayName"] for item in listed} == {"Personal", "Work"}
        with pytest.raises(PermissionError):
            mail.list_mailboxes(account_id="another-user", workspace_id=owner.principal.workspace_id)
        with pytest.raises(ValueError):
            mail.connect_mailbox(
                account_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
                mailbox_role="unsupported", credentials_payload=_credentials("agent@example.com", "three"),
                validate_connection=False,
            )
    catalog = ToolCatalog(authorizer=lambda _definition, _context: True)
    register_email_tools(catalog=catalog, runtime=runtime)
    context = ToolInvocationContext(
        agent=AgentKind.VOICE, user_id=owner.principal.user_id,
        workspace_id=owner.principal.workspace_id, tool_call_id="mail-call-1",
        local_session_id="local-1", voice_session_id="voice-1",
    )
    status = catalog.invoke("email_account_status", {}, context=context)
    assert not status.is_error and status.structured_content["count"] == 2
    ambiguous = catalog.invoke("email_check", {}, context=context)
    assert ambiguous.is_error and "mailboxAccountId is required" in ambiguous.text
    with psycopg.connect(database_url) as connection:
        rows = connection.execute(
            "SELECT nonce,ciphertext FROM vault_private.vault_email_provider_credentials"
        ).fetchall()
        dump = b"".join(bytes(row[0]) + bytes(row[1]) for row in rows)
    assert len(rows) == 2
    assert b"imap-one" not in dump and b"smtp-two" not in dump
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
