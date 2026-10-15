from __future__ import annotations

from collections.abc import Callable
from threading import RLock

from jsonschema import Draft202012Validator

from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.argument_aliases import normalize_tool_arguments
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult

InvocationAuthorizer = Callable[[ToolDefinition, ToolInvocationContext], bool]
InvocationObserver = Callable[
    [ToolInvocationContext, str, dict[str, object], ToolInvocationResult], None
]


class ToolCatalog:
    """Single donor-derived authority for schema, audience and dispatch."""

    def __init__(self, *, authorizer: InvocationAuthorizer) -> None:
        self._by_name: dict[str, ToolDefinition] = {}
        self._by_id: dict[str, ToolDefinition] = {}
        self._source_tool_ids: dict[str, set[str]] = {}
        self._authorizer = authorizer
        self._observer: InvocationObserver | None = None
        self._lock = RLock()

    def set_invocation_observer(self, observer: InvocationObserver | None) -> None:
        with self._lock:
            self._observer = observer

    def register(self, definition: ToolDefinition) -> None:
        _validate_schema(definition.input_schema)
        with self._lock:
            if definition.name in self._by_name or definition.tool_id in self._by_id:
                raise ValueError("tool identity collision")
            self._by_name[definition.name] = definition
            self._by_id[definition.tool_id] = definition

    def replace_capability_source(
        self, source_id: str, definitions: tuple[ToolDefinition, ...]
    ) -> None:
        """Phase 5 hook: changes capabilities, never system-agent identity."""
        if not source_id.strip():
            raise ValueError("source_id is required")
        for definition in definitions:
            _validate_schema(definition.input_schema)
        with self._lock:
            prior_ids = self._source_tool_ids.get(source_id, set())
            prior_names = {self._by_id[tool_id].name for tool_id in prior_ids}
            names = [definition.name for definition in definitions]
            ids = [definition.tool_id for definition in definitions]
            if len(names) != len(set(names)) or len(ids) != len(set(ids)):
                raise ValueError("dynamic tool identity collision")
            if any(name in self._by_name and name not in prior_names for name in names):
                raise ValueError("tool name collision")
            if any(tool_id in self._by_id and tool_id not in prior_ids for tool_id in ids):
                raise ValueError("tool id collision")
            self._remove_source_locked(source_id)
            for definition in definitions:
                self._by_name[definition.name] = definition
                self._by_id[definition.tool_id] = definition
            self._source_tool_ids[source_id] = set(ids)

    def remove_capability_source(self, source_id: str) -> None:
        with self._lock:
            self._remove_source_locked(source_id)

    def definitions_for(
        self, agent: AgentKind, *, user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> tuple[ToolDefinition, ...]:
        with self._lock:
            return tuple(
                definition for definition in self._by_name.values()
                if agent in definition.audiences
                and definition.visible_in(user_id=user_id, workspace_id=workspace_id)
            )

    def metadata_for(self, agent: AgentKind, *, user_id: str, workspace_id: str) -> tuple[ToolDefinition, ...]:
        """Scoped metadata for invalidation only, NOT available/executable tools.

        Availability must still be checked before proposing or invoking a tool.
        Avoid invoking every availability provider merely to detect catalog edits.
        """
        with self._lock:
            return tuple(d for d in self._by_name.values() if agent in d.audiences and
                (d.scope_user_id is None or (d.scope_user_id==user_id and d.scope_workspace_id==workspace_id)))

    def realtime_definitions(
        self, *, user_id: str | None = None, workspace_id: str | None = None,
    ) -> tuple[dict[str, object], ...]:
        return tuple(item.realtime_definition() for item in self.definitions_for(
            AgentKind.VOICE, user_id=user_id, workspace_id=workspace_id,
        ))

    def invoke(
        self,
        name: object,
        arguments: object,
        *,
        context: ToolInvocationContext,
    ) -> ToolInvocationResult:
        with self._lock:
            definition = self._by_name.get(name) if isinstance(name, str) else None
            observer = self._observer
        if (
            definition is None or context.agent not in definition.audiences
            or not definition.visible_in(user_id=context.user_id, workspace_id=context.workspace_id)
        ):
            return ToolInvocationResult("Tool is not granted.", is_error=True)
        if not self._authorizer(definition, context):
            return ToolInvocationResult("Tool is not granted in the current local scope.", is_error=True)
        arguments = normalize_tool_arguments(name, arguments)
        if not isinstance(arguments, dict) or not _matches_schema(arguments, definition.input_schema):
            return ToolInvocationResult("Tool arguments are invalid.", is_error=True)
        result = definition.handler(context, arguments)
        if observer is not None:
            try:
                observer(context, definition.name, arguments, result)
            except Exception:
                pass
        return result

    def _remove_source_locked(self, source_id: str) -> None:
        for tool_id in self._source_tool_ids.pop(source_id, set()):
            definition = self._by_id.pop(tool_id, None)
            if definition is not None:
                self._by_name.pop(definition.name, None)


def _validate_schema(schema: dict[str, object]) -> None:
    Draft202012Validator.check_schema(schema)


def _matches_schema(arguments: dict[str, object], schema: dict[str, object]) -> bool:
    try:
        Draft202012Validator(schema).validate(arguments)
    except Exception:
        return False
    return True
