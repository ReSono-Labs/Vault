from __future__ import annotations

import json
from datetime import UTC, datetime

from app.vault_runtime.commands.service import CommandService
from app.vault_runtime.background_agent.coordination_contracts import OwnerScope
from app.vault_runtime.local_identity.models import LocalPrincipal
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult

# Chat shares the Voice catalog; Voice must never offer these.
CHAT_ONLY_TOOL_NAMES = frozenset({"command_run", "command_run_approved"})

_DIRECTORY = {
    "type": "string", "minLength": 1,
    "description": "Folder to run in, e.g. local/Projects/app. Must be inside one of the person's folders.",
}


def _principal(context: ToolInvocationContext) -> LocalPrincipal:
    return LocalPrincipal(
        user_id=context.user_id, username="agent", display_name="Agent", experience_style="balanced",
        is_device_owner=False, session_id=context.local_session_id or context.execution_id or "agent",
        workspace_id=context.workspace_id, expires_at=datetime.now(UTC),
    )


def _result(payload: dict[str, object], *, error: bool = False) -> ToolInvocationResult:
    return ToolInvocationResult(json.dumps(payload, separators=(",", ":")), payload, is_error=error)


def register_command_tools(*, catalog: ToolCatalog, service: CommandService) -> None:
    def chat_only(context: ToolInvocationContext) -> ToolInvocationResult | None:
        if context.agent is not AgentKind.VOICE or not context.conversation_id or context.voice_session_id:
            return _result({"error": "Commands can only be run from Chat."}, error=True)
        return None

    def run(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        denied = chat_only(context)
        if denied:
            return denied
        return _result(service.prepare_chat(
            principal=_principal(context), conversation_id=str(context.conversation_id),
            directory=str(arguments.get("directory", "")).strip(), command=str(arguments.get("command", "")),
        ))

    def run_approved(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        denied = chat_only(context)
        if denied:
            return denied
        return _result(service.run_approved_chat(
            principal=_principal(context), conversation_id=str(context.conversation_id),
            request_id=str(arguments.get("requestId", "")).strip(),
        ))

    def run_read_only(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        if context.agent is not AgentKind.BACKGROUND:
            return _result({"error": "Only the Background Agent runs commands without approval."}, error=True)
        return _result(service.run_background(
            principal=OwnerScope(context.user_id, context.workspace_id), directory=str(arguments.get("directory", "")).strip(),
            command=str(arguments.get("command", "")),
        ))

    def git_info(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
        principal = OwnerScope(context.user_id, context.workspace_id) if context.agent is AgentKind.BACKGROUND else _principal(context)
        return _result(service.git_info(principal=principal, directory=str(arguments.get("directory", "")).strip()))

    enabled = lambda _user_id, _workspace_id: service.enabled()  # noqa: E731
    for definition in (
        ToolDefinition(
            tool_id="builtin.command-run.v1",
            name="command_run",
            description=(
                "Ask to run a shell command inside one of the person's folders (Linux shell; network allowed; "
                "60-second limit; 64 KB of output). It does NOT run yet: the person sees the command and clicks "
                "Run or Don't run. Explain what the command does and why in one or two sentences. Prefer the "
                "workspace_* tools for finding and reading files; use commands for things like tests, builds, "
                "git or data processing."
            ),
            input_schema={
                "type": "object",
                "properties": {"directory": _DIRECTORY,
                               "command": {"type": "string", "minLength": 1, "maxLength": 2000}},
                "required": ["directory", "command"],
                "additionalProperties": False,
            },
            handler=run, effect_class="write", audiences=frozenset({AgentKind.VOICE}), availability=enabled,
        ),
        ToolDefinition(
            tool_id="builtin.command-run-approved.v1",
            name="command_run_approved",
            description=(
                "Run a command the person approved by clicking Run. Pass the requestId from command_run. "
                "It fails if they haven't approved it yet or chose Don't run; never retry a denied command."
            ),
            input_schema={
                "type": "object",
                "properties": {"requestId": {"type": "string", "minLength": 1}},
                "required": ["requestId"],
                "additionalProperties": False,
            },
            handler=run_approved, effect_class="write", audiences=frozenset({AgentKind.VOICE}), availability=enabled,
        ),
        ToolDefinition(
            tool_id="builtin.git-repo-info.v1",
            name="git_repo_info",
            description=(
                "Read a Git repository's summary without asking: remote URLs (credentials removed), current "
                "branch, upstream and ahead/behind, the last 5 commits, and changed files. Works even when "
                "hidden files are hidden (Vault opens only the repository's .git folder). Use this instead of "
                "running git remote/status/log as a command. It runs inside Vault, so it can't tell whether "
                "programs such as gh are installed or logged in on the person's computer."
            ),
            input_schema={
                "type": "object",
                "properties": {"directory": {**_DIRECTORY, "description": "A directory inside the repository, e.g. local/Projects/ReSono-Labs-Link."}},
                "required": ["directory"],
                "additionalProperties": False,
            },
            handler=git_info, effect_class="read", audiences=frozenset({AgentKind.VOICE, AgentKind.BACKGROUND}),
            availability=enabled,
        ),
        ToolDefinition(
            tool_id="builtin.command-run-read-only.v1",
            name="command_run_read_only",
            description=(
                "Run one read-only program inside one of the person's folders without asking: rg, grep, ls, "
                "tree, wc, head, tail, cat, file, du, stat, find, sort, uniq, diff, jq, fd, and git status/log/"
                "diff/show/ls-files/blame/branch/tag. No pipes, redirects, variables or wildcards. Nothing "
                "in the folder can be changed. 60-second limit."
            ),
            input_schema={
                "type": "object",
                "properties": {"directory": _DIRECTORY,
                               "command": {"type": "string", "minLength": 1, "maxLength": 2000}},
                "required": ["directory", "command"],
                "additionalProperties": False,
            },
            handler=run_read_only, effect_class="read", audiences=frozenset({AgentKind.BACKGROUND}),
            availability=enabled,
        ),
    ):
        catalog.register(definition)
