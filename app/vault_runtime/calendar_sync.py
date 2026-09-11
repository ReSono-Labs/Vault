from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
from typing import Any, Mapping, Protocol

from app.vault_runtime.calendar_provider import (
    VaultCalendarEvent,
    VaultCalendarProviderClient,
    credentials_from_payload,
)
from app.vault_runtime.datastore.domains import DOMAIN_CALENDAR_EVENT_CACHE, DOMAIN_PROVIDER_CREDENTIALS
from app.vault_runtime.types import VaultMigrationExportItem


CALENDAR_SYNC_RETENTION_DAYS = 14
CALENDAR_SYNC_FAILURE_RETRY_SECONDS = 60
CALENDAR_SYNC_STATUS_COMPLETED = "completed"
CALENDAR_SYNC_STATUS_WAITING_FOR_CREDENTIALS = "waiting_for_vault_provider_credentials"
CALENDAR_SYNC_STATUS_FAILED = "failed_support_safe"


class VaultCalendarSyncStore(Protocol):
    def list_provider_credentials(self, *, provider_kind: str, limit: int) -> list[dict[str, Any]]:
        ...

    def list_provider_credentials_for_scope(
        self,
        *,
        account_id: str,
        workspace_id: str,
        provider_kind: str,
        linked_account_id: str | None = None,
        installed_skill_id: str | None = None,
        limit: int,
    ) -> list[dict[str, Any]]:
        ...

    def import_items(
        self,
        items: tuple[VaultMigrationExportItem, ...],
        *,
        account_id: str | None = None,
        workspace_id: str | None = None,
    ) -> int:
        ...

    def update_provider_private_record(
        self,
        *,
        account_id: str,
        workspace_id: str,
        domain: str,
        source_id: str,
        source_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        ...


@dataclass(frozen=True, slots=True)
class VaultCalendarSyncResult:
    processed_count: int
    synced_credential_count: int
    skipped_count: int
    event_count: int
    failed_count: int
    items: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "completed",
            "processedCount": self.processed_count,
            "syncedCredentialCount": self.synced_credential_count,
            "skippedCount": self.skipped_count,
            "eventCount": self.event_count,
            "failedCount": self.failed_count,
            "items": list(self.items),
        }


def calendar_event_cache_item(
    *,
    account_id: str,
    workspace_id: str,
    linked_account_id: str | None,
    provider_key: str | None,
    event: VaultCalendarEvent,
    cached_at: datetime,
) -> VaultMigrationExportItem:
    return _event_item(
        account_id=account_id,
        workspace_id=workspace_id,
        linked_account_id=linked_account_id,
        provider_key=provider_key,
        event=event,
        cached_at=cached_at,
    )


class VaultCalendarSyncProcessor:
    def __init__(
        self,
        *,
        store: VaultCalendarSyncStore,
        calendar_provider: VaultCalendarProviderClient | None = None,
    ) -> None:
        self._store = store
        self._calendar_provider = calendar_provider or VaultCalendarProviderClient()

    def sync_active_credentials(
        self,
        *,
        limit: int = 5,
        events_per_credential: int = 50,
        sync_interval_seconds: int = 300,
        force: bool = False,
        account_id: str | None = None,
        workspace_id: str | None = None,
        linked_account_id: str | None = None,
        starts_at_from: datetime | None = None,
        starts_at_to: datetime | None = None,
    ) -> VaultCalendarSyncResult:
        records = self._list_provider_credentials(
            limit=max(1, min(int(limit or 5), 100)),
            account_id=account_id,
            workspace_id=workspace_id,
            linked_account_id=linked_account_id,
        )
        items: list[dict[str, Any]] = []
        counters = {
            "synced": 0,
            "skipped": 0,
            "events": 0,
            "failed": 0,
        }
        now = datetime.now(UTC)
        for record in records:
            item = self._sync_record(
                record=record,
                now=now,
                events_per_credential=max(1, min(int(events_per_credential or 50), 250)),
                sync_interval_seconds=max(30, int(sync_interval_seconds or 300)),
                force=force,
                starts_at_from=starts_at_from,
                starts_at_to=starts_at_to,
            )
            status = str(item.get("status") or "")
            if status == "skipped_not_due":
                counters["skipped"] += 1
            elif status == CALENDAR_SYNC_STATUS_COMPLETED:
                counters["synced"] += 1
                counters["events"] += int(item.get("eventCount") or 0)
            elif status in {CALENDAR_SYNC_STATUS_FAILED, CALENDAR_SYNC_STATUS_WAITING_FOR_CREDENTIALS}:
                counters["failed"] += 1
            items.append(item)
        return VaultCalendarSyncResult(
            processed_count=len(records),
            synced_credential_count=counters["synced"],
            skipped_count=counters["skipped"],
            event_count=counters["events"],
            failed_count=counters["failed"],
            items=tuple(items),
        )

    def _list_provider_credentials(
        self,
        *,
        limit: int,
        account_id: str | None,
        workspace_id: str | None,
        linked_account_id: str | None,
    ) -> list[dict[str, Any]]:
        if account_id and workspace_id:
            list_scoped = getattr(self._store, "list_provider_credentials_for_scope", None)
            if callable(list_scoped):
                return list_scoped(
                    account_id=account_id,
                    workspace_id=workspace_id,
                    provider_kind="calendar",
                    linked_account_id=linked_account_id,
                    installed_skill_id=None,
                    limit=limit,
                )
        list_credentials = getattr(self._store, "list_provider_credentials", None)
        if not callable(list_credentials):
            return []
        records = list_credentials(provider_kind="calendar", limit=limit)
        return [
            record
            for record in records
            if _record_matches_scope(
                record=record,
                account_id=account_id,
                workspace_id=workspace_id,
                linked_account_id=linked_account_id,
            )
        ]

    def _sync_record(
        self,
        *,
        record: Mapping[str, Any],
        now: datetime,
        events_per_credential: int,
        sync_interval_seconds: int,
        force: bool,
        starts_at_from: datetime | None,
        starts_at_to: datetime | None,
    ) -> dict[str, Any]:
        payload = _source_payload(record)
        account_id = _required_text(record.get("accountId"), field="accountId")
        workspace_id = _required_text(record.get("workspaceId"), field="workspaceId")
        linked_account_id = _optional_text(payload.get("linkedAccountId") or payload.get("linked_account_id"))
        if payload.get("calendarSyncEnabled") is False or payload.get("syncEnabled") is False:
            return _support_item(record, status="skipped_disabled", event_count=0)
        if not force and not _sync_due(payload=payload, now=now, sync_interval_seconds=sync_interval_seconds):
            return _support_item(record, status="skipped_not_due", event_count=0)
        try:
            credentials = credentials_from_payload(payload)
        except Exception:
            self._mark_credential(
                record=record,
                now=now,
                status=CALENDAR_SYNC_STATUS_WAITING_FOR_CREDENTIALS,
                event_count=0,
                code="vault_calendar_credentials_missing",
            )
            return _support_item(
                record,
                status=CALENDAR_SYNC_STATUS_WAITING_FOR_CREDENTIALS,
                event_count=0,
                code="vault_calendar_credentials_missing",
            )
        try:
            starts_at_from = starts_at_from or (now - timedelta(days=14))
            starts_at_to = starts_at_to or (now + timedelta(days=90))
            events = self._calendar_provider.fetch_events(
                credentials=credentials,
                starts_at_from=starts_at_from,
                starts_at_to=starts_at_to,
                limit=events_per_credential,
            )
            import_items = tuple(
                _event_item(
                    account_id=account_id,
                    workspace_id=workspace_id,
                    linked_account_id=linked_account_id,
                    provider_key=_optional_text(payload.get("providerKey") or payload.get("provider_key")),
                    event=event,
                    cached_at=now,
                )
                for event in events
            )
            imported_count = self._store.import_items(import_items, account_id=account_id, workspace_id=workspace_id)
            self._mark_credential(
                record=record,
                now=now,
                status=CALENDAR_SYNC_STATUS_COMPLETED,
                event_count=len(events),
                code=None,
            )
            return _support_item(
                record,
                status=CALENDAR_SYNC_STATUS_COMPLETED,
                event_count=len(events),
                imported_count=imported_count,
            )
        except Exception as exc:
            self._mark_credential(
                record=record,
                now=now,
                status=CALENDAR_SYNC_STATUS_FAILED,
                event_count=0,
                code="vault_calendar_sync_failed",
                error_class=exc.__class__.__name__,
            )
            return _support_item(record, status=CALENDAR_SYNC_STATUS_FAILED, event_count=0, code="vault_calendar_sync_failed")

    def _mark_credential(
        self,
        *,
        record: Mapping[str, Any],
        now: datetime,
        status: str,
        event_count: int,
        code: str | None,
        error_class: str | None = None,
    ) -> None:
        payload = dict(_source_payload(record))
        payload["calendarSyncStatus"] = status
        payload["lastCalendarSyncAttemptedAt"] = _iso(now)
        payload["lastCalendarSyncEventCount"] = event_count
        if status == CALENDAR_SYNC_STATUS_COMPLETED:
            payload["lastCalendarSyncCompletedAt"] = _iso(now)
            payload["lastCalendarSyncErrorCode"] = None
            payload["lastCalendarSyncErrorClass"] = None
        else:
            payload["lastCalendarSyncErrorCode"] = code
            payload["lastCalendarSyncErrorClass"] = error_class
        self._store.update_provider_private_record(
            account_id=_required_text(record.get("accountId"), field="accountId"),
            workspace_id=_required_text(record.get("workspaceId"), field="workspaceId"),
            domain=_required_text(record.get("domain"), field="domain"),
            source_id=_required_text(record.get("sourceId"), field="sourceId"),
            source_payload=payload,
        )


def _event_item(
    *,
    account_id: str,
    workspace_id: str,
    linked_account_id: str | None,
    provider_key: str | None,
    event: VaultCalendarEvent,
    cached_at: datetime,
) -> VaultMigrationExportItem:
    source_id = _source_id(
        "vault-calendar-cache",
        account_id,
        workspace_id,
        linked_account_id or "",
        event.provider_event_id,
    )
    source_payload = {
        "calendar_event_cache_id": source_id,
        "calendarEventCacheId": source_id,
        "linked_account_id": linked_account_id,
        "linkedAccountId": linked_account_id,
        "provider_key": provider_key,
        "providerKey": provider_key,
        "provider_event_id": event.provider_event_id,
        "providerEventId": event.provider_event_id,
        "calendar_label": event.calendar_label,
        "calendarLabel": event.calendar_label,
        "title": event.title,
        "description": event.description,
        "location": event.location,
        "starts_at": _iso(event.starts_at),
        "startsAt": _iso(event.starts_at),
        "ends_at": _iso(event.ends_at) if event.ends_at is not None else None,
        "endsAt": _iso(event.ends_at) if event.ends_at is not None else None,
        "all_day": event.all_day,
        "allDay": event.all_day,
        "organizer": event.organizer,
        "cached_at": _iso(cached_at),
        "cachedAt": _iso(cached_at),
        "retention_expires_at": _iso(cached_at + timedelta(days=CALENDAR_SYNC_RETENTION_DAYS)),
    }
    content_text = _joined_text(
        (
            event.provider_event_id,
            event.calendar_label,
            event.title,
            event.description,
            event.location,
            _iso(event.starts_at),
            _iso(event.ends_at) if event.ends_at is not None else None,
            event.organizer,
        )
    )
    return VaultMigrationExportItem(
        domain=DOMAIN_CALENDAR_EVENT_CACHE,
        source_id=source_id,
        payload={
            "accountId": account_id,
            "workspaceId": workspace_id,
            "sourceTable": "calendar_event_cache",
            "sourcePrimaryKey": ["calendar_event_cache_id"],
            "sourceId": source_id,
            "sourcePayload": source_payload,
            "personalFields": ["calendar_label", "title", "description", "location", "organizer"],
            "cloudRetainedFields": [
                "linked_account_id",
                "provider_key",
                "cached_at",
                "retention_expires_at",
            ],
            "retentionClass": "vault_migratable_personal",
            "rowScope": "linked_account",
            "splitRequired": False,
            "contentText": content_text,
            "createdAt": _iso(cached_at),
            "updatedAt": _iso(cached_at),
        },
    )


def _support_item(
    record: Mapping[str, Any],
    *,
    status: str,
    event_count: int,
    imported_count: int = 0,
    code: str | None = None,
) -> dict[str, Any]:
    payload = _source_payload(record)
    return {
        "credentialId": _optional_text(payload.get("provider_credential_id") or payload.get("providerCredentialId") or record.get("sourceId")),
        "providerKind": "calendar",
        "linkedAccountId": _optional_text(payload.get("linkedAccountId") or payload.get("linked_account_id")),
        "status": status,
        "eventCount": event_count,
        "importedCount": imported_count,
        "code": code,
    }


def _sync_due(*, payload: Mapping[str, Any], now: datetime, sync_interval_seconds: int) -> bool:
    completed = _parse_iso(payload.get("lastCalendarSyncCompletedAt"))
    if completed is not None:
        return now - completed >= timedelta(seconds=sync_interval_seconds)
    attempted = _parse_iso(payload.get("lastCalendarSyncAttemptedAt"))
    if attempted is None:
        return True
    retry_seconds = min(sync_interval_seconds, CALENDAR_SYNC_FAILURE_RETRY_SECONDS)
    return now - attempted >= timedelta(seconds=retry_seconds)


def _record_matches_scope(
    *,
    record: Mapping[str, Any],
    account_id: str | None,
    workspace_id: str | None,
    linked_account_id: str | None,
) -> bool:
    payload = _source_payload(record)
    if account_id and _optional_text(record.get("accountId")) != account_id:
        return False
    if workspace_id and _optional_text(record.get("workspaceId")) != workspace_id:
        return False
    if linked_account_id and _optional_text(payload.get("linkedAccountId") or payload.get("linked_account_id")) != linked_account_id:
        return False
    return True


def _source_payload(record: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = record.get("sourcePayload")
    return payload if isinstance(payload, Mapping) else {}


def _required_text(value: Any, *, field: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise ValueError(f"{field}_required")
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _joined_text(values: tuple[Any, ...]) -> str | None:
    parts = [str(value).strip() for value in values if value is not None and str(value).strip()]
    return "\n".join(parts) if parts else None


def _source_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:32]}"


def _parse_iso(value: Any) -> datetime | None:
    text = _optional_text(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _iso(value: datetime) -> str:
    resolved = value.astimezone(UTC) if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return resolved.isoformat().replace("+00:00", "Z")
