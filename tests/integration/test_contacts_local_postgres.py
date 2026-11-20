from __future__ import annotations

import os

import psycopg
import pytest

from app.core.security.tokens import hash_token
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.local_identity.service import LocalIdentityService
from app.vault_runtime.personal_data import PersonalDataRepository
from app.vault_runtime.session_tools.brokers.contacts import contacts_tool_result


def test_contacts_carry_confirmation_query_before_limit_and_user_isolation() -> None:
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
    identities.create_user(
        actor=owner.principal, username="second", password="second-password",
        display_name="Second", experience_style="warm",
    )
    second = identities.login(username="second", password="second-password")
    records = PersonalDataRepository(database_url=database_url)
    records.ensure_schema()
    prepared = contacts_tool_result(
        store=records, account_id=owner.principal.user_id,
        workspace_id=owner.principal.workspace_id,
        voice_realtime_session_id="voice-1", tool_call_id="call-1",
        tool_name="contacts_prepare_save",
        arguments={"actionType": "create", "firstName": "Ada", "lastName": "Lovelace", "emailAddress": "ada@example.com"},
    )
    assert prepared["status"] == "pending"
    assert records.list_private_records(
        account_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        source_table="contacts_entries", limit=10,
    ) == []
    confirmed = contacts_tool_result(
        store=records, account_id=owner.principal.user_id,
        workspace_id=owner.principal.workspace_id,
        voice_realtime_session_id="voice-1", tool_call_id="call-2",
        tool_name="contacts_confirm_pending",
        arguments={"pendingActionId": prepared["pendingActionId"], "approve": True},
    )
    assert confirmed["status"] == "confirmed"
    found = contacts_tool_result(
        store=records, account_id=owner.principal.user_id,
        workspace_id=owner.principal.workspace_id,
        voice_realtime_session_id="voice-1", tool_call_id="call-3",
        tool_name="contacts_search", arguments={"query": "ada@example.com", "limit": 1},
    )
    assert found["matchCount"] == 1 and found["contacts"][0]["displayName"] == "Ada Lovelace"
    assert contacts_tool_result(
        store=records, account_id=second.principal.user_id,
        workspace_id=second.principal.workspace_id,
        voice_realtime_session_id="voice-2", tool_call_id="call-4",
        tool_name="contacts_search", arguments={"query": "ada@example.com", "limit": 5},
    )["matchCount"] == 0
    with pytest.raises(PermissionError):
        records.list_private_records(
            account_id=second.principal.user_id,
            workspace_id=owner.principal.workspace_id,
            source_table="contacts_entries", limit=10,
        )
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
