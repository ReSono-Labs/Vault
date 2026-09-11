from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Protocol
from uuid import uuid4

from app.vault_runtime.session_tools.errors import VaultSessionToolRuntimeError
from app.vault_runtime.session_tools.primitives import (
    argument_bool,
    bounded_int,
    normalize_search_text,
    now_iso,
    optional_arg_text,
    payload_mapping,
    payload_text,
    required_arg_text,
    source_payload,
)
from app.vault_runtime.session_tools.records import PrivateRecordImportStore, record_haystack, upsert_private_record
from app.vault_runtime.types import VaultMigrationExportItem


CONTACT_TOOL_NAMES = frozenset(
    {
        "contacts_search",
        "contacts_prepare_save",
        "contacts_confirm_pending",
        "contacts_prepare_use",
        "contacts_confirm_use",
    }
)
CONTACT_SAVE_ACTIONS = frozenset({"create", "update", "delete"})
CONTACT_PAYLOAD_FIELDS = (
    "first_name",
    "last_name",
    "business_name",
    "address",
    "phone_number",
    "email_address",
    "website",
    "notes",
)
CONTACT_USE_FIELDS = frozenset({"email_address", "phone_number", "address", "website", "notes"})
CONTACT_PENDING_TTL_MINUTES = 15
CONTACTS_SEARCH_CONTRACT_QUERY_BEFORE_LIMIT = "contacts.search.query_before_limit.v2"


class ContactsStore(PrivateRecordImportStore, Protocol):
    def get_private_record(
        self,
        *,
        account_id: str,
        workspace_id: str,
        source_table: str,
        source_id: str,
    ) -> dict[str, Any] | None:
        ...

    def claim_private_record_status(
        self,
        *,
        account_id: str,
        workspace_id: str,
        source_table: str,
        source_id: str,
        expected_status: str,
        claimed_status: str,
    ) -> dict[str, Any] | None:
        ...

    def list_private_records(
        self,
        *,
        account_id: str,
        workspace_id: str,
        source_table: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        ...

    def search_private_records(
        self,
        *,
        account_id: str,
        workspace_id: str,
        source_table: str,
        query: str,
        limit: int,
        exclude_deleted: bool = False,
    ) -> list[dict[str, Any]]:
        ...

    def import_items(
        self,
        items: tuple[VaultMigrationExportItem, ...],
        *,
        account_id: str,
        workspace_id: str,
    ) -> int:
        ...


def contacts_tool_result(
    *,
    store: ContactsStore,
    account_id: str,
    workspace_id: str,
    voice_realtime_session_id: str,
    tool_call_id: str,
    tool_name: str,
    arguments: Mapping[str, Any],
    search_contract: str | None = CONTACTS_SEARCH_CONTRACT_QUERY_BEFORE_LIMIT,
) -> dict[str, Any]:
    if tool_name == "contacts_search":
        return _contacts_search_result(
            store=store,
            account_id=account_id,
            workspace_id=workspace_id,
            arguments=arguments,
            search_contract=search_contract,
        )
    if tool_name == "contacts_prepare_save":
        return _contacts_prepare_save_result(
            store=store,
            account_id=account_id,
            workspace_id=workspace_id,
            voice_realtime_session_id=voice_realtime_session_id,
            tool_call_id=tool_call_id,
            arguments=arguments,
        )
    if tool_name == "contacts_confirm_pending":
        return _contacts_confirm_pending_result(
            store=store,
            account_id=account_id,
            workspace_id=workspace_id,
            arguments=arguments,
        )
    if tool_name == "contacts_prepare_use":
        return _contacts_prepare_use_result(
            store=store,
            account_id=account_id,
            workspace_id=workspace_id,
            voice_realtime_session_id=voice_realtime_session_id,
            tool_call_id=tool_call_id,
            arguments=arguments,
        )
    if tool_name == "contacts_confirm_use":
        return _contacts_confirm_use_result(
            store=store,
            account_id=account_id,
            workspace_id=workspace_id,
            arguments=arguments,
        )
    raise AssertionError(f"Unhandled contacts tool: {tool_name}")


def _contacts_search_result(
    *,
    store: ContactsStore,
    account_id: str,
    workspace_id: str,
    arguments: Mapping[str, Any],
    search_contract: str | None,
) -> dict[str, Any]:
    query = optional_arg_text(arguments, "query", "searchText") or ""
    if not query.strip():
        raise VaultSessionToolRuntimeError(
            400,
            "contacts_search_query_required",
            "Contacts search requires a non-empty query.",
        )
    limit = bounded_int(arguments.get("limit"), default=5, minimum=1, maximum=20)
    normalized_query = query.strip().lower()
    items: list[dict[str, Any]] = []
    if search_contract not in {None, CONTACTS_SEARCH_CONTRACT_QUERY_BEFORE_LIMIT}:
        raise VaultSessionToolRuntimeError(
            409,
            "contacts_search_contract_unsupported",
            "Contacts search contract is not supported by this Vault runtime.",
        )
    if search_contract == CONTACTS_SEARCH_CONTRACT_QUERY_BEFORE_LIMIT:
        search_private_records = getattr(store, "search_private_records", None)
        if not callable(search_private_records):
            raise VaultSessionToolRuntimeError(
                409,
                "contacts_search_store_contract_missing",
                "Corrected Contacts search requires a query-before-limit private-record store.",
            )
        records = search_private_records(
            account_id=account_id,
            workspace_id=workspace_id,
            source_table="contacts_entries",
            query=query,
            limit=limit,
            exclude_deleted=True,
        )
    else:
        # Absence is the immutable Contacts 1.0.0 legacy behavior marker.
        records = _contact_records(
            store=store,
            account_id=account_id,
            workspace_id=workspace_id,
            limit=max(limit * 3, 20),
        )
    for record in records:
        payload = source_payload(record)
        if _contact_is_deleted(payload):
            continue
        haystack = (
            _contact_search_haystack(record)
            if search_contract == CONTACTS_SEARCH_CONTRACT_QUERY_BEFORE_LIMIT
            else record_haystack(record)
        )
        if normalized_query and normalized_query not in haystack:
            continue
        item = _contact_search_item(record)
        items.append(item)
        if len(items) >= limit:
            break
    return {
        "status": "ok",
        "query": query,
        "matchCount": len(items),
        "ambiguous": len(items) > 1,
        "contacts": items,
        "message": (
            "Multiple contacts match. Ask the user to choose one before using a contact field."
            if len(items) > 1
            else "No matching contacts found." if not items else "One matching contact found. Confirm before use."
        ),
    }


def _contacts_prepare_save_result(
    *,
    store: ContactsStore,
    account_id: str,
    workspace_id: str,
    voice_realtime_session_id: str,
    tool_call_id: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    action_type = _contact_action_type(required_arg_text(arguments, "actionType", "action_type"))
    contact_id = optional_arg_text(arguments, "contactId", "contact_id")
    existing_record = None
    existing_payload: Mapping[str, Any] | None = None
    if action_type in {"update", "delete"}:
        existing_record = _require_contact_record(
            store=store,
            account_id=account_id,
            workspace_id=workspace_id,
            contact_id=contact_id,
        )
        existing_payload = source_payload(existing_record)

    cleaned_payload = _contact_payload_from_arguments(arguments)
    if action_type == "update" and existing_payload is not None:
        merged_payload = _contact_payload_from_source(existing_payload)
        for key, value in cleaned_payload.items():
            if value is not None:
                merged_payload[key] = value
        cleaned_payload = merged_payload
    if action_type in {"create", "update"} and not any(cleaned_payload.values()):
        raise VaultSessionToolRuntimeError(400, "contact_field_required", "At least one contact field is required.")
    if action_type == "delete" and existing_payload is not None:
        cleaned_payload = _contact_payload_from_source(existing_payload)

    pending_id = f"contacts-pending-{uuid4()}"
    now = now_iso()
    expires_at = (datetime.now(UTC) + timedelta(minutes=CONTACT_PENDING_TTL_MINUTES)).isoformat()
    summary = _contact_save_summary(action_type=action_type, payload=cleaned_payload, existing=existing_payload)
    pending_payload = {
        "contacts_pending_action_id": pending_id,
        "installed_skill_id": optional_arg_text(arguments, "installedSkillId", "installed_skill_id"),
        "account_id": account_id,
        "workspace_id": workspace_id,
        "contacts_entry_id": _contact_id(existing_payload, existing_record) if existing_record is not None else contact_id,
        "action_type": action_type,
        "status": "pending",
        "payload_jsonb": {
            "contact": cleaned_payload,
            "sourceType": optional_arg_text(arguments, "sourceType", "source_type"),
            "sourceFileKey": optional_arg_text(arguments, "sourceFileKey", "source_file_key"),
            "sourceSessionId": voice_realtime_session_id,
        },
        "confirmation_summary": summary,
        "expires_at": expires_at,
        "created_via_session_id": voice_realtime_session_id,
        "created_at": now,
        "updated_at": now,
        "tool_call_id": tool_call_id,
    }
    upsert_private_record(
        store=store,
        account_id=account_id,
        workspace_id=workspace_id,
        source_table="contacts_pending_actions",
        source_id=pending_id,
        source_payload=pending_payload,
        content_text=_contact_pending_content_text(pending_payload),
    )
    return _contact_pending_response(
        pending_payload,
        message="Ask the user to confirm before saving this contact change.",
    )


def _contacts_confirm_pending_result(
    *,
    store: ContactsStore,
    account_id: str,
    workspace_id: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    pending_id = required_arg_text(arguments, "pendingActionId", "pending_action_id")
    approve = argument_bool(arguments, "approve", default=True)
    pending_record = _require_contact_pending_record(
        store=store,
        account_id=account_id,
        workspace_id=workspace_id,
        pending_id=pending_id,
    )
    pending_payload = dict(source_payload(pending_record))
    action_type = payload_text(pending_payload, "action_type", "actionType")
    if action_type not in CONTACT_SAVE_ACTIONS:
        raise VaultSessionToolRuntimeError(400, "contact_pending_wrong_action", "That pending action is not a contact save action.")
    if not approve:
        pending_payload = _claim_contact_pending(
            store=store,
            account_id=account_id,
            workspace_id=workspace_id,
            pending_id=pending_id,
            pending_payload=pending_payload,
            claimed_status="cancelled",
        )
        cancelled = _updated_pending_payload(pending_payload, status="cancelled", timestamp_field="cancelled_at")
        _upsert_contact_pending(store=store, account_id=account_id, workspace_id=workspace_id, pending_payload=cancelled)
        return {"status": "cancelled", "message": "Contact change cancelled.", "pendingActionId": pending_id}

    pending_payload = _claim_contact_pending(
        store=store,
        account_id=account_id,
        workspace_id=workspace_id,
        pending_id=pending_id,
        pending_payload=pending_payload,
        claimed_status="processing",
    )

    payload_jsonb = payload_mapping(pending_payload, "payload_jsonb", "payloadJsonb")
    contact_payload = _clean_contact_payload(
        payload_jsonb.get("contact") if isinstance(payload_jsonb.get("contact"), Mapping) else {}
    )
    contact_record: Mapping[str, Any] | None = None
    contact_source_payload: Mapping[str, Any] | None = None
    contact_id = payload_text(pending_payload, "contacts_entry_id", "contactId")
    if action_type == "create":
        contact_id = contact_id or f"contact-{uuid4()}"
        contact_source_payload = _contact_entry_source_payload(
            contact_id=contact_id,
            account_id=account_id,
            workspace_id=workspace_id,
            payload=contact_payload,
            source_type=payload_text(payload_jsonb, "sourceType", "source_type"),
            source_file_key=payload_text(payload_jsonb, "sourceFileKey", "source_file_key"),
            source_session_id=payload_text(payload_jsonb, "sourceSessionId", "source_session_id"),
        )
    elif action_type == "update":
        contact_record = _require_contact_record(
            store=store,
            account_id=account_id,
            workspace_id=workspace_id,
            contact_id=contact_id,
        )
        existing_payload = source_payload(contact_record)
        merged_payload = _contact_payload_from_source(existing_payload)
        for key, value in contact_payload.items():
            if value is not None:
                merged_payload[key] = value
        contact_source_payload = _contact_entry_source_payload(
            contact_id=_contact_id(existing_payload, contact_record) or contact_id or f"contact-{uuid4()}",
            account_id=account_id,
            workspace_id=workspace_id,
            payload=merged_payload,
            existing_payload=existing_payload,
        )
        contact_id = str(contact_source_payload["contacts_entry_id"])
    elif action_type == "delete":
        contact_record = _require_contact_record(
            store=store,
            account_id=account_id,
            workspace_id=workspace_id,
            contact_id=contact_id,
        )
        existing_payload = source_payload(contact_record)
        merged_payload = _contact_payload_from_source(existing_payload)
        contact_source_payload = _contact_entry_source_payload(
            contact_id=_contact_id(existing_payload, contact_record) or contact_id or f"contact-{uuid4()}",
            account_id=account_id,
            workspace_id=workspace_id,
            payload=merged_payload,
            existing_payload=existing_payload,
            deleted_at=now_iso(),
        )
        contact_id = str(contact_source_payload["contacts_entry_id"])

    assert contact_source_payload is not None
    upsert_private_record(
        store=store,
        account_id=account_id,
        workspace_id=workspace_id,
        source_table="contacts_entries",
        source_id=contact_id or str(contact_source_payload["contacts_entry_id"]),
        source_payload=contact_source_payload,
        content_text=_contact_entry_content_text(contact_source_payload),
    )
    confirmed = _updated_pending_payload(pending_payload, status="confirmed", timestamp_field="confirmed_at")
    confirmed["contacts_entry_id"] = contact_id
    _upsert_contact_pending(store=store, account_id=account_id, workspace_id=workspace_id, pending_payload=confirmed)
    return {
        "status": "confirmed",
        "message": "Contact deleted." if action_type == "delete" else "Contact change saved.",
        "pendingActionId": pending_id,
        "actionType": action_type,
        "contact": None if action_type == "delete" else _contact_full_item(contact_source_payload),
    }


def _contacts_prepare_use_result(
    *,
    store: ContactsStore,
    account_id: str,
    workspace_id: str,
    voice_realtime_session_id: str,
    tool_call_id: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    contact_id = required_arg_text(arguments, "contactId", "contact_id")
    field_name = _contact_use_field(required_arg_text(arguments, "fieldName", "field_name"))
    purpose = optional_arg_text(arguments, "purpose")
    contact_record = _require_contact_record(
        store=store,
        account_id=account_id,
        workspace_id=workspace_id,
        contact_id=contact_id,
    )
    contact_payload = source_payload(contact_record)
    value = _contact_field_text(contact_payload, field_name)
    if not value:
        return {
            "status": "missing_field",
            "contactId": contact_id,
            "fieldName": field_name,
            "message": "That contact does not have the requested field.",
        }
    pending_id = f"contacts-pending-{uuid4()}"
    now = now_iso()
    expires_at = (datetime.now(UTC) + timedelta(minutes=CONTACT_PENDING_TTL_MINUTES)).isoformat()
    summary = (
        f"Use {_contact_field_label(field_name)} for {_contact_display_name(contact_payload)}"
        f"{f' to {purpose.strip()}' if purpose and purpose.strip() else ''}?"
    )
    pending_payload = {
        "contacts_pending_action_id": pending_id,
        "account_id": account_id,
        "workspace_id": workspace_id,
        "contacts_entry_id": contact_id,
        "action_type": "use",
        "status": "pending",
        "field_name": field_name,
        "purpose": purpose,
        "payload_jsonb": {
            "contactId": contact_id,
            "fieldName": field_name,
            "value": value,
            "displayName": _contact_display_name(contact_payload),
            "purpose": purpose,
        },
        "confirmation_summary": summary,
        "expires_at": expires_at,
        "created_via_session_id": voice_realtime_session_id,
        "created_at": now,
        "updated_at": now,
        "tool_call_id": tool_call_id,
    }
    upsert_private_record(
        store=store,
        account_id=account_id,
        workspace_id=workspace_id,
        source_table="contacts_pending_actions",
        source_id=pending_id,
        source_payload=pending_payload,
        content_text=_contact_pending_content_text(pending_payload),
    )
    return {
        **_contact_pending_response(pending_payload, message="Ask the user to confirm before using this contact field."),
        "contact": _contact_search_item(contact_record),
        "fieldName": field_name,
        "maskedValue": _mask_contact_value(field_name, value),
    }


def _contacts_confirm_use_result(
    *,
    store: ContactsStore,
    account_id: str,
    workspace_id: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    pending_id = required_arg_text(arguments, "pendingActionId", "pending_action_id")
    approve = argument_bool(arguments, "approve", default=True)
    pending_record = _require_contact_pending_record(
        store=store,
        account_id=account_id,
        workspace_id=workspace_id,
        pending_id=pending_id,
    )
    pending_payload = dict(source_payload(pending_record))
    if payload_text(pending_payload, "action_type", "actionType") != "use":
        raise VaultSessionToolRuntimeError(400, "contact_pending_wrong_action", "That pending action is not a contact use action.")
    if not approve:
        pending_payload = _claim_contact_pending(
            store=store,
            account_id=account_id,
            workspace_id=workspace_id,
            pending_id=pending_id,
            pending_payload=pending_payload,
            claimed_status="cancelled",
        )
        cancelled = _updated_pending_payload(pending_payload, status="cancelled", timestamp_field="cancelled_at")
        _upsert_contact_pending(store=store, account_id=account_id, workspace_id=workspace_id, pending_payload=cancelled)
        return {"status": "cancelled", "message": "Contact use cancelled.", "pendingActionId": pending_id}
    pending_payload = _claim_contact_pending(
        store=store,
        account_id=account_id,
        workspace_id=workspace_id,
        pending_id=pending_id,
        pending_payload=pending_payload,
        claimed_status="processing",
    )
    payload_jsonb = payload_mapping(pending_payload, "payload_jsonb", "payloadJsonb")
    value = payload_text(payload_jsonb, "value")
    field_name = payload_text(payload_jsonb, "fieldName", "field_name")
    if not value or not field_name:
        raise VaultSessionToolRuntimeError(409, "contact_use_invalid", "The pending contact use request is missing data.")
    confirmed = _updated_pending_payload(pending_payload, status="confirmed", timestamp_field="confirmed_at")
    _upsert_contact_pending(store=store, account_id=account_id, workspace_id=workspace_id, pending_payload=confirmed)
    return {
        "status": "confirmed",
        "message": "Contact field confirmed for use.",
        "pendingActionId": pending_id,
        "contactUseConfirmationId": pending_id,
        "fieldName": field_name,
        "value": value,
        "purpose": payload_text(payload_jsonb, "purpose"),
    }


def _contact_records(
    *,
    store: ContactsStore,
    account_id: str,
    workspace_id: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    return store.list_private_records(
        account_id=account_id,
        workspace_id=workspace_id,
        source_table="contacts_entries",
        limit=limit,
    )


def _contact_pending_records(
    *,
    store: ContactsStore,
    account_id: str,
    workspace_id: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    return store.list_private_records(
        account_id=account_id,
        workspace_id=workspace_id,
        source_table="contacts_pending_actions",
        limit=limit,
    )


def _find_contact_record(
    *,
    store: ContactsStore,
    account_id: str,
    workspace_id: str,
    contact_id: str | None,
) -> Mapping[str, Any] | None:
    if not contact_id:
        return None
    get_private_record = getattr(store, "get_private_record", None)
    if callable(get_private_record):
        record = get_private_record(
            account_id=account_id,
            workspace_id=workspace_id,
            source_table="contacts_entries",
            source_id=contact_id,
        )
        if record is None:
            return None
        payload = source_payload(record)
        return None if _contact_is_deleted(payload) else record
    for record in _contact_records(store=store, account_id=account_id, workspace_id=workspace_id, limit=1000):
        payload = source_payload(record)
        if _contact_is_deleted(payload):
            continue
        if contact_id in {_contact_id(payload, record), payload_text(payload, "contactId")}:
            return record
    return None


def _require_contact_record(
    *,
    store: ContactsStore,
    account_id: str,
    workspace_id: str,
    contact_id: str | None,
) -> Mapping[str, Any]:
    record = _find_contact_record(store=store, account_id=account_id, workspace_id=workspace_id, contact_id=contact_id)
    if record is None:
        raise VaultSessionToolRuntimeError(404, "contact_not_found", "The requested contact was not found.")
    return record


def _find_contact_pending_record(
    *,
    store: ContactsStore,
    account_id: str,
    workspace_id: str,
    pending_id: str | None,
) -> Mapping[str, Any] | None:
    if not pending_id:
        return None
    get_private_record = getattr(store, "get_private_record", None)
    if callable(get_private_record):
        return get_private_record(
            account_id=account_id,
            workspace_id=workspace_id,
            source_table="contacts_pending_actions",
            source_id=pending_id,
        )
    for record in _contact_pending_records(store=store, account_id=account_id, workspace_id=workspace_id, limit=1000):
        payload = source_payload(record)
        if pending_id in {
            str(record.get("sourceId") or ""),
            payload_text(payload, "contacts_pending_action_id", "pendingActionId"),
        }:
            return record
    return None


def _require_contact_pending_record(
    *,
    store: ContactsStore,
    account_id: str,
    workspace_id: str,
    pending_id: str | None,
) -> Mapping[str, Any]:
    record = _find_contact_pending_record(
        store=store,
        account_id=account_id,
        workspace_id=workspace_id,
        pending_id=pending_id,
    )
    if record is None:
        raise VaultSessionToolRuntimeError(404, "contact_pending_not_found", "The pending contact action was not found.")
    payload = source_payload(record)
    status = payload_text(payload, "status")
    if status != "pending":
        raise VaultSessionToolRuntimeError(409, "contact_pending_terminal", "The pending contact action can no longer be updated.")
    if _contact_pending_expired(payload):
        raise VaultSessionToolRuntimeError(409, "contact_pending_expired", "The pending contact action has expired.")
    return record


def _upsert_contact_pending(
    *,
    store: ContactsStore,
    account_id: str,
    workspace_id: str,
    pending_payload: dict[str, Any],
) -> None:
    pending_id = payload_text(pending_payload, "contacts_pending_action_id", "pendingActionId")
    if not pending_id:
        raise VaultSessionToolRuntimeError(409, "contact_pending_invalid", "The pending contact action is missing an id.")
    upsert_private_record(
        store=store,
        account_id=account_id,
        workspace_id=workspace_id,
        source_table="contacts_pending_actions",
        source_id=pending_id,
        source_payload=pending_payload,
        content_text=_contact_pending_content_text(pending_payload),
    )


def _claim_contact_pending(
    *,
    store: ContactsStore,
    account_id: str,
    workspace_id: str,
    pending_id: str,
    pending_payload: dict[str, Any],
    claimed_status: str,
) -> dict[str, Any]:
    claim = getattr(store, "claim_private_record_status", None)
    if not callable(claim):
        # Compatibility for deterministic in-memory test stores. Production
        # Vault stores implement the atomic claim contract.
        return {**pending_payload, "status": claimed_status, "updated_at": now_iso()}
    claimed = claim(
        account_id=account_id,
        workspace_id=workspace_id,
        source_table="contacts_pending_actions",
        source_id=pending_id,
        expected_status="pending",
        claimed_status=claimed_status,
    )
    if claimed is None:
        raise VaultSessionToolRuntimeError(
            409,
            "contact_pending_terminal",
            "The pending contact action can no longer be updated.",
        )
    return dict(source_payload(claimed))


def _contact_search_item(record: Mapping[str, Any]) -> dict[str, Any]:
    payload = source_payload(record)
    contact_id = _contact_id(payload, record)
    email = _contact_field_text(payload, "email_address")
    phone = _contact_field_text(payload, "phone_number")
    address = _contact_field_text(payload, "address")
    website = _contact_field_text(payload, "website")
    notes = _contact_field_text(payload, "notes")
    return {
        "contactId": contact_id,
        "displayName": _contact_display_name(payload),
        "firstName": payload_text(payload, "first_name", "firstName"),
        "lastName": payload_text(payload, "last_name", "lastName"),
        "businessName": payload_text(payload, "business_name", "businessName"),
        "hasEmail": bool(email),
        "hasPhone": bool(phone),
        "hasAddress": bool(address),
        "hasWebsite": bool(website),
        "hasNotes": bool(notes),
        "maskedEmail": _mask_email(email),
        "maskedPhone": _mask_phone(phone),
        "websiteHost": _website_host(website),
        "updatedAt": payload_text(payload, "updated_at", "updatedAt") or payload_text(record, "updatedAt"),
    }


def _contact_full_item(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "contactId": _contact_id(payload, None),
        "firstName": payload_text(payload, "first_name", "firstName"),
        "lastName": payload_text(payload, "last_name", "lastName"),
        "businessName": payload_text(payload, "business_name", "businessName"),
        "address": _contact_field_text(payload, "address"),
        "phoneNumber": _contact_field_text(payload, "phone_number"),
        "emailAddress": _contact_field_text(payload, "email_address"),
        "website": _contact_field_text(payload, "website"),
        "notes": _contact_field_text(payload, "notes"),
        "updatedAt": payload_text(payload, "updated_at", "updatedAt"),
    }


def _contact_id(payload: Mapping[str, Any] | None, record: Mapping[str, Any] | None) -> str | None:
    payload = payload or {}
    value = payload_text(payload, "contacts_entry_id", "contactId", "contact_id")
    if value:
        return value
    if record is not None:
        record_source_id = record.get("sourceId")
        return str(record_source_id).strip() if record_source_id else None
    return None


def _contact_payload_from_arguments(arguments: Mapping[str, Any]) -> dict[str, str | None]:
    nested = arguments.get("contactPayload")
    if not isinstance(nested, Mapping):
        nested = arguments.get("contact")
    source = nested if isinstance(nested, Mapping) else arguments
    return _clean_contact_payload(source)


def _contact_payload_from_source(payload: Mapping[str, Any]) -> dict[str, str | None]:
    return {
        "first_name": payload_text(payload, "first_name", "firstName"),
        "last_name": payload_text(payload, "last_name", "lastName"),
        "business_name": payload_text(payload, "business_name", "businessName"),
        "address": payload_text(payload, "address"),
        "phone_number": payload_text(payload, "phone_number", "phoneNumber", "phone"),
        "email_address": payload_text(payload, "email_address", "emailAddress", "email"),
        "website": payload_text(payload, "website", "url"),
        "notes": payload_text(payload, "notes"),
    }


def _clean_contact_payload(payload: Mapping[str, Any]) -> dict[str, str | None]:
    return {
        "first_name": _clean_optional_contact_text(_payload_raw(payload, "first_name", "firstName")),
        "last_name": _clean_optional_contact_text(_payload_raw(payload, "last_name", "lastName")),
        "business_name": _clean_optional_contact_text(_payload_raw(payload, "business_name", "businessName")),
        "address": _clean_optional_contact_text(_payload_raw(payload, "address")),
        "phone_number": _clean_optional_contact_text(_payload_raw(payload, "phone_number", "phoneNumber", "phone")),
        "email_address": _clean_optional_contact_text(_payload_raw(payload, "email_address", "emailAddress", "email")),
        "website": _clean_optional_contact_text(_payload_raw(payload, "website", "url")),
        "notes": _clean_optional_contact_text(_payload_raw(payload, "notes")),
    }


def _payload_raw(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def _clean_optional_contact_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise VaultSessionToolRuntimeError(400, "invalid_contact_field", "Contact fields must be text.")
    stripped = value.strip()
    return stripped or None


def _contact_entry_source_payload(
    *,
    contact_id: str,
    account_id: str,
    workspace_id: str,
    payload: Mapping[str, str | None],
    source_type: str | None = None,
    source_file_key: str | None = None,
    source_session_id: str | None = None,
    existing_payload: Mapping[str, Any] | None = None,
    deleted_at: str | None = None,
) -> dict[str, Any]:
    now = now_iso()
    source = dict(existing_payload or {})
    source.update(
        {
            "contacts_entry_id": contact_id,
            "account_id": account_id,
            "workspace_id": workspace_id,
            "first_name": payload.get("first_name"),
            "last_name": payload.get("last_name"),
            "business_name": payload.get("business_name"),
            "address": payload.get("address"),
            "phone_number": payload.get("phone_number"),
            "email_address": payload.get("email_address"),
            "website": payload.get("website"),
            "notes": payload.get("notes"),
            "normalized_name": normalize_search_text(" ".join(filter(None, [payload.get("first_name"), payload.get("last_name")]))),
            "normalized_business_name": normalize_search_text(payload.get("business_name") or "") or None,
            "normalized_email_address": (payload.get("email_address") or "").strip().lower() or None,
            "normalized_phone_number": _normalize_phone(payload.get("phone_number")),
            "search_text": normalize_search_text(_contact_payload_text(payload)),
            "source_type": source_type if source_type is not None else payload_text(source, "source_type", "sourceType"),
            "source_file_key": source_file_key if source_file_key is not None else payload_text(source, "source_file_key", "sourceFileKey"),
            "source_session_id": source_session_id if source_session_id is not None else payload_text(source, "source_session_id", "sourceSessionId"),
            "updated_at": now,
        }
    )
    source.setdefault("created_at", now)
    if deleted_at is not None:
        source["deleted_at"] = deleted_at
    return source


def _contact_entry_content_text(payload: Mapping[str, Any]) -> str:
    return "\n".join(
        value
        for value in (
            _contact_display_name(payload),
            _contact_field_text(payload, "email_address"),
            _contact_field_text(payload, "phone_number"),
            _contact_field_text(payload, "address"),
            _contact_field_text(payload, "website"),
            _contact_field_text(payload, "notes"),
        )
        if value
    )


def _contact_pending_content_text(payload: Mapping[str, Any]) -> str:
    values = [
        payload_text(payload, "action_type", "actionType"),
        payload_text(payload, "status"),
        payload_text(payload, "confirmation_summary", "confirmationSummary"),
    ]
    payload_jsonb = payload_mapping(payload, "payload_jsonb", "payloadJsonb")
    contact = payload_jsonb.get("contact")
    if isinstance(contact, Mapping):
        values.append(_contact_payload_text(_contact_payload_from_source(contact)))
    values.append(payload_text(payload_jsonb, "value"))
    return "\n".join(value for value in values if value)


def _contact_pending_response(pending_payload: Mapping[str, Any], *, message: str) -> dict[str, Any]:
    return {
        "status": payload_text(pending_payload, "status"),
        "message": message,
        "pendingActionId": payload_text(pending_payload, "contacts_pending_action_id", "pendingActionId"),
        "actionType": payload_text(pending_payload, "action_type", "actionType"),
        "confirmationRequired": True,
        "summary": payload_text(pending_payload, "confirmation_summary", "confirmationSummary"),
        "expiresAt": payload_text(pending_payload, "expires_at", "expiresAt"),
    }


def _updated_pending_payload(payload: Mapping[str, Any], *, status: str, timestamp_field: str) -> dict[str, Any]:
    updated = dict(payload)
    now = now_iso()
    updated["status"] = status
    updated[timestamp_field] = now
    updated["updated_at"] = now
    return updated


def _contact_save_summary(
    *,
    action_type: str,
    payload: Mapping[str, str | None],
    existing: Mapping[str, Any] | None,
) -> str:
    if action_type == "delete" and existing is not None:
        return f"Delete contact {_contact_display_name(existing)}?"
    if action_type == "update" and existing is not None:
        return f"Update contact {_contact_display_name(existing)} with: {_contact_payload_summary(payload)}?"
    return f"Save contact {_contact_payload_display_name(payload)}: {_contact_payload_summary(payload)}?"


def _contact_payload_summary(payload: Mapping[str, str | None]) -> str:
    parts = []
    for key, value in payload.items():
        if value:
            parts.append(f"{_contact_field_label(key)} {value}")
    return "; ".join(parts) if parts else "no fields"


def _contact_payload_display_name(payload: Mapping[str, str | None]) -> str:
    name = " ".join(filter(None, [payload.get("first_name"), payload.get("last_name")])).strip()
    return (
        name
        or payload.get("business_name")
        or payload.get("email_address")
        or payload.get("phone_number")
        or payload.get("website")
        or "Unnamed contact"
    )


def _contact_payload_text(payload: Mapping[str, str | None]) -> str:
    return " ".join(value for key in CONTACT_PAYLOAD_FIELDS if (value := payload.get(key)))


def _contact_search_haystack(record: Mapping[str, Any]) -> str:
    """Return contact values only; JSON object key names are not data."""

    payload = source_payload(record)
    values = [
        payload_text(record, "contentText"),
        payload_text(payload, "search_text", "searchText"),
        _contact_display_name(payload),
        *(_contact_field_text(payload, field_name) for field_name in CONTACT_PAYLOAD_FIELDS),
    ]
    return "\n".join(value for value in values if value).lower()


def _contact_display_name(payload: Mapping[str, Any]) -> str:
    display_name = payload_text(payload, "display_name", "displayName")
    if display_name:
        return display_name
    name = " ".join(
        filter(
            None,
            [
                payload_text(payload, "first_name", "firstName"),
                payload_text(payload, "last_name", "lastName"),
            ],
        )
    ).strip()
    return (
        name
        or payload_text(payload, "business_name", "businessName")
        or payload_text(payload, "email_address", "emailAddress", "email")
        or payload_text(payload, "phone_number", "phoneNumber", "phone")
        or payload_text(payload, "website", "url")
        or "Unnamed contact"
    )


def _contact_field_text(payload: Mapping[str, Any], field_name: str) -> str | None:
    aliases = {
        "first_name": ("first_name", "firstName"),
        "last_name": ("last_name", "lastName"),
        "business_name": ("business_name", "businessName"),
        "address": ("address",),
        "phone_number": ("phone_number", "phoneNumber", "phone"),
        "email_address": ("email_address", "emailAddress", "email"),
        "website": ("website", "url"),
        "notes": ("notes",),
    }
    return payload_text(payload, *aliases.get(field_name, (field_name,)))


def _contact_is_deleted(payload: Mapping[str, Any]) -> bool:
    return bool(payload_text(payload, "deleted_at", "deletedAt"))


def _contact_pending_expired(payload: Mapping[str, Any]) -> bool:
    expires_at = payload_text(payload, "expires_at", "expiresAt")
    if not expires_at:
        return False
    try:
        parsed = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed <= datetime.now(UTC)


def _contact_action_type(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in CONTACT_SAVE_ACTIONS:
        raise VaultSessionToolRuntimeError(400, "unsupported_contact_action", "Unsupported contact save action.")
    return normalized


def _contact_use_field(value: str) -> str:
    normalized = value.strip().lower()
    field = {
        "email": "email_address",
        "emailaddress": "email_address",
        "email_address": "email_address",
        "phone": "phone_number",
        "phonenumber": "phone_number",
        "phone_number": "phone_number",
        "address": "address",
        "website": "website",
        "url": "website",
        "site": "website",
        "notes": "notes",
        "note": "notes",
    }.get(normalized, normalized)
    if field not in CONTACT_USE_FIELDS:
        raise VaultSessionToolRuntimeError(400, "unsupported_contact_field", "Unsupported contact field for use.")
    return field


def _contact_field_label(field_name: str) -> str:
    return {
        "first_name": "first name",
        "last_name": "last name",
        "business_name": "business",
        "address": "address",
        "phone_number": "phone",
        "email_address": "email",
        "website": "website",
        "notes": "notes",
    }.get(field_name, field_name.replace("_", " "))


def _mask_contact_value(field_name: str, value: str | None) -> str | None:
    if field_name == "email_address":
        return _mask_email(value)
    if field_name == "phone_number":
        return _mask_phone(value)
    if field_name == "address" and value:
        return "address on file"
    if field_name == "website":
        return _website_host(value) or "website on file"
    if field_name == "notes" and value:
        return "notes on file"
    return None


def _mask_email(value: str | None) -> str | None:
    if not value or "@" not in value:
        return None
    local, domain = value.split("@", 1)
    return f"{local[:1]}***@{domain}" if local else f"***@{domain}"


def _mask_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) < 4:
        return "***"
    return f"***-***-{digits[-4:]}"


def _website_host(value: str | None) -> str | None:
    if not value:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    without_scheme = stripped.split("://", 1)[-1]
    return without_scheme.split("/", 1)[0] or None


def _normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    return digits or None
