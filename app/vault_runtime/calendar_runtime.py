"""Local authority adapter around the copied Voice Calendar provider and sync."""

from __future__ import annotations

import json
import os
from typing import Any
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from psycopg.types.json import Jsonb

from app.vault_runtime.calendar_provider import VaultCalendarProviderClient, credentials_from_payload
from app.vault_runtime.calendar_sync import VaultCalendarSyncProcessor, calendar_event_cache_item
from app.vault_runtime.extensions.secrets import LocalMasterKey
from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.personal_data import PersonalDataRepository


SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS vault_private.vault_calendar_accounts (
      calendar_account_id text PRIMARY KEY,
      account_id text NOT NULL REFERENCES vault_private.local_users(user_id) ON DELETE CASCADE,
      workspace_id text NOT NULL REFERENCES vault_private.local_workspaces(workspace_id) ON DELETE CASCADE,
      provider_type text NOT NULL CHECK (provider_type IN ('ics','caldav')),
      display_name text NOT NULL,
      public_configuration jsonb NOT NULL,
      nonce bytea NOT NULL,
      ciphertext bytea NOT NULL,
      status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled')),
      sync_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      UNIQUE(account_id,workspace_id,calendar_account_id)
    )""",
    """CREATE INDEX IF NOT EXISTS ix_vault_calendar_accounts_scope
       ON vault_private.vault_calendar_accounts(account_id,workspace_id,status,updated_at DESC)""",
)


class LocalCalendarRuntime:
    def __init__(
        self, *, database_url: str, master_key: LocalMasterKey,
        provider: VaultCalendarProviderClient | None = None,
        records: PersonalDataRepository | None = None,
    ) -> None:
        self._database_url = database_url
        self._master_key = master_key
        self._provider = provider or VaultCalendarProviderClient()
        self._records = records or PersonalDataRepository(database_url=database_url)

    def ensure_schema(self) -> None:
        import psycopg
        with psycopg.connect(self._database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                for statement in SCHEMA_STATEMENTS:
                    cursor.execute(statement)

    def connect(self, principal: LocalPrincipal, payload: dict[str, Any], *, validate: bool = True) -> dict[str, Any]:
        provider_type = str(payload.get("providerType") or "").strip().lower()
        if provider_type not in {"ics", "caldav"}:
            raise ValueError("Calendar providerType must be ics or caldav.")
        credentials = payload.get("credentials")
        if not isinstance(credentials, dict):
            raise ValueError("Calendar credentials are required.")
        credential_payload = _credential_payload(provider_type, credentials)
        parsed = credentials_from_payload({"credentials": credential_payload})
        if validate:
            if provider_type == "ics":
                self._provider._ics.validate_feed(credentials=self._provider_credentials_ics(parsed))
            else:
                self._provider._caldav.validate_calendar(credentials=self._provider_credentials_caldav(parsed))
        account_id = f"calendar-{uuid4()}"
        public = {
            key: value for key, value in credential_payload.items()
            if key not in {"password", "username"}
        }
        plaintext = json.dumps(credential_payload, sort_keys=True, separators=(",", ":")).encode()
        nonce = os.urandom(12)
        aad = self._aad(principal, account_id)
        ciphertext = AESGCM(self._master_key.load_or_create()).encrypt(nonce, plaintext, aad)
        import psycopg
        with psycopg.connect(self._database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, principal)
                cursor.execute(
                    """INSERT INTO vault_private.vault_calendar_accounts
                       (calendar_account_id,account_id,workspace_id,provider_type,display_name,
                        public_configuration,nonce,ciphertext)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (account_id,principal.user_id,principal.workspace_id,provider_type,
                     str(payload.get("displayName") or provider_type.upper()).strip(),
                     Jsonb(public),nonce,ciphertext),
                )
        return self.account(principal, account_id)

    @staticmethod
    def _provider_credentials_ics(credentials):
        from app.modules.integrations.calendar_ics_provider import IcsCalendarCredentials
        return IcsCalendarCredentials(feed_url=str(credentials.feed_url or credentials.calendar_url))

    @staticmethod
    def _provider_credentials_caldav(credentials):
        from app.modules.integrations.caldav_calendar_provider import CaldavCalendarCredentials
        return CaldavCalendarCredentials(
            username=str(credentials.username or ""), password=str(credentials.password or ""),
            calendar_url=credentials.calendar_url,
        )

    def accounts(self, principal: LocalPrincipal) -> list[dict[str, Any]]:
        import psycopg
        with psycopg.connect(self._database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, principal)
                cursor.execute(
                    """SELECT calendar_account_id,provider_type,display_name,public_configuration,
                              status,sync_metadata,updated_at
                       FROM vault_private.vault_calendar_accounts
                       WHERE account_id=%s AND workspace_id=%s ORDER BY created_at,calendar_account_id""",
                    (principal.user_id,principal.workspace_id),
                )
                return [_public_account(row) for row in cursor.fetchall()]

    def account(self, principal: LocalPrincipal, calendar_account_id: str) -> dict[str, Any]:
        items = [item for item in self.accounts(principal) if item["calendarAccountId"] == calendar_account_id]
        if not items:
            raise LookupError("Calendar account was not found.")
        return items[0]

    def sync(self, principal: LocalPrincipal, calendar_account_id: str) -> dict[str, Any]:
        store = _ScopedCalendarStore(runtime=self, principal=principal)
        result = VaultCalendarSyncProcessor(store=store, calendar_provider=self._provider).sync_active_credentials(
            account_id=principal.user_id, workspace_id=principal.workspace_id,
            linked_account_id=calendar_account_id, limit=1, force=True,
        )
        return result.as_dict()

    def events(self, principal: LocalPrincipal, *, limit: int = 250) -> list[dict[str, Any]]:
        return self._records.list_private_records(
            account_id=principal.user_id, workspace_id=principal.workspace_id,
            source_table="calendar_event_cache", limit=limit,
        )

    def create_event(self, principal: LocalPrincipal, calendar_account_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        from datetime import UTC, datetime
        record = self._credential_record(principal, calendar_account_id)
        if record is None:
            raise LookupError("Calendar account was not found.")
        credentials = credentials_from_payload(record["sourcePayload"])
        starts_at = _iso_datetime(arguments.get("startsAt"), "startsAt")
        ends_at = _iso_datetime(arguments.get("endsAt"), "endsAt") if arguments.get("endsAt") else None
        event = self._provider.create_event(
            credentials=credentials, title=str(arguments.get("title") or "").strip(),
            starts_at=starts_at, ends_at=ends_at, all_day=bool(arguments.get("allDay", False)),
            description=str(arguments.get("description") or "").strip() or None,
            location=str(arguments.get("location") or "").strip() or None,
        )
        item = calendar_event_cache_item(
            account_id=principal.user_id, workspace_id=principal.workspace_id,
            linked_account_id=calendar_account_id, provider_key=credentials.provider_key,
            event=event, cached_at=datetime.now(UTC),
        )
        self._records.import_items((item,), account_id=principal.user_id, workspace_id=principal.workspace_id)
        return {"eventId": event.provider_event_id, "title": event.title,
                "startsAt": event.starts_at.isoformat(), "endsAt": event.ends_at.isoformat() if event.ends_at else None,
                "allDay": event.all_day}

    def remove(self, principal: LocalPrincipal, calendar_account_id: str) -> None:
        import psycopg
        with psycopg.connect(self._database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, principal)
                cursor.execute(
                    """DELETE FROM vault_private.vault_calendar_accounts
                       WHERE calendar_account_id=%s AND account_id=%s AND workspace_id=%s""",
                    (calendar_account_id,principal.user_id,principal.workspace_id),
                )
                if cursor.rowcount != 1:
                    raise LookupError("Calendar account was not found.")

    def _credential_record(self, principal: LocalPrincipal, calendar_account_id: str) -> dict[str, Any] | None:
        import psycopg
        with psycopg.connect(self._database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, principal)
                cursor.execute(
                    """SELECT provider_type,nonce,ciphertext,status,sync_metadata
                       FROM vault_private.vault_calendar_accounts
                       WHERE calendar_account_id=%s AND account_id=%s AND workspace_id=%s""",
                    (calendar_account_id,principal.user_id,principal.workspace_id),
                )
                row = cursor.fetchone()
        if row is None or row[3] != "active":
            return None
        plaintext = AESGCM(self._master_key.load_or_create()).decrypt(
            bytes(row[1]), bytes(row[2]), self._aad(principal, calendar_account_id),
        )
        credentials = json.loads(plaintext)
        metadata = row[4] if isinstance(row[4], dict) else {}
        source_payload = {
            "provider_credential_id": f"calendar:{calendar_account_id}",
            "providerKind": "calendar", "providerKey": row[0],
            "linkedAccountId": calendar_account_id, "status": "active",
            "credentials": credentials, **metadata,
        }
        return {
            "accountId": principal.user_id, "workspaceId": principal.workspace_id,
            "domain": "provider_credentials", "sourceId": f"calendar:{calendar_account_id}",
            "sourcePayload": source_payload,
        }

    def _update_metadata(self, principal: LocalPrincipal, calendar_account_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        metadata = {key: value for key, value in payload.items() if key.startswith("calendarSync") or key.startswith("lastCalendarSync")}
        import psycopg
        with psycopg.connect(self._database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                self._require_scope(cursor, principal)
                cursor.execute(
                    """UPDATE vault_private.vault_calendar_accounts SET sync_metadata=%s,updated_at=now()
                       WHERE calendar_account_id=%s AND account_id=%s AND workspace_id=%s""",
                    (Jsonb(metadata),calendar_account_id,principal.user_id,principal.workspace_id),
                )
        return self._credential_record(principal, calendar_account_id)

    @staticmethod
    def _require_scope(cursor, principal: LocalPrincipal) -> None:
        PersonalDataRepository._scope(cursor, account_id=principal.user_id, workspace_id=principal.workspace_id)

    @staticmethod
    def _aad(principal: LocalPrincipal, account_id: str) -> bytes:
        return f"{principal.user_id}:{principal.workspace_id}:{account_id}:calendar".encode()


class _ScopedCalendarStore:
    def __init__(self, *, runtime: LocalCalendarRuntime, principal: LocalPrincipal) -> None:
        self._runtime, self._principal = runtime, principal

    def list_provider_credentials_for_scope(self, *, account_id: str, workspace_id: str,
                                            provider_kind: str, linked_account_id: str | None = None,
                                            installed_skill_id: str | None = None, limit: int = 5):
        if account_id != self._principal.user_id or workspace_id != self._principal.workspace_id or provider_kind != "calendar":
            raise PermissionError("Calendar scope was not authorized.")
        ids = [linked_account_id] if linked_account_id else [item["calendarAccountId"] for item in self._runtime.accounts(self._principal)]
        return [record for item_id in ids[:limit] if item_id and (record := self._runtime._credential_record(self._principal, item_id))]

    def import_items(self, items, *, account_id=None, workspace_id=None):
        if account_id != self._principal.user_id or workspace_id != self._principal.workspace_id:
            raise PermissionError("Calendar scope was not authorized.")
        return self._runtime._records.import_items(tuple(items), account_id=account_id, workspace_id=workspace_id)

    def update_provider_private_record(self, *, account_id: str, workspace_id: str, domain: str,
                                       source_id: str, source_payload: dict[str, Any]):
        if account_id != self._principal.user_id or workspace_id != self._principal.workspace_id or domain != "provider_credentials":
            raise PermissionError("Calendar scope was not authorized.")
        return self._runtime._update_metadata(self._principal, source_id.removeprefix("calendar:"), source_payload)


def _credential_payload(provider_type: str, credentials: dict[str, Any]) -> dict[str, Any]:
    if provider_type == "ics":
        feed_url = str(credentials.get("feedUrl") or "").strip()
        if not feed_url:
            raise ValueError("Calendar feedUrl is required.")
        return {"providerType": "ics", "providerKey": "ics", "feedUrl": feed_url}
    username, password = str(credentials.get("username") or "").strip(), str(credentials.get("password") or "")
    if not username or not password:
        raise ValueError("CalDAV username and password are required.")
    return {"providerType": "caldav", "providerKey": "caldav", "calendarUrl": str(credentials.get("calendarUrl") or "").strip() or None,
            "username": username, "password": password}


def _public_account(row) -> dict[str, Any]:
    public = row[3] if isinstance(row[3], dict) else {}
    metadata = row[5] if isinstance(row[5], dict) else {}
    return {"calendarAccountId": row[0], "providerType": row[1], "displayName": row[2],
            "configuration": public, "status": row[4], "sync": metadata,
            "updatedAt": row[6].isoformat()}


def _iso_datetime(value: Any, field: str):
    from datetime import datetime
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        raise ValueError(f"Calendar {field} is required.")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError(f"Calendar {field} must include a timezone.")
    return parsed
