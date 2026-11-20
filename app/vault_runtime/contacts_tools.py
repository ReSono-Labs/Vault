"""Canonical tool-catalog adapter for the carried Voice Contacts broker."""

from __future__ import annotations

import json

from app.vault_runtime.personal_data import PersonalDataRepository
from app.vault_runtime.session_tools.brokers.contacts import CONTACT_TOOL_NAMES, contacts_tool_result
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult


_SCHEMAS: dict[str, dict[str, object]] = {
    "contacts_search": {
        "type": "object", "properties": {
            "query": {"type": "string", "minLength": 1},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20},
        }, "required": ["query"], "additionalProperties": False,
    },
    "contacts_prepare_save": {
        "type": "object", "properties": {
            "actionType": {"enum": ["create", "update", "delete"]},
            "contactId": {"type": "string"}, "firstName": {"type": "string"},
            "lastName": {"type": "string"}, "businessName": {"type": "string"},
            "address": {"type": "string"}, "phoneNumber": {"type": "string"},
            "emailAddress": {"type": "string"}, "website": {"type": "string"},
            "notes": {"type": "string"},
        }, "required": ["actionType"], "additionalProperties": False,
    },
    "contacts_confirm_pending": {
        "type": "object", "properties": {
            "pendingActionId": {"type": "string", "minLength": 1}, "approve": {"type": "boolean"},
        }, "required": ["pendingActionId"], "additionalProperties": False,
    },
    "contacts_prepare_use": {
        "type": "object", "properties": {
            "contactId": {"type": "string", "minLength": 1},
            "field": {"enum": ["email_address", "phone_number", "address", "website", "notes"]},
        }, "required": ["contactId", "field"], "additionalProperties": False,
    },
    "contacts_confirm_use": {
        "type": "object", "properties": {
            "pendingActionId": {"type": "string", "minLength": 1}, "approve": {"type": "boolean"},
        }, "required": ["pendingActionId"], "additionalProperties": False,
    },
}


_DESCRIPTIONS: dict[str, str] = {
    "contacts_prepare_save": "Prepare saving, changing or deleting a contact, keeping every detail the user did not change. "
                             "Then call contacts_confirm_pending in the same turn to show the owner's approval card.",
    "contacts_confirm_pending": "Show the owner's Approve/Decline card for a prepared contact change; it is saved only if the owner approves.",
    "contacts_prepare_use": "Prepare using one contact field. Then call contacts_confirm_use in the same turn to show the owner's approval card.",
    "contacts_confirm_use": "Show the owner's Approve/Decline card for using a prepared contact field; it is released only if the owner approves.",
}


def register_contacts_tools(*, catalog: ToolCatalog, store: PersonalDataRepository, background_actions=None) -> None:
    def handler(name: str):
        def execute(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
            if context.background_scope is not None and name != "contacts_search":
                if background_actions is None:
                    return ToolInvocationResult("Background approvals are unavailable.", is_error=True)
                return background_actions.invoke(context, name, arguments)
            try:
                payload = contacts_tool_result(
                    store=store, account_id=context.user_id, workspace_id=context.workspace_id,
                    voice_realtime_session_id=context.voice_session_id or context.local_session_id,
                    tool_call_id=context.tool_call_id, tool_name=name, arguments=arguments,
                )
                return ToolInvocationResult(json.dumps(payload, separators=(",", ":")), payload)
            except Exception as exc:
                return ToolInvocationResult(str(exc), is_error=True)
        return execute

    for name in sorted(CONTACT_TOOL_NAMES):
        catalog.register(ToolDefinition(
            tool_id=f"builtin.{name.replace('_', '-')}.v1", name=name,
            description=_DESCRIPTIONS.get(name, f"Use the local Vault Contacts client: {name.replace('_', ' ')}."),
            input_schema=_SCHEMAS[name], handler=handler(name),
            effect_class="read" if name == "contacts_search" else "write",
            audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}),
        ))
