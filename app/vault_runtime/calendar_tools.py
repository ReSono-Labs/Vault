"""Canonical Voice Calendar tools over copied donor cache/provider behavior."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
from uuid import uuid4

from app.vault_runtime.calendar_runtime import LocalCalendarRuntime
from app.vault_runtime.personal_data import PersonalDataRepository
from app.vault_runtime.session_tools.brokers.provider_cache import CALENDAR_CACHE_TOOLS, provider_cache_result
from app.vault_runtime.session_tools.records import upsert_private_record
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult


def register_calendar_tools(*, catalog: ToolCatalog, runtime: LocalCalendarRuntime, records: PersonalDataRepository) -> None:
    for name, schema, description in _read_specs():
        def read(context: ToolInvocationContext, arguments: dict[str, object], tool_name=name) -> ToolInvocationResult:
            try:
                principal = SimpleNamespace(user_id=context.user_id, workspace_id=context.workspace_id)
                if arguments.get("freshness") == "live":
                    linked = str(arguments.get("linkedAccountId") or "").strip()
                    if linked:
                        runtime.sync(principal, linked)  # type: ignore[arg-type]
                items = runtime.events(principal, limit=1000)  # type: ignore[arg-type]
                payload = provider_cache_result(tool_name=tool_name, arguments=arguments, items=items)
                return ToolInvocationResult(json.dumps(payload, separators=(",", ":")), payload)
            except Exception as exc:
                return ToolInvocationResult(str(exc), is_error=True)
        catalog.register(ToolDefinition(
            tool_id=f"builtin.{name.replace('_', '-')}.v1", name=name, description=description,
            input_schema=schema, handler=read, effect_class="read", audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}),
        ))

    def create(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        try:
            payload = _calendar_create(
                runtime=runtime, records=records, context=context, arguments=arguments,
            )
            return ToolInvocationResult(json.dumps(payload, separators=(",", ":")), payload)
        except Exception as exc:
            return ToolInvocationResult(str(exc), is_error=True)
    catalog.register(ToolDefinition(
        tool_id="builtin.calendar-create.v1", name="calendar_create",
        description="Prepare a Calendar event, then create it only after explicit confirmation.",
        input_schema=_create_schema(), handler=create, effect_class="write",
        audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}),
    ))


def _calendar_create(*, runtime: LocalCalendarRuntime, records: PersonalDataRepository,
                     context: ToolInvocationContext, arguments: dict[str, object]) -> dict[str, object]:
    pending_id = str(arguments.get("pendingActionId") or "").strip()
    if not pending_id:
        linked = str(arguments.get("linkedAccountId") or "").strip()
        title, starts = str(arguments.get("title") or "").strip(), str(arguments.get("startsAt") or "").strip()
        if not linked or not title or not starts or "approve" in arguments:
            raise ValueError("Calendar create requires linkedAccountId, title and startsAt before confirmation.")
        pending_id = f"calendar-pending-{uuid4()}"
        now = datetime.now(UTC)
        payload = {
            "calendar_pending_action_id": pending_id, "status": "pending_confirmation",
            "arguments": dict(arguments), "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=15)).isoformat(),
            "voice_realtime_session_id": context.voice_session_id or context.local_session_id,
            "tool_call_id": context.tool_call_id,
        }
        upsert_private_record(
            store=records, account_id=context.user_id, workspace_id=context.workspace_id,
            source_table="calendar_pending_actions", source_id=pending_id,
            source_payload=payload, content_text=f"{title}\n{starts}",
        )
        return {"status": "pending_confirmation", "pendingActionId": pending_id,
                "confirmationRequired": True, "providerSideEffect": "not_executed",
                "event": {"title": title, "startsAt": starts}}
    if set(arguments) - {"pendingActionId", "approve"}:
        raise ValueError("Calendar confirmation accepts only pendingActionId and approve.")
    record = records.get_private_record(
        account_id=context.user_id, workspace_id=context.workspace_id,
        source_table="calendar_pending_actions", source_id=pending_id,
    )
    if record is None or record["sourcePayload"].get("status") != "pending_confirmation":
        raise ValueError("Calendar pending action is unavailable or already terminal.")
    payload = record["sourcePayload"]
    if datetime.fromisoformat(str(payload["expires_at"])) <= datetime.now(UTC):
        raise ValueError("Calendar pending action expired.")
    approve = arguments.get("approve")
    if not isinstance(approve, bool):
        raise ValueError("Calendar confirmation requires approve true or false.")
    claimed = records.claim_private_record_status(
        account_id=context.user_id, workspace_id=context.workspace_id,
        source_table="calendar_pending_actions", source_id=pending_id,
        expected_status="pending_confirmation", claimed_status="processing" if approve else "cancelled",
    )
    if claimed is None:
        raise ValueError("Calendar pending action was already claimed.")
    if not approve:
        return {"status": "cancelled", "pendingActionId": pending_id, "providerSideEffect": "not_executed"}
    original = payload.get("arguments")
    if not isinstance(original, dict):
        raise ValueError("Calendar pending action is invalid.")
    principal = SimpleNamespace(user_id=context.user_id, workspace_id=context.workspace_id)
    event = runtime.create_event(principal, str(original["linkedAccountId"]), original)  # type: ignore[arg-type]
    completed = dict(payload); completed.update({"status": "completed", "completed_at": datetime.now(UTC).isoformat()})
    upsert_private_record(
        store=records, account_id=context.user_id, workspace_id=context.workspace_id,
        source_table="calendar_pending_actions", source_id=pending_id,
        source_payload=completed, content_text=str(original.get("title") or ""),
    )
    return {"status": "completed", "pendingActionId": pending_id,
            "providerSideEffect": "executed", "event": event}


def _read_specs():
    text = {"type": "string"}; common = {"linkedAccountId": text, "freshness": {"enum": ["cache", "live"]}}
    obj = lambda props, required=(): {"type": "object", "properties": props,
                                      **({"required": list(required)} if required else {}), "additionalProperties": False}
    return (
        ("calendar_check", obj({**common, "startsAtFrom": {"type": "string", "format": "date-time"}, "startsAtTo": {"type": "string", "format": "date-time"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}), "Check upcoming events across an approved linked calendar."),
        ("calendar_read_day", obj({**common, "targetDate": {"type": "string", "format": "date"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}), "Read events for a specific day from an approved linked calendar."),
        ("calendar_search", obj({**common, "query": text, "startsAtFrom": {"type": "string", "format": "date-time"}, "startsAtTo": {"type": "string", "format": "date-time"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, ("query",)), "Search Calendar events by title, description, location, or organizer."),
        ("calendar_read_event", obj({**common, "eventId": text}, ("eventId",)), "Read a specific event from an approved linked calendar."),
    )


def _create_schema():
    text = {"type": "string"}
    return {"type": "object", "properties": {"linkedAccountId": text, "title": text,
            "startsAt": {"type": "string", "format": "date-time"}, "endsAt": {"type": "string", "format": "date-time"},
            "allDay": {"type": "boolean"}, "description": text, "location": text,
            "pendingActionId": text, "approve": {"type": "boolean"}}, "additionalProperties": False}
