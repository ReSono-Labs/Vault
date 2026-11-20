"""Explicit MCP discovery/grant/catalog projection adapted from frozen R1 donors."""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
import json
import re

from jsonschema import Draft202012Validator

from app.vault_runtime.extensions.mcp_client import McpClient, McpProtocolError
from app.vault_runtime.extensions.repository import ExtensionRecord, ExtensionRepository
from app.vault_runtime.extensions.models import ExtensionKind
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult


McpClientFactory = Callable[[ExtensionRecord, ToolInvocationContext], McpClient]


class McpLifecycle:
    def __init__(self, *, repository: ExtensionRepository, catalog: ToolCatalog, client_factory: McpClientFactory) -> None:
        self._repository = repository
        self._catalog = catalog
        self._client_factory = client_factory
        self._sources_by_extension: dict[str, set[str]] = {}

    def client_for(self, connection: ExtensionRecord, context: ToolInvocationContext) -> McpClient:
        return self._client_factory(connection, context)

    def discover(
        self, *, actor_user_id: str, workspace_id: str,
        connection: ExtensionRecord, client: McpClient,
    ) -> tuple[str, ...]:
        if connection.kind.value != "mcp" or connection.workspace_id != workspace_id:
            raise ValueError("MCP connection scope is invalid")
        client.initialize()
        discovered = client.discover_tools()
        rows = tuple((
            item.name, item.title, item.description, item.input_schema, item.output_schema,
            _discovery_hash(item.name, item.description, item.input_schema, item.output_schema),
        ) for item in discovered)
        self._repository.replace_mcp_tools(
            actor_user_id=actor_user_id, workspace_id=workspace_id,
            extension_id=connection.extension_id, tools=rows,
        )
        # Discovery is intentionally persistence only. It grants and projects nothing.
        return tuple(item.name for item in discovered)

    def project_scope(
        self, *, user_id: str, workspace_id: str, agent: AgentKind,
        connection: ExtensionRecord,
    ) -> tuple[str, ...]:
        source_id = self._source_id(user_id, workspace_id, agent, connection.extension_id)
        granted = self._repository.granted_mcp_tools(
            user_id=user_id, workspace_id=workspace_id, agent=agent,
            extension_id=connection.extension_id,
        )
        definitions = tuple(
            self._definition(
                user_id=user_id, workspace_id=workspace_id, agent=agent,
                connection=connection, remote_name=name, description=description,
                input_schema=input_schema, output_schema=output_schema, effect=effect,
            )
            for name, description, input_schema, output_schema, effect in granted
        )
        self._catalog.replace_capability_source(source_id, definitions)
        self._sources_by_extension.setdefault(connection.extension_id, set()).add(source_id)
        return tuple(item.name for item in definitions)

    def restore_scope(
        self, *, user_id: str, workspace_id: str, agent: AgentKind
    ) -> tuple[str, ...]:
        """Rebuild the in-memory catalog projection from durable scoped grants."""
        records: dict[str, ExtensionRecord] = {}
        for record, _capability, _effect in self._repository.granted_extensions(
            user_id=user_id, workspace_id=workspace_id, agent=agent,
            kind=ExtensionKind.MCP,
        ):
            records[record.extension_id] = record
        projected: list[str] = []
        for record in records.values():
            projected.extend(self.project_scope(
                user_id=user_id, workspace_id=workspace_id, agent=agent,
                connection=record,
            ))
        return tuple(projected)

    def revoke_scope(
        self, *, user_id: str, workspace_id: str, agent: AgentKind, extension_id: str,
    ) -> None:
        self._catalog.remove_capability_source(self._source_id(user_id, workspace_id, agent, extension_id))
        sources = self._sources_by_extension.get(extension_id)
        if sources is not None:
            sources.discard(self._source_id(user_id, workspace_id, agent, extension_id))
            if not sources:
                self._sources_by_extension.pop(extension_id, None)

    def remove_extension(self, extension_id: str) -> None:
        for source_id in self._sources_by_extension.pop(extension_id, set()):
            self._catalog.remove_capability_source(source_id)

    def enter_safe_mode(self) -> None:
        for extension_id in tuple(self._sources_by_extension):
            self.remove_extension(extension_id)

    def _definition(
        self, *, user_id: str, workspace_id: str, agent: AgentKind,
        connection: ExtensionRecord, remote_name: str, description: str,
        input_schema: dict[str, object], output_schema: dict[str, object] | None,
        effect: str,
    ) -> ToolDefinition:
        model_name = _model_name(connection.extension_id, user_id, workspace_id, agent, remote_name)
        scope_hash = sha256(f"{user_id}:{workspace_id}:{agent.value}".encode()).hexdigest()[:12]

        def invoke(context: ToolInvocationContext, arguments: dict[str, object]) -> ToolInvocationResult:
            # Recheck durable grant at invocation, not only at projection time.
            current = self._repository.granted_mcp_tools(
                user_id=context.user_id, workspace_id=context.workspace_id,
                agent=context.agent, extension_id=connection.extension_id,
            )
            if remote_name not in {item[0] for item in current}:
                return ToolInvocationResult("Tool grant was revoked.", is_error=True)
            try:
                client = self._client_factory(connection, context)
                client.initialize()
                result = client.call_tool(remote_name, arguments)
                structured = result.get("structuredContent")
                if output_schema is not None:
                    if not isinstance(structured, dict):
                        raise McpProtocolError("MCP tool omitted required structured output")
                    Draft202012Validator(output_schema).validate(structured)
                text_parts = [
                    str(item["text"]) for item in result.get("content", [])
                    if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str)
                ]
                text = "\n".join(text_parts) or (
                    json.dumps(structured, separators=(",", ":")) if isinstance(structured, dict)
                    else "MCP tool returned non-text content."
                )
                return ToolInvocationResult(text, structured_content=structured if isinstance(structured, dict) else None, is_error=bool(result.get("isError", False)))
            except Exception:
                return ToolInvocationResult("MCP tool invocation failed.", is_error=True)

        return ToolDefinition(
            tool_id=f"mcp:{connection.extension_id}:{scope_hash}:{remote_name}", name=model_name,
            description=description, input_schema=input_schema, handler=invoke,
            effect_class=effect, audiences=frozenset({agent}),
            scope_user_id=user_id, scope_workspace_id=workspace_id,
        )

    @staticmethod
    def _source_id(user_id: str, workspace_id: str, agent: AgentKind, extension_id: str) -> str:
        return f"mcp:{extension_id}:{workspace_id}:{user_id}:{agent.value}"


def _model_name(extension_id: str, user_id: str, workspace_id: str, agent: AgentKind, remote_name: str) -> str:
    prefix = sha256(f"{extension_id}:{user_id}:{workspace_id}:{agent.value}".encode()).hexdigest()[:10]
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", remote_name)[:100]
    return f"mcp_{prefix}_{safe}"


def _discovery_hash(name: str, description: str, input_schema: object, output_schema: object) -> str:
    return sha256(json.dumps(
        [name,description,input_schema,output_schema], sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
