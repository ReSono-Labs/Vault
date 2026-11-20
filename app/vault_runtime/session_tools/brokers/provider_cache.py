from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Mapping

from app.vault_runtime.session_tools.errors import VaultSessionToolRuntimeError
from app.vault_runtime.session_tools.primitives import (
    bounded_int,
    list_items_result,
    optional_private_argument_text,
    parse_support_iso,
    payload_bool,
    payload_text,
    private_argument_text,
    read_item_result,
    safe_int,
    source_payload,
)


CALENDAR_CACHE_TOOLS = frozenset(
    {"calendar_check", "calendar_read_day", "calendar_search", "calendar_read_event"}
)


def provider_cache_query(*, tool_name: str, arguments: Mapping[str, Any]) -> str:
    if tool_name in {"email_search", "agent_mail_search", "calendar_search", "email_contact_lookup"}:
        return private_argument_text(arguments, "query", required=True)
    if tool_name in {"email_read", "agent_mail_read"}:
        return private_argument_text(arguments, "messageId", required=True)
    if tool_name == "calendar_read_event":
        return private_argument_text(arguments, "eventId", required=True)
    if tool_name == "calendar_read_day":
        return private_argument_text(arguments, "targetDate", required=False)
    return ""


def provider_cache_search_limit(*, tool_name: str, arguments: Mapping[str, Any]) -> int:
    if tool_name in {"email_read", "agent_mail_read", "calendar_read_event"}:
        return 25
    if tool_name == "email_contact_lookup":
        result_limit = bounded_int(arguments.get("limit"), default=10, minimum=1, maximum=25)
        return min(100, max(result_limit * 5, 25))
    maximum = 50 if tool_name.startswith("calendar_") else 100
    default = 10 if tool_name.startswith("calendar_") else 25
    return bounded_int(arguments.get("limit"), default=default, minimum=1, maximum=maximum)


def calendar_refresh_limit(*, tool_name: str, arguments: Mapping[str, Any]) -> int:
    if tool_name == "calendar_read_event":
        return 100
    return max(provider_cache_search_limit(tool_name=tool_name, arguments=arguments), 50)


def calendar_refresh_window(
    *,
    tool_name: str,
    arguments: Mapping[str, Any],
) -> tuple[datetime | None, datetime | None]:
    if tool_name == "calendar_read_day":
        target_date = optional_private_argument_text(arguments, "targetDate")
        if target_date:
            try:
                day = datetime.fromisoformat(target_date).date()
            except ValueError:
                return None, None
            return (
                datetime.combine(day, datetime.min.time(), tzinfo=UTC),
                datetime.combine(day, datetime.max.time(), tzinfo=UTC),
            )
    starts_at_from = parse_support_iso(optional_private_argument_text(arguments, "startsAtFrom"))
    starts_at_to = parse_support_iso(optional_private_argument_text(arguments, "startsAtTo"))
    return starts_at_from, starts_at_to


def provider_live_refresh_requested(arguments: Mapping[str, Any]) -> bool:
    freshness = optional_private_argument_text(arguments, "freshness")
    if freshness is None:
        return False
    normalized = freshness.strip().lower()
    if normalized == "live":
        return True
    if normalized == "cache":
        return False
    raise VaultSessionToolRuntimeError(
        400,
        "invalid_private_tool_argument",
        "Browser Voice provider tools require freshness to be cache or live.",
        details={"fieldPath": "$.arguments.freshness"},
    )


def provider_sync_freshness(*, kind: str, result: Mapping[str, Any]) -> dict[str, Any]:
    processed_count = safe_int(result.get("processedCount"))
    synced_count = safe_int(result.get("syncedCredentialCount"))
    failed_count = safe_int(result.get("failedCount"))
    items = result.get("items") if isinstance(result.get("items"), list) else []
    folders: list[str] = []
    results_may_be_partial = False
    codes: list[str] = []
    statuses: list[str] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        statuses.append(str(item.get("status") or ""))
        for folder in item.get("foldersSearched") or []:
            text = str(folder).strip()
            if text and text not in folders:
                folders.append(text)
        results_may_be_partial = results_may_be_partial or bool(item.get("resultsMayBePartial"))
        code = str(item.get("code") or "").strip()
        if code and code not in codes:
            codes.append(code)
    if synced_count > 0:
        source = "live"
    elif processed_count == 0:
        source = "live_unavailable"
    elif failed_count > 0:
        source = "live_failed"
    else:
        source = "live_empty"
    return {
        "source": source,
        "kind": kind,
        "processedCredentialCount": processed_count,
        "syncedCredentialCount": synced_count,
        "failedCredentialCount": failed_count,
        "foldersSearched": folders,
        "resultsMayBePartial": results_may_be_partial,
        "statuses": [status for status in dict.fromkeys(statuses) if status],
        "errorCodes": codes,
    }


def provider_cache_result(
    *,
    tool_name: str,
    arguments: Mapping[str, Any],
    items: list[dict[str, Any]],
    live_refresh_started_at: datetime | None = None,
    live_refresh_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if live_refresh_started_at is not None:
        items = _filter_records_cached_at_or_after(items=items, cached_at_or_after=live_refresh_started_at)
    freshness = live_refresh_metadata or {"source": "vault_cache", "resultsMayBePartial": True}
    if tool_name in CALENDAR_CACHE_TOOLS:
        normalized = _calendar_items(items, linked_account_id=optional_private_argument_text(arguments, "linkedAccountId"))
        if tool_name == "calendar_search":
            normalized = _filter_calendar_query(
                normalized,
                private_argument_text(arguments, "query", required=True),
            )
        normalized = _filter_calendar_window(
            normalized,
            starts_at_from=optional_private_argument_text(arguments, "startsAtFrom"),
            starts_at_to=optional_private_argument_text(arguments, "startsAtTo"),
        )
        if tool_name == "calendar_read_day":
            normalized = _filter_calendar_day(
                normalized,
                optional_private_argument_text(arguments, "targetDate"),
            )
        if tool_name == "calendar_read_event":
            return _with_provider_freshness(
                read_item_result(
                    items=normalized,
                    lookup=private_argument_text(arguments, "eventId", required=True),
                    id_key="eventId",
                ),
                freshness=freshness,
            )
        normalized = _limit_calendar_items(
            _sort_calendar_items(normalized),
            limit=provider_cache_search_limit(tool_name=tool_name, arguments=arguments),
        )
        return _with_provider_freshness(list_items_result(normalized), freshness=freshness)
    raise AssertionError(f"Unhandled provider cache tool: {tool_name}")


def _filter_records_cached_at_or_after(
    *,
    items: list[dict[str, Any]],
    cached_at_or_after: datetime,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    threshold = cached_at_or_after.astimezone(UTC) - timedelta(seconds=1)
    for item in items:
        payload = source_payload(item)
        cached_at = parse_support_iso(payload_text(payload, "cached_at", "cachedAt"))
        if cached_at is not None and cached_at >= threshold:
            filtered.append(item)
    return filtered


def _with_provider_freshness(result: dict[str, Any], *, freshness: Mapping[str, Any]) -> dict[str, Any]:
    updated = dict(result)
    updated["freshness"] = dict(freshness)
    source = str(freshness.get("source") or updated.get("source") or "vault_cache")
    updated["source"] = source
    if source in {"live_unavailable", "live_failed", "live_empty"}:
        updated["status"] = source
        updated["message"] = _provider_freshness_message(freshness)
    return updated


def _provider_freshness_message(freshness: Mapping[str, Any]) -> str:
    source = str(freshness.get("source") or "")
    kind = str(freshness.get("kind") or "provider")
    if source == "live_unavailable":
        return f"No Vault {kind} credentials are available for live provider refresh."
    if source == "live_failed":
        return f"Vault {kind} live provider refresh failed."
    if source == "live_empty":
        return f"Vault {kind} live provider refresh completed without importing fresh records."
    return "Vault provider refresh completed."


def _calendar_items(items: list[dict[str, Any]], *, linked_account_id: str | None) -> list[dict[str, Any]]:
    normalized = []
    for item in items:
        payload = source_payload(item)
        item_linked_account_id = payload_text(payload, "linked_account_id", "linkedAccountId")
        if linked_account_id and item_linked_account_id != linked_account_id:
            continue
        normalized.append(
            {
                "eventId": payload_text(payload, "provider_event_id", "providerEventId") or item.get("sourceId"),
                "linkedAccountId": item_linked_account_id,
                "calendarLabel": payload_text(payload, "calendar_label", "calendarLabel"),
                "title": payload_text(payload, "title") or "",
                "description": payload_text(payload, "description"),
                "location": payload_text(payload, "location"),
                "startsAt": payload_text(payload, "starts_at", "startsAt"),
                "endsAt": payload_text(payload, "ends_at", "endsAt"),
                "allDay": payload_bool(payload, "all_day", "allDay") is True,
                "organizer": payload_text(payload, "organizer"),
                "cachedAt": payload_text(payload, "cached_at", "cachedAt"),
                "sourceId": item.get("sourceId"),
            }
        )
    return normalized


def _filter_calendar_query(items: list[dict[str, Any]], query: str | None) -> list[dict[str, Any]]:
    normalized_query = (query or "").strip().lower()
    if not normalized_query:
        return items
    return [
        item
        for item in items
        if normalized_query
        in " ".join(
            str(item.get(key) or "")
            for key in ("title", "description", "location", "organizer", "calendarLabel")
        ).lower()
    ]


def _filter_calendar_day(items: list[dict[str, Any]], target_date: str | None) -> list[dict[str, Any]]:
    if not target_date:
        return items
    try:
        day = datetime.fromisoformat(target_date).date()
    except ValueError:
        return []
    starts_at_from = datetime.combine(day, datetime.min.time(), tzinfo=UTC)
    starts_at_to = datetime.combine(day, datetime.max.time(), tzinfo=UTC)
    return [
        item
        for item in items
        if _calendar_item_in_window(item, starts_at_from=starts_at_from, starts_at_to=starts_at_to)
    ]


def _filter_calendar_window(
    items: list[dict[str, Any]],
    *,
    starts_at_from: str | None,
    starts_at_to: str | None,
) -> list[dict[str, Any]]:
    lower = parse_support_iso(starts_at_from)
    upper = parse_support_iso(starts_at_to)
    if lower is None and upper is None:
        return items
    return [
        item
        for item in items
        if _calendar_item_in_window(item, starts_at_from=lower, starts_at_to=upper)
    ]


def _calendar_item_in_window(
    item: Mapping[str, Any],
    *,
    starts_at_from: datetime | None,
    starts_at_to: datetime | None,
) -> bool:
    starts_at = parse_support_iso(str(item.get("startsAt") or ""))
    if starts_at is None:
        return False
    if starts_at_from is not None and starts_at < starts_at_from:
        return False
    if starts_at_to is not None and starts_at > starts_at_to:
        return False
    return True


def _sort_calendar_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=_calendar_item_sort_key)


def _calendar_item_sort_key(item: Mapping[str, Any]) -> tuple[datetime, str]:
    starts_at = parse_support_iso(str(item.get("startsAt") or ""))
    return starts_at or datetime.max.replace(tzinfo=UTC), str(item.get("eventId") or item.get("sourceId") or "")


def _limit_calendar_items(items: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    return items[: max(1, min(limit, 50))]
