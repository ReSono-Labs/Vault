"""Explicit MCP discovery/grant/catalog projection adapted from frozen R1 donors."""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
import json
import re

from jsonschema import ValidationError

from app.core.security.json_schema import offline_validator
from app.vault_runtime.extensions.mcp_client import (
    McpAuthError, McpClient, McpProtocolError, McpTimeoutError, McpTransportError,
)
from app.vault_runtime.extensions.mcp_rules import connection_executable
from app.vault_runtime.extensions.repository import ExtensionRecord, ExtensionRepository
from app.vault_runtime.extensions.models import ExtensionKind
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult


McpClientFactory = Callable[[ExtensionRecord, ToolInvocationContext], McpClient]
# After a 401/403: a message for the person, or None when their sign-in was renewed (retry once).
AuthRefused = Callable[[ExtensionRecord, ToolInvocationContext, McpAuthError], "str | None"]


class McpLifecycle:
    def __init__(self, *, repository: ExtensionRepository, catalog: ToolCatalog, client_factory: McpClientFactory,
                 auth_refused: AuthRefused | None = None) -> None:
        self._repository = repository
        self._catalog = catalog
        self._client_factory = client_factory
        self._auth_refused = auth_refused
        self._sources_by_extension: dict[str, set[str]] = {}

    def client_for(self, connection: ExtensionRecord, context: ToolInvocationContext) -> McpClient:
        return self._client_factory(connection, context)

    def discover(
        self, *, actor_user_id: str, workspace_id: str,
        connection: ExtensionRecord, client: McpClient,
    ) -> tuple[str, ...]:
        if connection.kind.value != "mcp" or connection.workspace_id != workspace_id:
            raise ValueError("MCP connection scope is invalid")
        if not connection_executable(connection.configuration):
            raise McpProtocolError("MCP connection uses an unsupported transport")
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
        if not connection_executable(connection.configuration):
            self._catalog.remove_capability_source(source_id)  # Never project an unsupported transport.
            return ()
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
            if not connection_executable(connection.configuration):
                return ToolInvocationResult("MCP connection uses an unsupported transport.", is_error=True)
            def call() -> dict[str, object]:
                client = self._client_factory(connection, context)
                client.initialize()
                return client.call_tool(remote_name, arguments, input_schema=input_schema)

            try:
                try:
                    result = call()
                except McpAuthError as refused:
                    # The server refused before running anything, so one retry after a renewed
                    # sign-in cannot repeat the action.
                    message = (self._auth_refused(connection, context, refused) if self._auth_refused
                               else "MCP server refused the credentials. Reconnect this connection's account.")
                    if message is not None:
                        return ToolInvocationResult(message, is_error=True)
                    result = call()
            except McpTimeoutError:
                return ToolInvocationResult(
                    "MCP server did not answer in time. The tool may still have run; check before retrying.",
                    is_error=True)
            except McpAuthError as refused:
                message = self._auth_refused(connection, context, refused) if self._auth_refused else None
                return ToolInvocationResult(
                    message or "MCP server refused the credentials. Reconnect this connection's account.", is_error=True)
            except McpTransportError:
                return ToolInvocationResult("MCP server could not be reached.", is_error=True)
            except McpProtocolError as exc:
                code = f" ({exc.code})" if exc.code is not None else ""
                return ToolInvocationResult(f"MCP server returned an error{code}: {str(exc)[:300]}", is_error=True)
            except Exception:
                return ToolInvocationResult("MCP tool invocation failed.", is_error=True)
            return _tool_result(result, output_schema)

        return ToolDefinition(
            tool_id=f"mcp:{connection.extension_id}:{scope_hash}:{remote_name}", name=model_name,
            description=description, input_schema=input_schema, handler=invoke,
            effect_class=effect, audiences=frozenset({agent}),
            scope_user_id=user_id, scope_workspace_id=workspace_id,
        )

    @staticmethod
    def _source_id(user_id: str, workspace_id: str, agent: AgentKind, extension_id: str) -> str:
        return f"mcp:{extension_id}:{workspace_id}:{user_id}:{agent.value}"


def _tool_result(result: dict[str, object], output_schema: dict[str, object] | None) -> ToolInvocationResult:
    """Project an MCP tool result. A tool error is returned as-is: its structured output
    need not match the output schema."""
    is_error = bool(result.get("isError", False))
    has_structured = "structuredContent" in result
    structured = result.get("structuredContent")
    if output_schema is not None and not is_error:
        if not has_structured:
            return ToolInvocationResult("MCP tool omitted its required structured output.", is_error=True)
        try:
            offline_validator(output_schema).validate(structured)
        except ValidationError:
            return ToolInvocationResult("MCP tool output did not match its declared schema.", is_error=True)
        except Exception:      # e.g. a reference outside the schema, persisted before that check
            return ToolInvocationResult("MCP tool output schema is refused.", is_error=True)
    parts = [_describe(item) for item in result.get("content", []) if isinstance(item, dict)]
    text = "\n".join(part for part in parts if part)
    if not text:
        text = (json.dumps(structured, separators=(",", ":")) if has_structured
                else "MCP tool returned no content.")
    return ToolInvocationResult(
        text, structured_content=structured if isinstance(structured, dict) else None, is_error=is_error,
    )


def _describe(item: dict[str, object]) -> str:
    """Text as-is; other content types are named so the model knows what came back."""
    kind = item.get("type")
    if kind == "text":
        return str(item.get("text", ""))
    if kind in ("image", "audio"):
        return f"[{kind} content: {str(item.get('mimeType') or 'unknown type')[:100]}]"
    if kind == "resource_link":
        name = item.get("name") or item.get("uri")
        return f"[resource link: {str(name)[:200]} <{str(item.get('uri', ''))[:500]}>]"
    if kind == "resource":
        resource = item.get("resource") if isinstance(item.get("resource"), dict) else {}
        if isinstance(resource.get("text"), str):
            return str(resource["text"])
        return f"[embedded resource: {str(resource.get('uri', ''))[:500]}]"
    return f"[{str(kind)[:50]} content]"


def _model_name(extension_id: str, user_id: str, workspace_id: str, agent: AgentKind, remote_name: str) -> str:
    prefix = sha256(f"{extension_id}:{user_id}:{workspace_id}:{agent.value}".encode()).hexdigest()[:10]
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", remote_name)[:100]
    return f"mcp_{prefix}_{safe}"


def _discovery_hash(name: str, description: str, input_schema: object, output_schema: object) -> str:
    return sha256(json.dumps(
        [name,description,input_schema,output_schema], sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
