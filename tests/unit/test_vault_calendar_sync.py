import json
from datetime import UTC, datetime, timedelta

from app.vault_runtime.calendar_provider import VaultCalendarEvent
from app.vault_runtime.calendar_sync import (
    CALENDAR_SYNC_STATUS_COMPLETED,
    CALENDAR_SYNC_STATUS_WAITING_FOR_CREDENTIALS,
    VaultCalendarSyncProcessor,
)
from app.vault_runtime.datastore.domains import DOMAIN_CALENDAR_EVENT_CACHE, DOMAIN_PROVIDER_CREDENTIALS


def test_vault_calendar_sync_fetches_events_with_vault_credentials_and_imports_cache_locally() -> None:
    store = FakeCalendarSyncStore(credentials=[_calendar_credential()])
    provider = FakeCalendarProvider(
        events=[
            VaultCalendarEvent(
                provider_event_id="caldav-event-1",
                title="Private calendar planning",
                starts_at=datetime(2026, 6, 10, 18, 0, tzinfo=UTC),
                ends_at=datetime(2026, 6, 10, 19, 0, tzinfo=UTC),
                all_day=False,
                description="Private calendar body",
                location="Private location",
                organizer="owner@example.test",
                calendar_label="Private Calendar",
            )
        ]
    )

    result = VaultCalendarSyncProcessor(store=store, calendar_provider=provider).sync_active_credentials(
        limit=5,
        events_per_credential=50,
        sync_interval_seconds=300,
    )

    assert result.processed_count == 1
    assert result.synced_credential_count == 1
    assert result.event_count == 1
    assert provider.fetches == [
        {
            "calendarUrl": "https://caldav.example.test/calendars/user/private/",
            "limit": 50,
        }
    ]
    assert len(store.imported_items) == 1
    item = store.imported_items[0]
    assert item.domain == DOMAIN_CALENDAR_EVENT_CACHE
    assert item.payload["sourceTable"] == "calendar_event_cache"
    assert item.payload["sourcePayload"]["title"] == "Private calendar planning"
    assert item.payload["sourcePayload"]["description"] == "Private calendar body"
    assert item.payload["sourcePayload"]["location"] == "Private location"
    credential_payload = store.record(DOMAIN_PROVIDER_CREDENTIALS, "calendar:calendar-linked-1")["sourcePayload"]
    assert credential_payload["calendarSyncStatus"] == CALENDAR_SYNC_STATUS_COMPLETED
    assert credential_payload["lastCalendarSyncEventCount"] == 1
    support_text = json.dumps(result.as_dict(), sort_keys=True)
    assert "Private calendar planning" not in support_text
    assert "Private location" not in support_text
    assert "caldav-secret" not in support_text


def test_vault_calendar_sync_waits_support_safe_when_credential_secret_missing() -> None:
    credential = _calendar_credential()
    credential["sourcePayload"]["credentials"].pop("password")
    store = FakeCalendarSyncStore(credentials=[credential])
    provider = FakeCalendarProvider(events=[])

    result = VaultCalendarSyncProcessor(store=store, calendar_provider=provider).sync_active_credentials()

    assert result.processed_count == 1
    assert result.failed_count == 1
    assert provider.fetches == []
    assert store.imported_items == []
    credential_payload = store.record(DOMAIN_PROVIDER_CREDENTIALS, "calendar:calendar-linked-1")["sourcePayload"]
    assert credential_payload["calendarSyncStatus"] == CALENDAR_SYNC_STATUS_WAITING_FOR_CREDENTIALS
    assert credential_payload["lastCalendarSyncErrorCode"] == "vault_calendar_credentials_missing"
    assert "caldav-secret" not in json.dumps(result.as_dict(), sort_keys=True)


def test_vault_calendar_sync_uses_completed_watermark_for_normal_cadence() -> None:
    credential = _calendar_credential()
    now = datetime.now(UTC)
    credential["sourcePayload"]["lastCalendarSyncAttemptedAt"] = (now - timedelta(minutes=10)).isoformat().replace("+00:00", "Z")
    credential["sourcePayload"]["lastCalendarSyncCompletedAt"] = now.isoformat().replace("+00:00", "Z")
    store = FakeCalendarSyncStore(credentials=[credential])
    provider = FakeCalendarProvider(events=[])

    result = VaultCalendarSyncProcessor(store=store, calendar_provider=provider).sync_active_credentials(
        sync_interval_seconds=300,
    )

    assert result.processed_count == 1
    assert result.skipped_count == 1
    assert provider.fetches == []
    assert store.imported_items == []


def test_vault_calendar_sync_retries_failed_attempts_before_full_cadence_interval() -> None:
    credential = _calendar_credential()
    now = datetime.now(UTC)
    credential["sourcePayload"]["lastCalendarSyncAttemptedAt"] = (now - timedelta(seconds=90)).isoformat().replace("+00:00", "Z")
    credential["sourcePayload"].pop("lastCalendarSyncCompletedAt", None)
    store = FakeCalendarSyncStore(credentials=[credential])
    provider = FakeCalendarProvider(events=[])

    result = VaultCalendarSyncProcessor(store=store, calendar_provider=provider).sync_active_credentials(
        sync_interval_seconds=300,
    )

    assert result.processed_count == 1
    assert result.synced_credential_count == 1
    assert provider.fetches == [
        {
            "calendarUrl": "https://caldav.example.test/calendars/user/private/",
            "limit": 50,
        }
    ]


class FakeCalendarSyncStore:
    def __init__(self, *, credentials: list[dict]) -> None:
        self.records = {
            (record["domain"], record["sourceId"]): record
            for record in credentials
        }
        self.imported_items = []

    def record(self, domain: str, source_id: str) -> dict:
        return self.records[(domain, source_id)]

    def list_provider_credentials(self, *, provider_kind: str, limit: int) -> list[dict]:
        records = [
            record
            for (domain, _source_id), record in self.records.items()
            if domain == DOMAIN_PROVIDER_CREDENTIALS
            and record["sourcePayload"].get("providerKind") == provider_kind
            and record["sourcePayload"].get("status", "active") == "active"
        ]
        return records[:limit]

    def import_items(self, items, *, account_id=None, workspace_id=None):
        self.imported_items.extend(items)
        for item in items:
            self.records[(item.domain, item.source_id)] = {
                "accountId": account_id or item.payload.get("accountId"),
                "workspaceId": workspace_id or item.payload.get("workspaceId"),
                "domain": item.domain,
                "sourceId": item.source_id,
                "sourcePayload": item.payload.get("sourcePayload"),
            }
        return len(items)

    def update_provider_private_record(
        self,
        *,
        account_id: str,
        workspace_id: str,
        domain: str,
        source_id: str,
        source_payload: dict,
    ) -> dict | None:
        record = self.records.get((domain, source_id))
        if record is None:
            return None
        record["sourcePayload"] = dict(source_payload)
        return record


class FakeCalendarProvider:
    def __init__(self, *, events: list[VaultCalendarEvent]) -> None:
        self.events = list(events)
        self.fetches = []

    def fetch_events(self, *, credentials, starts_at_from=None, starts_at_to=None, limit: int = 100):
        self.fetches.append({"calendarUrl": credentials.calendar_url, "limit": limit})
        return list(self.events)


def _calendar_credential() -> dict:
    return {
        "accountId": "account-1",
        "workspaceId": "workspace-1",
        "domain": DOMAIN_PROVIDER_CREDENTIALS,
        "sourceId": "calendar:calendar-linked-1",
        "sourcePayload": {
            "provider_credential_id": "calendar:calendar-linked-1",
            "providerKind": "calendar",
            "providerKey": "caldav",
            "configurationRef": "caldav-calendar",
            "linkedAccountId": "calendar-linked-1",
            "status": "active",
            "credentials": {
                "providerType": "caldav-calendar",
                "providerKey": "caldav",
                "calendarUrl": "https://caldav.example.test/calendars/user/private/",
                "username": "owner@example.test",
                "password": "caldav-secret",
            },
        },
    }
