from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path

import psycopg
import pytest

from app.core.security.tokens import hash_token
from app.vault_runtime.calendar_provider import VaultCalendarEvent
from app.vault_runtime.calendar_runtime import LocalCalendarRuntime
from app.vault_runtime.calendar_tools import register_calendar_tools
from app.vault_runtime.extensions.secrets import LocalMasterKey
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.local_identity.service import LocalIdentityService
from app.vault_runtime.personal_data import PersonalDataRepository
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolInvocationContext


class _CalendarProvider:
    def __init__(self) -> None:
        self.creates = 0

    def fetch_events(self, **_kwargs):
        return [VaultCalendarEvent(
            provider_event_id="event-1", title="Private appointment",
            starts_at=datetime(2026, 8, 30, 14, 0, tzinfo=UTC), ends_at=None,
            all_day=False, description="private body", location=None,
            organizer=None, calendar_label="Personal",
        )]

    def create_event(self, *, title, starts_at, ends_at, all_day, description=None,
                     location=None, **_kwargs):
        self.creates += 1
        return VaultCalendarEvent(
            provider_event_id="created-1", title=title, starts_at=starts_at,
            ends_at=ends_at, all_day=all_day, description=description,
            location=location, organizer=None, calendar_label="Personal",
        )


def test_calendar_credentials_are_encrypted_scoped_syncable_and_revocable(tmp_path: Path) -> None:
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
    provider = _CalendarProvider()
    runtime = LocalCalendarRuntime(
        database_url=database_url, master_key=LocalMasterKey(tmp_path / "calendar.key"),
        provider=provider, records=records,  # type: ignore[arg-type]
    )
    runtime.ensure_schema()
    connected = runtime.connect(owner.principal, {
        "providerType": "caldav", "displayName": "Private",
        "credentials": {"calendarUrl": "https://calendar.example.test/user/",
                        "username": "owner@example.test", "password": "calendar-secret"},
    }, validate=False)
    account_id = connected["calendarAccountId"]
    assert "calendar-secret" not in repr(connected)
    assert runtime.accounts(second.principal) == []
    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            "SELECT ciphertext,public_configuration::text FROM vault_private.vault_calendar_accounts WHERE calendar_account_id=%s",
            (account_id,),
        ).fetchone()
    assert row is not None and b"calendar-secret" not in bytes(row[0])
    assert "calendar-secret" not in row[1] and "owner@example.test" not in row[1]
    result = runtime.sync(owner.principal, account_id)
    assert result["eventCount"] == 1 and result["failedCount"] == 0
    assert runtime.events(owner.principal)[0]["sourcePayload"]["title"] == "Private appointment"
    assert runtime.events(second.principal) == []
    catalog = ToolCatalog(authorizer=lambda _definition, _context: True)
    register_calendar_tools(catalog=catalog, runtime=runtime, records=records)
    context = ToolInvocationContext(
        agent=AgentKind.VOICE, user_id=owner.principal.user_id,
        workspace_id=owner.principal.workspace_id, tool_call_id="calendar-call-1",
        local_session_id="local-1", voice_session_id="voice-1",
    )
    prepared = catalog.invoke("calendar_create", {
        "linkedAccountId": account_id, "title": "Confirmed event",
        "startsAt": "2026-09-01T12:00:00+00:00",
    }, context=context)
    assert not prepared.is_error and prepared.structured_content["status"] == "pending_confirmation"
    assert provider.creates == 0
    confirmed = catalog.invoke("calendar_create", {
        "pendingActionId": prepared.structured_content["pendingActionId"], "approve": True,
    }, context=ToolInvocationContext(
        agent=AgentKind.VOICE, user_id=owner.principal.user_id,
        workspace_id=owner.principal.workspace_id, tool_call_id="calendar-call-2",
        local_session_id="local-1", voice_session_id="voice-1",
    ))
    assert not confirmed.is_error and confirmed.structured_content["status"] == "completed"
    assert provider.creates == 1
    replay = catalog.invoke("calendar_create", {
        "pendingActionId": prepared.structured_content["pendingActionId"], "approve": True,
    }, context=context)
    assert replay.is_error and provider.creates == 1
    runtime.remove(owner.principal, account_id)
    assert runtime.accounts(owner.principal) == []
    with pytest.raises(LookupError):
        runtime.remove(owner.principal, account_id)
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
