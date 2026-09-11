from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from app.modules.integrations.calendar_ics_provider import IcsCalendarCredentials, IcsCalendarProviderClient
from app.modules.integrations.caldav_calendar_provider import (
    CaldavCalendarCreateRequest,
    CaldavCalendarCredentials,
    CaldavCalendarProviderClient,
)


_CALDAV_PROVIDER_TYPES = {"caldav", "caldav-calendar", "caldav_calendar", "calendar_caldav"}
_ICS_PROVIDER_TYPES = {"ics", "ics-feed", "ics_feed", "calendar_ics"}


@dataclass(frozen=True, slots=True)
class VaultCalendarCredentials:
    provider_type: str
    provider_key: str | None
    calendar_url: str | None
    feed_url: str | None
    username: str | None
    password: str | None


@dataclass(frozen=True, slots=True)
class VaultCalendarEvent:
    provider_event_id: str
    title: str
    starts_at: datetime
    ends_at: datetime | None
    all_day: bool
    description: str | None
    location: str | None
    organizer: str | None
    calendar_label: str | None


class VaultCalendarProviderClient:
    def __init__(
        self,
        *,
        ics_provider: IcsCalendarProviderClient | None = None,
        caldav_provider: CaldavCalendarProviderClient | None = None,
    ) -> None:
        self._ics = ics_provider or IcsCalendarProviderClient()
        self._caldav = caldav_provider or CaldavCalendarProviderClient()

    def fetch_events(
        self,
        *,
        credentials: VaultCalendarCredentials,
        starts_at_from: datetime | None = None,
        starts_at_to: datetime | None = None,
        limit: int = 100,
    ) -> list[VaultCalendarEvent]:
        if credentials.provider_type in _ICS_PROVIDER_TYPES:
            feed_url = _required_text(credentials.feed_url or credentials.calendar_url, field="feedUrl")
            return [
                _event_from_provider_event(event)
                for event in self._ics.fetch_events(
                    credentials=IcsCalendarCredentials(feed_url=feed_url),
                    starts_at_from=starts_at_from,
                    starts_at_to=starts_at_to,
                    limit=limit,
                )
            ]
        if credentials.provider_type in _CALDAV_PROVIDER_TYPES:
            return [
                _event_from_provider_event(event)
                for event in self._caldav.fetch_events(
                    credentials=_caldav_credentials(credentials),
                    starts_at_from=starts_at_from,
                    starts_at_to=starts_at_to,
                    limit=limit,
                )
            ]
        raise ValueError("vault_calendar_provider_type_unsupported")

    def create_event(
        self,
        *,
        credentials: VaultCalendarCredentials,
        title: str,
        starts_at: datetime,
        ends_at: datetime | None,
        all_day: bool,
        description: str | None = None,
        location: str | None = None,
        calendar_label: str | None = None,
    ) -> VaultCalendarEvent:
        if credentials.provider_type not in _CALDAV_PROVIDER_TYPES:
            raise ValueError("vault_calendar_provider_read_only")
        created = self._caldav.create_event(
            credentials=_caldav_credentials(credentials),
            request=CaldavCalendarCreateRequest(
                title=title,
                starts_at=starts_at,
                ends_at=ends_at,
                all_day=all_day,
                description=description,
                location=location,
            ),
            calendar_label=calendar_label,
        )
        return _event_from_provider_event(created)

    def update_event(
        self, *, credentials: VaultCalendarCredentials, provider_event_id: str,
        title: str, starts_at: datetime, ends_at: datetime | None, all_day: bool,
        description: str | None = None, location: str | None = None,
        calendar_label: str | None = None,
    ) -> VaultCalendarEvent:
        if credentials.provider_type not in _CALDAV_PROVIDER_TYPES:
            raise ValueError("vault_calendar_provider_read_only")
        updated = self._caldav.update_event(
            credentials=_caldav_credentials(credentials), provider_event_id=provider_event_id,
            request=CaldavCalendarCreateRequest(title=title, starts_at=starts_at, ends_at=ends_at,
                all_day=all_day, description=description, location=location),
            calendar_label=calendar_label,
        )
        return _event_from_provider_event(updated)

    def delete_event(self, *, credentials: VaultCalendarCredentials, provider_event_id: str) -> None:
        if credentials.provider_type not in _CALDAV_PROVIDER_TYPES:
            raise ValueError("vault_calendar_provider_read_only")
        self._caldav.delete_event(credentials=_caldav_credentials(credentials), provider_event_id=provider_event_id)


def credentials_from_payload(payload: Mapping[str, Any]) -> VaultCalendarCredentials:
    credentials = payload.get("credentials") if isinstance(payload.get("credentials"), Mapping) else payload
    provider_type = _provider_type(credentials=credentials, payload=payload)
    calendar_url = _optional_text(credentials.get("calendarUrl") or credentials.get("calendar_url"))
    feed_url = _optional_text(credentials.get("feedUrl") or credentials.get("feed_url"))
    username = _optional_text(credentials.get("username"))
    password = _optional_text(credentials.get("password"))
    if provider_type in _ICS_PROVIDER_TYPES:
        _required_text(feed_url or calendar_url, field="feedUrl")
    if provider_type in _CALDAV_PROVIDER_TYPES:
        _required_text(calendar_url, field="calendarUrl")
        _required_text(username, field="username")
        _required_text(password, field="password")
    return VaultCalendarCredentials(
        provider_type=provider_type,
        provider_key=_optional_text(credentials.get("providerKey") or payload.get("providerKey") or payload.get("provider_key")),
        calendar_url=calendar_url,
        feed_url=feed_url,
        username=username,
        password=password,
    )


def credentials_support_event_create(payload: Mapping[str, Any]) -> bool:
    try:
        credentials = credentials_from_payload(payload)
    except ValueError:
        return False
    return credentials.provider_type in _CALDAV_PROVIDER_TYPES


def _provider_type(*, credentials: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
    explicit = _optional_text(
        credentials.get("providerType")
        or credentials.get("provider_type")
        or credentials.get("configurationRef")
        or credentials.get("configuration_ref")
        or payload.get("providerType")
        or payload.get("provider_type")
        or payload.get("configurationRef")
        or payload.get("configuration_ref")
    )
    if explicit:
        normalized = explicit.lower().replace("_", "-")
        if normalized in _CALDAV_PROVIDER_TYPES or normalized in _ICS_PROVIDER_TYPES:
            return normalized
    if _optional_text(credentials.get("feedUrl") or credentials.get("feed_url")):
        return "ics-feed"
    if _optional_text(credentials.get("calendarUrl") or credentials.get("calendar_url")) and _optional_text(credentials.get("password")):
        return "caldav-calendar"
    provider_key = _optional_text(credentials.get("providerKey") or payload.get("providerKey") or payload.get("provider_key"))
    if provider_key:
        normalized_key = provider_key.lower().replace("_", "-")
        if normalized_key in _CALDAV_PROVIDER_TYPES or normalized_key in _ICS_PROVIDER_TYPES:
            return normalized_key
    raise ValueError("vault_calendar_provider_type_required")


def _caldav_credentials(credentials: VaultCalendarCredentials) -> CaldavCalendarCredentials:
    return CaldavCalendarCredentials(
        calendar_url=_required_text(credentials.calendar_url, field="calendarUrl"),
        username=_required_text(credentials.username, field="username"),
        password=_required_text(credentials.password, field="password"),
    )


def _event_from_provider_event(event: Any) -> VaultCalendarEvent:
    return VaultCalendarEvent(
        provider_event_id=_required_text(getattr(event, "provider_event_id", None), field="providerEventId"),
        title=_required_text(getattr(event, "title", None), field="title"),
        starts_at=getattr(event, "starts_at"),
        ends_at=getattr(event, "ends_at", None),
        all_day=bool(getattr(event, "all_day", False)),
        description=_optional_text(getattr(event, "description", None)),
        location=_optional_text(getattr(event, "location", None)),
        organizer=_optional_text(getattr(event, "organizer", None)),
        calendar_label=_optional_text(getattr(event, "calendar_label", None)),
    )


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
