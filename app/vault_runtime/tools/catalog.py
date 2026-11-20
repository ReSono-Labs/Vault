from __future__ import annotations

import json

from collections.abc import Callable
from threading import RLock

from jsonschema import Draft202012Validator

from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.argument_aliases import normalize_tool_arguments
from app.vault_runtime.tools.definitions import ToolDefinition, ToolInvocationContext, ToolInvocationResult
from app.vault_runtime.workspace_files.errors import WorkspaceFileError

InvocationAuthorizer = Callable[[ToolDefinition, ToolInvocationContext], bool]
BackgroundInvocationAuthorizer = Callable[[ToolDefinition, ToolInvocationContext, dict[str, object]], bool]
InvocationObserver = Callable[
    [ToolInvocationContext, str, dict[str, object], ToolInvocationResult], None
]


class ToolCatalog:
    """Single donor-derived authority for schema, audience and dispatch."""

    def __init__(self, *, authorizer: InvocationAuthorizer,
                 background_authorizer: BackgroundInvocationAuthorizer | None = None) -> None:
        self._by_name: dict[str, ToolDefinition] = {}
        self._by_id: dict[str, ToolDefinition] = {}
        self._source_tool_ids: dict[str, set[str]] = {}
        self._authorizer = authorizer
        self._background_authorizer = background_authorizer
        # Owner approvals: set once at composition; gated interactive calls stop here.
        self._approval_gate = None
        self._observer: InvocationObserver | None = None
        self._lock = RLock()

    def set_approval_gate(self, gate) -> None:
        """The system's approve/deny stop for every interactive agent path (Chat and Voice)."""
        with self._lock:
            self._approval_gate = gate

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

    def definition(self, name: str) -> ToolDefinition | None:
        """One registered definition by name (no audience or grant check)."""
        with self._lock:
            return self._by_name.get(name) if isinstance(name, str) else None

    def definitions_for(
        self, agent: AgentKind, *, user_id: str | None = None,
        workspace_id: str | None = None, conversation: bool = False,
    ) -> tuple[ToolDefinition, ...]:
        with self._lock:
            return tuple(
                definition for definition in self._by_name.values()
                if agent in definition.audiences
                and (conversation or not definition.conversation_only)
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
        approval_wait=None,
    ) -> ToolInvocationResult:
        with self._lock:
            definition = self._by_name.get(name) if isinstance(name, str) else None
            observer = self._observer
            gate = self._approval_gate
        if (
            definition is None or context.agent not in definition.audiences
            or (definition.conversation_only and context.conversation_id is None)
            or not definition.visible_in(user_id=context.user_id, workspace_id=context.workspace_id)
        ):
            return ToolInvocationResult("Tool is not granted.", is_error=True)
        background = context.background_scope is not None
        if (background and self._background_authorizer is None) or (not background and not self._authorizer(definition, context)):
            return ToolInvocationResult("Tool is not granted in the current local scope.", is_error=True)
        arguments = normalize_tool_arguments(
            name, arguments, schema_fields=((definition.input_schema or {}).get("properties") or {}).keys(),
        )
        if not isinstance(arguments, dict):
            return ToolInvocationResult("Tool arguments are invalid: they must be a JSON object.", is_error=True)
        problem = _schema_problem(arguments, definition.input_schema)
        if problem is not None:
            # Say what to fix (never the values), so the agent can correct the call.
            return ToolInvocationResult(f"Tool arguments are invalid: {problem}.", is_error=True)
        if background and not self._background_authorizer(definition, context, arguments):
            return ToolInvocationResult("Tool/resource is not granted to this background work.", is_error=True)
        approval_id = None
        if gate is not None and gate.applies(context, name, arguments):
            from app.vault_runtime.conversation_tools.approval_gate import ApprovalWait
            approval_id, refusal = gate.hold(context, name, arguments, approval_wait or ApprovalWait())
            if refusal is not None:
                return ToolInvocationResult(refusal, is_error=True)
            if "approve" in ((definition.input_schema or {}).get("properties") or {}):
                arguments = {**arguments, "approve": True}   # the owner's tap, never the model's flag
        try:
            result = definition.handler(context, arguments)
        except (WorkspaceFileError, ValueError) as exc:
            # Expected tool errors (missing path, bad arguments, access refused) go back to the
            # agent as a tool result, so it can read the message and try something else.
            # Anything else still fails the call.
            result = ToolInvocationResult(
                json.dumps({"error": str(exc) or "The tool call failed.",
                            "code": getattr(exc, "code", "invalid_request")}, separators=(",", ":")),
                is_error=True,
            )
        except BaseException:
            if approval_id is not None:
                gate.finish(context, approval_id, {"state": "unknown"})   # it may or may not have happened
            raise
        if approval_id is not None:
            gate.finish(context, approval_id, {"state": "failed" if result.is_error else "completed"})
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
    return _schema_problem(arguments, schema) is None


def _schema_problem(arguments: dict[str, object], schema: dict[str, object]) -> str | None:
    """What is wrong with the arguments, in a few words naming fields only (no values), or None."""
    try:
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(arguments), key=lambda e: (len(e.path), str(e.validator)))
    except Exception:
        return "they do not match the tool's parameters"
    if not errors:
        return None
    problems = []
    for error in errors[:3]:
        where = ".".join(str(part) for part in error.path) or "arguments"
        kind, expected = str(error.validator), error.validator_value
        if kind == "required":
            have = error.instance if isinstance(error.instance, dict) else {}
            missing = [str(name) for name in (expected or []) if name not in have]
            problems.append(f"missing required field {', '.join(missing)}" + ("" if where == "arguments" else f" in {where}"))
        elif kind == "additionalProperties":
            allowed = set((error.schema.get("properties") or {}).keys()) if isinstance(error.schema, dict) else set()
            extra = sorted(str(k) for k in (error.instance or {}) if k not in allowed) if isinstance(error.instance, dict) else []
            problems.append(f"unknown field {', '.join(extra[:5])}" + ("" if where == "arguments" else f" in {where}"))
        elif kind == "type":
            problems.append(f"{where} must be {expected if isinstance(expected, str) else ' or '.join(map(str, expected))}")
        elif kind == "enum":
            problems.append(f"{where} must be one of {', '.join(map(str, list(expected)[:8]))}")
        elif kind in {"minLength", "maxLength", "minItems", "maxItems", "minimum", "maximum"}:
            problems.append(f"{where} breaks {kind} {expected}")
        else:
            problems.append(f"{where} fails the {kind} rule")
    return "; ".join(problems)[:400]
