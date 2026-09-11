from __future__ import annotations

from threading import Event, Thread
from uuid import uuid4

from app.vault_runtime.agent_network.client import A2AClient, A2AError, task_result
from app.vault_runtime.agent_network.repository import A2AConnection, A2ARepository
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.definitions import ToolInvocationContext


class A2AService:
    def __init__(self, *, repository: A2ARepository, client: A2AClient | None=None) -> None:
        self.repository=repository; self.client=client or A2AClient(); self._stop=Event(); self._thread: Thread|None=None

    def start(self) -> None:
        if self._thread is None:
            self._thread=Thread(target=self._poll_loop,name="vault-a2a-poller",daemon=True); self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread: self._thread.join(timeout=3)

    def connect(self, *, user_id: str, workspace_id: str, display_name: str, card_url: str, token: str="") -> A2AConnection:
        card=self.client.discover(card_url,token)
        return self.repository.create(connection_id=str(uuid4()),user_id=user_id,workspace_id=workspace_id,
          display_name=display_name.strip() or card.name,card_url=card.card_url,rpc_url=card.rpc_url,card=card.card,token=token.strip())

    def send(self, *, context: ToolInvocationContext, connection_id: str, message: str) -> dict[str, object]:
        message=message.strip()
        if not message or len(message)>16000: raise A2AError("a2a_request_invalid","The external-agent message is invalid.")
        connection=self.repository.get(user_id=context.user_id,workspace_id=context.workspace_id,connection_id=connection_id)
        if not connection.enabled: raise A2AError("a2a_connection_disabled","The external-agent connection is disabled.")
        owner_kind="voice" if context.agent is AgentKind.VOICE else "background"
        owner_id=context.voice_session_id if owner_kind=="voice" else context.execution_id
        owner_id=owner_id or context.local_session_id
        context_id=self.repository.context(connection_id=connection_id,user_id=context.user_id,workspace_id=context.workspace_id,owner_kind=owner_kind,owner_id=owner_id) or f"ctx-{uuid4().hex}"
        capabilities = connection.agent_card.get("capabilities")
        asynchronous = isinstance(capabilities, dict) and bool(
            capabilities.get("pushNotifications") or capabilities.get("streaming")
        )
        task=self.client.send(rpc_url=connection.rpc_url,token=self.repository.token(connection),message=message,context_id=context_id,return_immediately=asynchronous)
        state,summary,issue=task_result(task); remote_id=str(task.get("id") or ""); context_id=str(task.get("contextId") or context_id)
        record_id=str(uuid4())
        self.repository.save_task(record_id=record_id,connection=connection,owner_kind=owner_kind,owner_id=owner_id,context_id=context_id,remote_task_id=remote_id,state=state,summary=summary,issue=issue)
        return {"taskId":record_id,"remoteTaskId":remote_id,"contextId":context_id,"agentName":connection.display_name,"state":state,"summary":summary,"issue":issue}

    def _poll_loop(self) -> None:
        while not self._stop.wait(2):
            for item in self.repository.pending():
                try:
                    connection=self.repository.get(user_id=str(item["userId"]),workspace_id=str(item["workspaceId"]),connection_id=str(item["connectionId"]))
                    task=self.client.get_task(rpc_url=connection.rpc_url,token=self.repository.token(connection),task_id=str(item["remoteTaskId"]))
                    state,summary,issue=task_result(task)
                    self.repository.save_task(record_id=str(item["recordId"]),connection=connection,owner_kind=str(item["ownerKind"]),owner_id=str(item["ownerId"]),context_id=str(task.get("contextId") or item["contextId"]),remote_task_id=str(item["remoteTaskId"]),state=state,summary=summary,issue=issue)
                except Exception:
                    continue
