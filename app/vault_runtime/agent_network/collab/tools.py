from __future__ import annotations

import json
from typing import Any

from app.vault_runtime.agent_network.collab.a2a_rpc import A2aRpcError
from app.vault_runtime.agent_network.collab.coordinator import TurnCoordinator
from app.vault_runtime.agent_network.collab.types import PeerEndpoint
from app.vault_runtime.agent_network.service import A2AService
from app.vault_runtime.agent_network.tools import Agent2AgentOption, agent2agent_option_on
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools import ToolCatalog, ToolDefinition, ToolInvocationResult

COLLAB_PLUGIN = "agent2agent_collab"
UNKNOWN_PEER_MESSAGE = "That A2A peer is not connected."


def collab_tools_available(option: Agent2AgentOption | None, user_id: str, workspace_id: str) -> bool:
    return agent2agent_option_on(option, user_id, workspace_id)


def _format_turn(result: dict[str, Any]) -> str:
    status = result.get("status", "unknown")
    peer = result.get("peer", "?")
    context_id = result.get("context_id") or ""
    task_id = result.get("task_id") or ""
    header = f"[{peer} · status {status}"
    if context_id:
        header += f" · context {context_id}"
    if task_id:
        header += f" · task {task_id}"
    header += "]"
    if result.get("error"):
        return f"{header}\nError: {result['error']}"
    body = (result.get("response_text") or "").strip() or "(no text reply)"
    return f"{header}\n{body}"


def _load_peer(service: A2AService, *, user_id: str, workspace_id: str, peer_name: str) -> PeerEndpoint:
    needle = peer_name.strip().lower()
    for item in service.repository.list(user_id=user_id, workspace_id=workspace_id):
        if not item.enabled:
            continue
        if item.connection_id.lower() != needle and item.display_name.strip().lower() != needle:
            continue
        token = service.repository.token(item)
        url = str(item.rpc_url or "").strip()
        if not url:
            raise ValueError(f"peer {peer_name!r} has no url")
        if not token:
            raise ValueError(f"peer {peer_name!r} has no bearer token")
        return PeerEndpoint(name=item.display_name, url=url, token=token)
    raise KeyError(peer_name)


def register_collab_tools(
    catalog: ToolCatalog,
    service: A2AService,
    *,
    builtin_plugins: Agent2AgentOption | None = None,
    coordinator: TurnCoordinator | None = None,
) -> None:
    turns = coordinator or TurnCoordinator()

    def available(user_id: str, workspace_id: str) -> bool:
        return collab_tools_available(builtin_plugins, user_id, workspace_id)

    def refuse_if_off(user_id: str, workspace_id: str) -> ToolInvocationResult | None:
        if not agent2agent_option_on(builtin_plugins, user_id, workspace_id):
            return ToolInvocationResult("Agent2Agent is turned off.", {"error": "a2a_option_disabled"}, is_error=True)
        return None

    def turn(context, arguments):
        blocked = refuse_if_off(context.user_id, context.workspace_id)
        if blocked is not None:
            return blocked
        peer_name = str(
            arguments.get("peer") or arguments.get("agent") or arguments.get("agent_name") or ""
        ).strip()
        message = str(arguments.get("message") or arguments.get("text") or "").strip()
        context_id = str(arguments.get("context_id") or arguments.get("contextId") or "").strip() or None
        timeout = float(arguments.get("timeout") or 120.0)
        if not peer_name or not message:
            return ToolInvocationResult("Error: both 'peer' and 'message' are required.", {"error": "collab_args"}, is_error=True)
        try:
            peer = _load_peer(
                service, user_id=context.user_id, workspace_id=context.workspace_id, peer_name=peer_name,
            )
            result = turns.send(peer, message, context_id=context_id, wait=True, timeout=timeout)
        except KeyError:
            return ToolInvocationResult(UNKNOWN_PEER_MESSAGE, {"error": "unknown_peer"}, is_error=True)
        except (A2aRpcError, ValueError) as exc:
            return ToolInvocationResult(f"Error: A2A collab turn failed — {exc}", {"error": "collab_failed"}, is_error=True)
        except Exception as exc:
            return ToolInvocationResult(f"Error: A2A collab turn failed — {exc}", {"error": "collab_failed"}, is_error=True)
        return ToolInvocationResult(_format_turn(result), result)

    def list_turns(context, arguments):
        blocked = refuse_if_off(context.user_id, context.workspace_id)
        if blocked is not None:
            return blocked
        try:
            limit = max(1, min(int(arguments.get("limit") or 20), 100))
        except (TypeError, ValueError):
            limit = 20
        recorded = turns.list_turns(limit)
        if not recorded:
            return ToolInvocationResult("No recorded A2A collab turns yet.", {"turns": []})
        return ToolInvocationResult(json.dumps(recorded, indent=2), {"turns": recorded})

    audiences = frozenset({AgentKind.VOICE, AgentKind.BACKGROUND})
    catalog.register(ToolDefinition(
        tool_id="builtin.a2a.collab.turn.v1", name="a2a_collab_turn",
        description="Send a message to another agent and wait for their reply.",
        input_schema={
            "type": "object",
            "properties": {
                "peer": {"type": "string", "minLength": 1},
                "message": {"type": "string", "minLength": 1, "maxLength": 16000},
                "context_id": {"type": "string"},
                "timeout": {"type": "number"},
            },
            "required": ["peer", "message"],
            "additionalProperties": False,
        },
        handler=turn, effect_class="write", audiences=audiences,
        availability=lambda user_id, workspace_id: available(user_id, workspace_id),
    ))
    catalog.register(ToolDefinition(
        tool_id="builtin.a2a.collab.list.v1", name="a2a_collab_list",
        description="Show recent back-and-forth with other agents.",
        input_schema={
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
            "additionalProperties": False,
        },
        handler=list_turns, effect_class="read", audiences=audiences,
        availability=lambda user_id, workspace_id: available(user_id, workspace_id),
    ))
