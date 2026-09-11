from __future__ import annotations

from app.vault_runtime.agent_network.client import A2AError
from app.vault_runtime.agent_network.service import A2AService
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools import ToolCatalog, ToolDefinition, ToolInvocationResult


def register_a2a_tools(catalog: ToolCatalog, service: A2AService) -> None:
    def list_agents(context, _arguments):
        items=service.repository.list(user_id=context.user_id,workspace_id=context.workspace_id)
        return ToolInvocationResult("\n".join(f"{i.display_name} ({i.connection_id})" for i in items) or "No external agents are connected.",{"agents":[{"connectionId":i.connection_id,"name":i.display_name,"card":i.agent_card} for i in items]})
    def send(context, arguments):
        try:
            result=service.send(context=context,connection_id=str(arguments["connectionId"]),message=str(arguments["message"]))
            text=f"{result['agentName']} is still working. Vault will notify you when it finishes." if result["state"] in {"working","submitted"} else f"{result['agentName']} replied: {result['summary']}"
            return ToolInvocationResult(text,result,is_error=bool(result["issue"]))
        except (A2AError,ValueError) as exc:
            return ToolInvocationResult(str(exc),{"error":getattr(exc,"code","a2a_failed")},is_error=True)
    audiences=frozenset({AgentKind.VOICE,AgentKind.BACKGROUND})
    catalog.register(ToolDefinition(tool_id="builtin.a2a.list.v1",name="agent2agent_list",description="List external A2A agents connected to this Vault and their Agent Cards.",input_schema={"type":"object","additionalProperties":False},handler=list_agents,effect_class="read",audiences=audiences))
    catalog.register(ToolDefinition(tool_id="builtin.a2a.send.v1",name="agent2agent_send",description="Send work or a follow-up message to a connected external A2A agent. Vault preserves conversation continuity and reports completion later when the peer keeps working.",input_schema={"type":"object","properties":{"connectionId":{"type":"string","minLength":1},"message":{"type":"string","minLength":1,"maxLength":16000}},"required":["connectionId","message"],"additionalProperties":False},handler=send,effect_class="write",audiences=audiences))
