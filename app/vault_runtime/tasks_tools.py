"""Canonical Voice Tasks tools ported from the R1 builtin Tasks domain."""

from __future__ import annotations

import json

from app.vault_runtime.builtin_plugins import BuiltinPluginRepository
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tasks.repository import TaskRepository, task_view
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult


def register_tasks_tools(
    *,
    catalog: ToolCatalog,
    repository: TaskRepository,
    builtin_plugins: BuiltinPluginRepository | None = None,
) -> None:
    descriptions = {
        "tasks_list": "List local tasks, open by default.",
        "tasks_read": "Read one local task.",
        "tasks_add": "Prepare a plain-text task. Preserve any date or future wording the user supplied in the task text, but tell the user Tasks cannot schedule it or send a reminder. Read the exact prepared text back and ask before confirming.",
        "tasks_edit": "Prepare replacement plain-text task text. Preserve any date or future wording the user supplied in the text, but tell the user Tasks cannot schedule it or send a reminder. Read the exact replacement text back and ask before confirming.",
        "tasks_mark_completed": "Prepare marking a task completed. Ask before confirming.",
        "tasks_remove": "Prepare permanent removal of a task. Ask before confirming.",
        "tasks_confirm_action": "Execute one unchanged reviewed Task action after explicit approval within ten minutes.",
    }
    schemas = {
        "tasks_list": _schema({"includeCompleted": {"type": "boolean"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100}}),
        "tasks_read": _schema({"taskId": {"type": "string"}}, ("taskId",)),
        "tasks_add": _schema({"text": {"type": "string"}}, ("text",)),
        "tasks_edit": _schema({"taskId": {"type": "string"}, "text": {"type": "string"}}, ("taskId", "text")),
        "tasks_mark_completed": _schema({"taskId": {"type": "string"}}, ("taskId",)),
        "tasks_remove": _schema({"taskId": {"type": "string"}}, ("taskId",)),
        "tasks_confirm_action": _schema({"actionId": {"type": "string"}, "contentHash": {"type": "string"}}, ("actionId", "contentHash")),
    }

    def guard(context: ToolInvocationContext) -> ToolInvocationResult | None:
        if builtin_plugins is not None and not builtin_plugins.enabled(
            account_id=context.user_id, workspace_id=context.workspace_id, plugin_key="tasks",
        ):
            return ToolInvocationResult("Tasks is turned off.", is_error=True)
        return None

    def handler(name: str):
        def execute(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
            blocked = guard(context)
            if blocked is not None:
                return blocked
            try:
                payload = _invoke(repository=repository, name=name, context=context, arguments=arguments)
                return ToolInvocationResult(json.dumps(payload, separators=(",", ":")), payload)
            except Exception as exc:
                return ToolInvocationResult(str(exc), is_error=True)
        return execute

    for name in descriptions:
        catalog.register(ToolDefinition(
            tool_id=f"builtin.{name.replace('_', '-')}.v1",
            name=name,
            description=descriptions[name],
            input_schema=schemas[name],
            handler=handler(name),
            effect_class="read" if name in {"tasks_list", "tasks_read"} else "write",
            audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}),
            availability=(
                (lambda user_id, workspace_id: builtin_plugins.enabled(
                    account_id=user_id, workspace_id=workspace_id, plugin_key="tasks",
                ))
                if builtin_plugins is not None else None
            ),
        ))


def _invoke(
    *,
    repository: TaskRepository,
    name: str,
    context: ToolInvocationContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    user_id, workspace_id = context.user_id, context.workspace_id
    if name == "tasks_list":
        items = repository.list(
            user_id=user_id,
            workspace_id=workspace_id,
            include_completed=bool(arguments.get("includeCompleted", False)),
            limit=_limit(arguments),
        )
        return {"tasks": [task_view(item) for item in items]}
    if name == "tasks_read":
        item = repository.get(user_id=user_id, workspace_id=workspace_id, task_id=_required(arguments, "taskId"))
        if item is None:
            raise ValueError("Task was not found.")
        return task_view(item)
    if name == "tasks_confirm_action":
        return _confirm(repository=repository, context=context, arguments=arguments)
    return _prepare(repository=repository, name=name, context=context, arguments=arguments)


def _prepare(
    *,
    repository: TaskRepository,
    name: str,
    context: ToolInvocationContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    operation = {
        "tasks_add": "add",
        "tasks_edit": "edit",
        "tasks_mark_completed": "complete",
        "tasks_remove": "remove",
    }.get(name)
    if operation is None:
        raise ValueError("Task tool is unavailable.")
    payload: dict[str, object] = {}
    if operation in {"add", "edit"}:
        payload["text"] = _required(arguments, "text")
    return repository.prepare(
        user_id=context.user_id,
        workspace_id=context.workspace_id,
        operation=operation,
        task_id=_optional(arguments, "taskId"),
        payload=payload,
        voice_session_id=context.voice_session_id or context.local_session_id or "",
        tool_call_id=context.tool_call_id or "",
        utterance_id=int(context.user_utterance_id or 0),
    )


def _confirm(
    *,
    repository: TaskRepository,
    context: ToolInvocationContext,
    arguments: dict[str, object],
) -> dict[str, object]:
    action_id = _required(arguments, "actionId")
    claim = repository.claim(
        user_id=context.user_id,
        workspace_id=context.workspace_id,
        action_id=action_id,
        content_hash=_required(arguments, "contentHash"),
        voice_session_id=context.voice_session_id or context.local_session_id or "",
        approval_utterance_id=int(context.user_utterance_id or 0),
    )
    try:
        item = repository.execute(user_id=context.user_id, workspace_id=context.workspace_id, claim=claim)
    except Exception:
        repository.finish(action_id, completed=False)
        raise
    repository.finish(action_id, completed=True)
    return {"state": "completed", "actionId": action_id, "task": task_view(item) if item is not None else None}


def _schema(properties: dict[str, object], required: tuple[str, ...] = ()) -> dict[str, object]:
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


def _required(value: dict[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item.strip():
        raise ValueError(f"{key} is required.")
    return item.strip()


def _optional(value: dict[str, object], key: str) -> str | None:
    item = value.get(key)
    return item.strip() if isinstance(item, str) and item.strip() else None


def _limit(value: dict[str, object]) -> int:
    item = value.get("limit", 25)
    return max(1, min(item, 100)) if isinstance(item, int) and not isinstance(item, bool) else 25
