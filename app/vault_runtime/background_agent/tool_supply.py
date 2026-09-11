from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from threading import Lock

from app.vault_runtime.background_agent.contracts import AutonomyProfile
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolInvocationContext, ToolInvocationResult


class ToolBudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BackgroundToolGrant:
    autonomy: AutonomyProfile
    explicit_names: frozenset[str]
    max_calls: int

    def __post_init__(self) -> None:
        if self.max_calls <= 0:
            raise ValueError("max_calls must be positive")


class BackgroundToolSupply:
    """One run's immutable intersection over the canonical tool catalog."""

    def __init__(
        self, *, catalog: ToolCatalog, grant: BackgroundToolGrant,
        user_id: str | None = None, workspace_id: str | None = None,
        activity: Callable[[str, dict[str, object]], None] | None = None,
    ) -> None:
        self._catalog = catalog
        self._grant = grant
        self._definitions = tuple(
            item for item in catalog.definitions_for(
                AgentKind.BACKGROUND, user_id=user_id, workspace_id=workspace_id,
            ) if self._allowed(item)
        )
        self._allowed_names = frozenset(item.name for item in self._definitions)
        self._calls = 0
        self._activity = activity or (lambda _event, _detail: None)
        self._lock = Lock()

    @property
    def calls_used(self) -> int:
        with self._lock:
            return self._calls

    def definitions(self) -> tuple[dict[str, object], ...]:
        return tuple(item.mcp_definition() for item in self._definitions)

    def invoke(
        self, name: object, arguments: object, *, context: ToolInvocationContext
    ) -> ToolInvocationResult:
        if context.agent is not AgentKind.BACKGROUND or not isinstance(name, str) or name not in self._allowed_names:
            return ToolInvocationResult("Tool is not granted to this Background Agent run.", is_error=True)
        with self._lock:
            if self._calls >= self._grant.max_calls:
                raise ToolBudgetExceeded("Background Agent tool-call limit reached")
            self._calls += 1
            call_number = self._calls
        self._activity("tool_started", {"name": name, "call": call_number})
        try:
            result = self._catalog.invoke(name, arguments, context=context)
        except Exception:
            self._activity("tool_failed", {"name": name, "call": call_number})
            raise
        self._activity(
            "tool_failed" if result.is_error else "tool_completed",
            {"name": name, "call": call_number, "isError": result.is_error},
        )
        return result

    def _allowed(self, definition) -> bool:
        if definition.name not in self._grant.explicit_names:
            return False
        if self._grant.autonomy is AutonomyProfile.LIMITED:
            return definition.effect_class == "read"
        if self._grant.autonomy is AutonomyProfile.EXPANDED:
            return definition.effect_class in {"read", "write"}
        return definition.effect_class != "delete"
