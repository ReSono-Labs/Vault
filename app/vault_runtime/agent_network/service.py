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
        self._inbound=None

    def attach_inbound(self, inbound) -> None:
        self._inbound = inbound

    def listen_info(self, *, user_id: str, workspace_id: str) -> dict[str, str]:
        if self._inbound is None:
            raise RuntimeError("Agent2Agent inbound is unavailable.")
        return self._inbound.listen_info(user_id=user_id, workspace_id=workspace_id)

    def start(self) -> None:
        if self._thread is None:
            self._thread=Thread(target=self._poll_loop,name="vault-a2a-poller",daemon=True); self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread: self._thread.join(timeout=3)
        inbound_http = getattr(self, "_inbound_http", None)
        if inbound_http is not None:
            inbound_http.stop()

    def connect(self, *, user_id: str, workspace_id: str, display_name: str, card_url: str, token: str="") -> A2AConnection:
        token=token.strip()
        if token and self.repository.inbound_token_equals(user_id=user_id, workspace_id=workspace_id, token=token):
            raise ValueError("The outbound bearer must not be this Vault's inbound Agent2Agent token.")
        card=self.client.discover(card_url,token)
        return self.repository.create(connection_id=str(uuid4()),user_id=user_id,workspace_id=workspace_id,
          display_name=display_name.strip() or card.name,card_url=card.card_url,rpc_url=card.rpc_url,card=card.card,token=token)

    def apply_link_snapshot(self, *, inbound: list[dict[str, str]], outbound: list[dict[str, object]]) -> dict[str, object]:
        scopes = self.repository.inbound_scopes()
        if not scopes:
            raise ValueError("Turn on Agent2Agent in Vault before Link can apply Agent Network peers.")
        accept: list[tuple[str, str]] = []
        for item in inbound:
            grant_id = str(item.get("grant_id") or "").strip()
            token = str(item.get("token") or "").strip()
            if not grant_id or not token:
                raise ValueError("Link inbound peers need grant_id and token.")
            accept.append((grant_id, token))
        accept_tokens = tuple(accept)
        outbound_rows: list[tuple[str, str, str, str]] = []
        for item in outbound:
            grant_id = str(item.get("grant_id") or "").strip()
            name = str(item.get("alias") or item.get("name") or "").strip()
            url = str(item.get("url") or "").rstrip("/")
            token = str(item.get("token") or "").strip()
            if not grant_id or not name or not url or not token:
                raise ValueError("Link outbound peers need grant_id, name, url, and token.")
            outbound_rows.append((grant_id, name, url, token))
        active_grants = tuple(row[0] for row in outbound_rows)
        for user_id, workspace_id in scopes:
            self.repository.replace_link_accept(user_id=user_id, workspace_id=workspace_id, tokens=accept_tokens)
            self.repository.prune_link_connections(
                user_id=user_id, workspace_id=workspace_id, active_grant_ids=active_grants,
            )
            for grant_id, name, url, token in outbound_rows:
                card_url = f"{url}/.well-known/agent-card.json"
                # The route origin is only bootstrap metadata. The peer's
                # authenticated Agent Card is authoritative for the RPC path.
                rpc_url = f"{url}/"
                card = {
                    "name": name,
                    "description": "Link Agent Network peer",
                    "supportedInterfaces": [{
                        "protocolBinding": "JSONRPC",
                        "protocolVersion": "1.0",
                        "url": rpc_url,
                    }],
                    "securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"}},
                }
                self.repository.upsert_link_connection(
                    user_id=user_id, workspace_id=workspace_id, grant_id=grant_id,
                    display_name=name, card_url=card_url, rpc_url=rpc_url, card=card, token=token,
                )
        return {"applied": True, "workspaces": len(scopes), "inbound": len(accept_tokens), "outbound": len(outbound)}

    def clear_link_snapshot(self) -> None:
        self.repository.clear_link_managed()

    def _resolve_link_peer(self, connection: A2AConnection, token: str) -> A2AConnection:
        if connection.link_grant_id is None:
            return connection
        discovered = self.client.discover(connection.card_url, token)
        return self.repository.refresh_link_card(
            connection=connection, rpc_url=discovered.rpc_url, card=discovered.card,
        )

    def send(self, *, context: ToolInvocationContext, connection_id: str, message: str) -> dict[str, object]:
        message=message.strip()
        if not message or len(message)>16000: raise A2AError("a2a_request_invalid","The external-agent message is invalid.")
        connection=self.repository.get(user_id=context.user_id,workspace_id=context.workspace_id,connection_id=connection_id)
        if not connection.enabled: raise A2AError("a2a_connection_disabled","The external-agent connection is disabled.")
        token=self.repository.token(connection)
        connection=self._resolve_link_peer(connection, token)
        owner_kind="voice" if context.agent is AgentKind.VOICE else "background"
        owner_id=context.voice_session_id if owner_kind=="voice" else context.execution_id
        owner_id=owner_id or context.local_session_id
        context_id=self.repository.context(connection_id=connection_id,user_id=context.user_id,workspace_id=context.workspace_id,owner_kind=owner_kind,owner_id=owner_id) or f"ctx-{uuid4().hex}"
        capabilities = connection.agent_card.get("capabilities")
        asynchronous = isinstance(capabilities, dict) and bool(
            capabilities.get("pushNotifications") or capabilities.get("streaming")
        )
        task=self.client.send(rpc_url=connection.rpc_url,token=token,message=message,context_id=context_id,return_immediately=asynchronous)
        state,summary,issue=task_result(task); remote_id=str(task.get("id") or ""); context_id=str(task.get("contextId") or context_id)
        record_id=str(uuid4())
        self.repository.save_task(record_id=record_id,connection=connection,owner_kind=owner_kind,owner_id=owner_id,context_id=context_id,remote_task_id=remote_id,state=state,summary=summary,issue=issue)
        return {"taskId":record_id,"remoteTaskId":remote_id,"contextId":context_id,"agentName":connection.display_name,"state":state,"summary":summary,"issue":issue}

    def _poll_loop(self) -> None:
        while not self._stop.wait(2):
            for item in self.repository.pending():
                try:
                    connection=self.repository.get(user_id=str(item["userId"]),workspace_id=str(item["workspaceId"]),connection_id=str(item["connectionId"]))
                    token=self.repository.token(connection)
                    connection=self._resolve_link_peer(connection, token)
                    task=self.client.get_task(rpc_url=connection.rpc_url,token=token,task_id=str(item["remoteTaskId"]))
                    state,summary,issue=task_result(task)
                    self.repository.save_task(record_id=str(item["recordId"]),connection=connection,owner_kind=str(item["ownerKind"]),owner_id=str(item["ownerId"]),context_id=str(task.get("contextId") or item["contextId"]),remote_task_id=str(item["remoteTaskId"]),state=state,summary=summary,issue=issue)
                except Exception:
                    continue
