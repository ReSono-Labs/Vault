"""Canonical fixed-agent adapter for the copied Voice Mail tool implementation."""

from __future__ import annotations

import json

from app.vault_runtime.email_runtime import LocalEmailRuntime
from types import SimpleNamespace
from app.vault_runtime.signals.email.session_tools import EMAIL_SIGNAL_CACHE_TOOLS, EMAIL_SIGNAL_SIDE_EFFECT_TOOLS
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult
from app.vault_runtime.builtin_plugins import BuiltinPluginRepository


def register_email_tools(*, catalog: ToolCatalog, runtime: LocalEmailRuntime, builtin_plugins: BuiltinPluginRepository | None = None) -> None:
    schemas = _schemas()
    descriptions = _descriptions()
    for name in sorted(EMAIL_SIGNAL_CACHE_TOOLS | EMAIL_SIGNAL_SIDE_EFFECT_TOOLS):
        def execute(context: ToolInvocationContext, arguments: dict[str, object], tool_name=name) -> ToolInvocationResult:
            principal = SimpleNamespace(user_id=context.user_id, workspace_id=context.workspace_id)
            try:
                with runtime.tools(principal) as tools:
                    kwargs = dict(
                        account_id=context.user_id, workspace_id=context.workspace_id,
                        voice_realtime_session_id=context.voice_session_id or context.local_session_id,
                        tool_call_id=context.tool_call_id, tool_name=tool_name, arguments=arguments,
                    )
                    payload = (tools.execute_cache_tool(**kwargs) if tool_name in EMAIL_SIGNAL_CACHE_TOOLS
                               else tools.execute_side_effect_tool(**kwargs))
                return ToolInvocationResult(json.dumps(payload, separators=(",", ":")), payload)
            except Exception as exc:
                return ToolInvocationResult(str(exc), is_error=True)
        catalog.register(ToolDefinition(
            tool_id=f"builtin.{name.replace('_', '-')}.v1", name=name,
            description=descriptions[name], input_schema=schemas[name], handler=execute,
            effect_class="read" if name in EMAIL_SIGNAL_CACHE_TOOLS else "write",
            audiences=frozenset({AgentKind.VOICE}),
        ))
    agent_names = {name for name in EMAIL_SIGNAL_CACHE_TOOLS | EMAIL_SIGNAL_SIDE_EFFECT_TOOLS if name in {"email_check","email_get_unread","email_search","email_read","email_mark_read","email_mark_unread","email_compose","email_send_pending","email_archive"}}
    for email_name in sorted(agent_names):
        agent_name = email_name.replace("email_", "agent_mail_", 1)
        def execute_agent(context: ToolInvocationContext, arguments: dict[str, object], source_name=email_name) -> ToolInvocationResult:
            if builtin_plugins is not None and not builtin_plugins.enabled(account_id=context.user_id, workspace_id=context.workspace_id, plugin_key="agent_mail"):
                return ToolInvocationResult("Agent Mail is turned off.", is_error=True)
            principal = SimpleNamespace(user_id=context.user_id, workspace_id=context.workspace_id)
            try:
                with runtime.tools(principal, mailbox_role="agent_mail") as tools:
                    kwargs = dict(account_id=context.user_id, workspace_id=context.workspace_id, voice_realtime_session_id=context.voice_session_id or context.local_session_id, tool_call_id=context.tool_call_id, tool_name=source_name, arguments=arguments)
                    payload = tools.execute_cache_tool(**kwargs) if source_name in EMAIL_SIGNAL_CACHE_TOOLS else tools.execute_side_effect_tool(**kwargs)
                return ToolInvocationResult(json.dumps(payload, separators=(",", ":")), payload)
            except Exception as exc: return ToolInvocationResult(str(exc), is_error=True)
        catalog.register(ToolDefinition(tool_id=f"builtin.{agent_name.replace('_','-')}.v1", name=agent_name, description=descriptions[email_name].replace("email", "Agent Mail"), input_schema=schemas[email_name], handler=execute_agent, effect_class="read" if email_name in EMAIL_SIGNAL_CACHE_TOOLS else "write", audiences=frozenset({AgentKind.VOICE}), availability=(lambda user_id, workspace_id: builtin_plugins.enabled(account_id=user_id, workspace_id=workspace_id, plugin_key="agent_mail")) if builtin_plugins is not None else None))


def _object(properties: dict[str, object], required: tuple[str, ...] = ()) -> dict[str, object]:
    value: dict[str, object] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        value["required"] = list(required)
    return value


def _schemas() -> dict[str, dict[str, object]]:
    text = {"type": "string"}; mailbox = {"mailboxAccountId": text}
    message = {**mailbox, "messageId": text, "sourceFolder": text}
    return {
        "email_account_status": _object(mailbox), "email_list_folders": _object(mailbox),
        "email_check": _object({**mailbox, "folder": text, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}),
        "email_get_unread": _object({**mailbox, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}),
        "email_search": _object({**mailbox, "query": text, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}, ("query",)),
        "email_read": _object({**mailbox, "messageId": text}, ("messageId",)),
        "email_read_attachment": _object({**mailbox, "attachmentId": text}, ("attachmentId",)),
        "email_mark_read": _object(message, ("messageId",)), "email_mark_unread": _object(message, ("messageId",)),
        "email_contact_lookup": _object({**mailbox, "query": text, "limit": {"type": "integer", "minimum": 1, "maximum": 25}}, ("query",)),
        "email_compose": _object({**mailbox, "to": {"type": "array", "items": text, "minItems": 1}, "subject": text, "body": text}, ("to", "subject", "body")),
        "email_send_pending": _object({**mailbox, "pendingRequestId": text, "approve": {"type": "boolean"}}, ("pendingRequestId",)),
        "email_archive": _object(message, ("messageId",)),
        "email_create_folder": _object({**mailbox, "folderName": text}, ("folderName",)),
        "email_rename_folder": _object({**mailbox, "sourceFolder": text, "destinationFolder": text}, ("sourceFolder", "destinationFolder")),
        "email_move_message": _object({**mailbox, "messageId": text, "sourceFolder": text, "destinationFolder": text}, ("messageId", "sourceFolder", "destinationFolder")),
    }


def _descriptions() -> dict[str, str]:
    return {
        "email_account_status": "List connected Vault Email mailboxes and truthful synchronization status.",
        "email_list_folders": "List folders for an approved Vault Email mailbox.",
        "email_check": "Check recent email messages from an approved linked account.",
        "email_get_unread": "Get unread email messages from an approved linked account.",
        "email_search": "Search email by contact name, partial email address, subject, or text.",
        "email_read": "Read a specific email message from an approved linked account.",
        "email_read_attachment": "Retrieve one explicitly requested attachment from an approved Vault Email mailbox.",
        "email_mark_read": "Mark a specific email message as read.", "email_mark_unread": "Mark a specific email message as unread.",
        "email_contact_lookup": "Find email contacts by name or partial email address.",
        "email_compose": "Create a pending email send request that still requires confirmation.",
        "email_send_pending": "Confirm and send a previously prepared pending email request.",
        "email_archive": "Archive a specific email message without deleting it.",
        "email_create_folder": "Create an ordinary mailbox folder.", "email_rename_folder": "Rename an ordinary mailbox folder.",
        "email_move_message": "Move a message between ordinary folders; moving to Trash is prohibited.",
    }
