from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Queue
from threading import Event, Lock, Thread
from time import monotonic
from typing import Protocol

from app.vault_runtime.background_agent.contracts import (
    AutonomyProfile,
    BackgroundRunRequest,
    BackgroundRunState,
)
from app.vault_runtime.background_agent.repository import BackgroundRunRepository, StoredBackgroundRun
from app.vault_runtime.background_agent.tool_supply import BackgroundToolGrant, BackgroundToolSupply
from app.vault_runtime.background_agent.output_contract import BackgroundAgentOutput
from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolInvocationContext


class BackgroundExecutor(Protocol):
    def execute(
        self,
        request: BackgroundRunRequest,
        *,
        tools: BackgroundToolSupply,
        context: ToolInvocationContext,
        progress: "RunProgressRecorder",
    ) -> dict[str, object]: ...


@dataclass(slots=True)
class RunProgressRecorder:
    repository: BackgroundRunRepository
    user_id: str
    workspace_id: str
    local_session_id: str
    run_id: str
    max_model_turns: int
    model_turns: int = 0

    def model_turn(self, count: int = 1) -> None:
        if count <= 0 or self.model_turns + count > self.max_model_turns:
            raise RuntimeError("max_model_turns_exceeded")
        self.model_turns += count
        self.repository.record_activity(
            user_id=self.user_id, workspace_id=self.workspace_id,
            local_session_id=self.local_session_id, run_id=self.run_id,
            event_type="model_turns", detail={"count": count},
        )

    def cancellation_requested(self) -> bool:
        return self.repository.get(
            user_id=self.user_id, workspace_id=self.workspace_id,
            local_session_id=self.local_session_id, run_id=self.run_id,
        ).cancellation_requested

    def context_frozen(self, memory_references: tuple[str, ...]) -> None:
        self.repository.record_activity(
            user_id=self.user_id, workspace_id=self.workspace_id,
            local_session_id=self.local_session_id, run_id=self.run_id,
            event_type="context_frozen", detail={"memoryReferences": list(memory_references)},
        )


class BackgroundAgentService:
    """Durable execution service for the one fixed Background Agent."""

    def __init__(
        self, *, repository: BackgroundRunRepository, catalog: ToolCatalog,
        executor: BackgroundExecutor, worker_count: int = 4,
    ) -> None:
        self._repository = repository
        self._catalog = catalog
        self._executor = executor
        self._queue: Queue[tuple[str, str, str, str]] = Queue()
        self._stop = Event()
        if not 1 <= worker_count <= 4:
            raise ValueError("Background worker count must be between one and four.")
        self._worker_count = worker_count
        self._workers: list[Thread] = []
        self._worker_lock = Lock()

    def start(self) -> None:
        with self._worker_lock:
            if any(worker.is_alive() for worker in self._workers):
                return
            self._repository.recover_interrupted()
            self._stop.clear()
            self._workers = [Thread(
                target=self._work_loop, name=f"vault-background-agent-{number + 1}", daemon=True
            ) for number in range(self._worker_count)]
            for worker in self._workers:
                worker.start()

    def stop(self, *, timeout: float = 5.0) -> None:
        with self._worker_lock:
            workers = tuple(self._workers)
            self._stop.set()
        for worker in workers:
            worker.join(timeout=max(0.1, timeout))
        with self._worker_lock:
            self._workers = []

    def submit(
        self, *, user_id: str, workspace_id: str, local_session_id: str,
        request: BackgroundRunRequest,
    ) -> StoredBackgroundRun:
        self._repository.create(
            user_id=user_id, workspace_id=workspace_id,
            local_session_id=local_session_id, request=request,
        )
        queued = self._repository.transition(
            user_id=user_id, workspace_id=workspace_id,
            local_session_id=local_session_id, run_id=request.run_id,
            target=BackgroundRunState.QUEUED, event_type="queued",
        )
        with self._worker_lock:
            worker_active = any(worker.is_alive() for worker in self._workers)
        if worker_active:
            self._queue.put((user_id, workspace_id, local_session_id, request.run_id))
        return queued

    def execute_queued(
        self, *, user_id: str, workspace_id: str, local_session_id: str, run_id: str
    ) -> StoredBackgroundRun:
        current = self._repository.get(
            user_id=user_id, workspace_id=workspace_id,
            local_session_id=local_session_id, run_id=run_id,
        )
        if current.state is not BackgroundRunState.QUEUED:
            return current
        if current.cancellation_requested:
            return self._repository.transition(
                user_id=user_id, workspace_id=workspace_id,
                local_session_id=local_session_id, run_id=run_id,
                target=BackgroundRunState.CANCELLED, event_type="cancelled",
            )
        running = self._repository.transition(
            user_id=user_id, workspace_id=workspace_id,
            local_session_id=local_session_id, run_id=run_id,
            target=BackgroundRunState.RUNNING, event_type="started",
        )
        progress = RunProgressRecorder(
            repository=self._repository, user_id=user_id, workspace_id=workspace_id,
            local_session_id=local_session_id, run_id=run_id,
            max_model_turns=running.request.limits.max_model_turns,
        )
        context = ToolInvocationContext(
            agent=AgentKind.BACKGROUND, user_id=user_id, workspace_id=workspace_id,
            tool_call_id=f"{run_id}:executor", local_session_id=local_session_id,
            execution_id=run_id,
        )

        def activity(event_type: str, detail: dict[str, object]) -> None:
            self._repository.record_activity(
                user_id=user_id, workspace_id=workspace_id,
                local_session_id=local_session_id, run_id=run_id,
                event_type=event_type, detail=detail,
            )

        supply = BackgroundToolSupply(
            catalog=self._catalog,
            user_id=user_id, workspace_id=workspace_id,
            grant=BackgroundToolGrant(
                autonomy=running.request.autonomy,
                explicit_names=frozenset(running.request.requested_tool_names),
                max_calls=running.request.limits.max_tool_calls,
            ),
            activity=activity,
        )
        started = monotonic()
        try:
            output = self._executor.execute(
                running.request, tools=supply, context=context, progress=progress
            )
            if progress.cancellation_requested():
                return self._repository.transition(
                    user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id, run_id=run_id,
                    target=BackgroundRunState.CANCELLED, event_type="cancelled",
                )
            if monotonic() - started > running.request.limits.max_seconds:
                raise RuntimeError("run_timeout")
            typed = BackgroundAgentOutput.model_validate(output)
        except Exception as exc:
            code = str(exc) if str(exc) in {
                "max_model_turns_exceeded", "run_timeout"
            } else type(exc).__name__.lower()
            return self._repository.transition(
                user_id=user_id, workspace_id=workspace_id,
                local_session_id=local_session_id, run_id=run_id,
                target=BackgroundRunState.FAILED, event_type="execution_failed",
                failure_code=code[:120], failure_message=str(exc)[:2048],
            )
        value = typed.model_dump(mode="json")
        for evidence in typed.phase_evidence:
            self._repository.record_activity(
                user_id=user_id, workspace_id=workspace_id,
                local_session_id=local_session_id, run_id=run_id,
                event_type="agent_evidence",
                detail={"phase": evidence.phase, "summary": evidence.summary},
            )
        if typed.status == "complete":
            return self._repository.transition(
                user_id=user_id, workspace_id=workspace_id,
                local_session_id=local_session_id, run_id=run_id,
                target=BackgroundRunState.COMPLETED, event_type="completed", output=value,
            )
        message = typed.summary if typed.status == "blocked" else (
            typed.unresolved_issues[0] if typed.unresolved_issues else typed.summary
        )
        return self._repository.transition(
            user_id=user_id, workspace_id=workspace_id,
            local_session_id=local_session_id, run_id=run_id,
            target=BackgroundRunState.FAILED, event_type="agent_incomplete", output=value,
            failure_code="agent_incomplete", failure_message=message[:1024],
        )

    def _work_loop(self) -> None:
        while not self._stop.is_set():
            try:
                user_id, workspace_id, local_session_id, run_id = self._queue.get(timeout=0.1)
            except Empty:
                continue
            try:
                self.execute_queued(
                    user_id=user_id, workspace_id=workspace_id,
                    local_session_id=local_session_id, run_id=run_id,
                )
            except Exception:
                # The repository/service records normal execution failures.
                # Authority loss or database failure leaves durable state for
                # startup recovery rather than killing the fixed worker.
                pass
            finally:
                self._queue.task_done()
