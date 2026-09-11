from __future__ import annotations

import json
from typing import Any, Mapping, Protocol

from app.vault_runtime.session_tools.primitives import payload_text
from app.vault_runtime.types import VaultMigrationExportItem


class PrivateRecordImportStore(Protocol):
    def import_items(
        self,
        items: tuple[VaultMigrationExportItem, ...],
        *,
        account_id: str,
        workspace_id: str,
    ) -> int:
        ...


def import_private_record(
    *,
    store: PrivateRecordImportStore,
    account_id: str,
    workspace_id: str,
    domain: str,
    source_table: str,
    source_id: str,
    source_payload: dict[str, Any],
    content_text: str | None,
) -> None:
    store.import_items(
        (
            VaultMigrationExportItem(
                domain=domain,
                source_id=source_id,
                payload={
                    "accountId": account_id,
                    "workspaceId": workspace_id,
                    "sourceTable": source_table,
                    "sourceId": source_id,
                    "sourcePayload": source_payload,
                    "personalFields": ["*"],
                    "cloudRetainedFields": [],
                    "retentionClass": "vault_migratable_personal",
                    "rowScope": "account_workspace",
                    "splitRequired": False,
                    "contentText": content_text,
                },
            ),
        ),
        account_id=account_id,
        workspace_id=workspace_id,
    )


def upsert_private_record(
    *,
    store: PrivateRecordImportStore,
    account_id: str,
    workspace_id: str,
    source_table: str,
    source_id: str,
    source_payload: dict[str, Any],
    content_text: str | None,
) -> None:
    import_private_record(
        store=store,
        account_id=account_id,
        workspace_id=workspace_id,
        domain=source_table,
        source_table=source_table,
        source_id=source_id,
        source_payload=source_payload,
        content_text=content_text,
    )


def source_table_primary_key(source_table: str) -> str:
    explicit = {
        "contacts_pending_actions": "contacts_pending_action_id",
    }
    if source_table in explicit:
        return explicit[source_table]
    if source_table.endswith("ies"):
        return f"{source_table[:-3]}y_id"
    if source_table.endswith("s"):
        return f"{source_table[:-1]}_id"
    return f"{source_table}_id"


def generic_record_content(payload: Mapping[str, Any]) -> str | None:
    values: list[str] = []
    for key in (
        "title",
        "name",
        "subject",
        "summary",
        "summary_text",
        "body",
        "body_text",
        "description",
        "notes",
        "content",
        "contentMarkdown",
        "text",
        "query",
    ):
        text = payload_text(payload, key)
        if text:
            values.append(text)
    return "\n".join(values) if values else None


def private_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): private_json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [private_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [private_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def request_content_text(*, tool_name: str, arguments: Mapping[str, Any]) -> str:
    values = [tool_name]
    values.extend(_flatten_private_values(arguments))
    return "\n".join(value for value in values if value)


def generic_private_record_item(*, source_table: str, record: Mapping[str, Any]) -> dict[str, Any]:
    payload = record_source_payload(record)
    source_id = str(record.get("sourceId") or payload.get(source_table_primary_key(source_table)) or "").strip()
    return {
        "domain": source_table,
        "sourceTable": source_table,
        "sourceId": source_id or None,
        "contentText": payload_text(record, "contentText") or generic_record_content(payload),
        "sourcePayload": payload,
        "updatedAt": payload_text(record, "updatedAt"),
    }


def record_haystack(record: Mapping[str, Any]) -> str:
    try:
        payload_text_value = json.dumps(record.get("sourcePayload") or {}, sort_keys=True, default=str)
    except (TypeError, ValueError):
        payload_text_value = str(record.get("sourcePayload") or "")
    return f"{record.get('contentText') or ''}\n{payload_text_value}".lower()


def record_source_payload(record: Mapping[str, Any]) -> Mapping[str, Any]:
    payload = record.get("sourcePayload")
    return payload if isinstance(payload, Mapping) else {}


def _flatten_private_values(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        values: list[str] = []
        for item in value.values():
            values.extend(_flatten_private_values(item))
        return values
    if isinstance(value, (list, tuple)):
        values: list[str] = []
        for item in value:
            values.extend(_flatten_private_values(item))
        return values
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []
