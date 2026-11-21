"""Donor-derived background coordinator, scratchpad ledger, and private helper dispatch (Task 6).

Adapted from Rakazo (`elie222/rakazo` @ `83db73c2e5fe5002487f4dc1cf488fe601a34c25`, Apache-2.0):
- `packages/agent/src/tools/scratchpad-tools.ts`: open/parked/done work ledger buckets and bounded
  scratchpad context assembly (`build_scratchpad_context`).
- `packages/agent/src/background-helpers.ts` & `packages/agent/src/background-helpers.prompt.ts`:
  private helper assignment, isolated specialist session context, helper prompt rules prohibiting
  recursive helper spawning / self-grant widening / owner impersonation, result provenance tagging,
  and one-result deduplication.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from typing import Any

import logging

from psycopg.types.json import Jsonb

from app.vault_runtime.system_agents.inventory import AgentKind
from app.vault_runtime.tools.catalog import ToolCatalog
from app.vault_runtime.tools.definitions import ToolInvocationContext

from .authority import BackgroundAuthority
from .contracts import AutonomyProfile, BackgroundRunRequest, ExecutionRecipe, RunLimits
from .coordination_contracts import (
    ApprovalDecision,
    ExecutionOutcome,
    OwnerScope,
    WorkerSpec,
    WorkRequest,
    WorkScope,
    WorkState,
)
from .coordination_repository import CoordinationRepository, _json
from .jobs import BackgroundJobs, JobAttempt
from .errors import BackgroundRunAuthorizationError, BackgroundRunConflictError
from .results import BackgroundResults
from .tool_supply import BackgroundToolGrant, BackgroundToolSupply
from .worker_repository import WorkerRepository

logger = logging.getLogger(__name__)

MAX_SCRATCHPAD_ITEMS = 12
MAX_SCRATCHPAD_CHARS = 4000
MAX_WORKER_HISTORY_ENTRIES = 20

FORBIDDEN_HELPER_TOOLS: frozenset[str] = frozenset({
    "goal_start",
    "goal_inspect",
    "goal_cancel",
    "coordinator_hand_off",
    "coordinator_status",
    "voice_mode_switch",
    "worker_create",
    "worker_propose",
    "grant_create",
    "grant_approve",
})

_OPEN_STATES = frozenset({"proposed", "ready", "queued", "running"})
_PARKED_STATES = frozenset({"waiting_approval", "waiting_input", "waiting_event"})
_DONE_STATES = frozenset({"completed", "failed", "cancelled", "unknown"})


@dataclass(frozen=True, slots=True)
class CoordinatorObservationDecision:
    action: str  # "none" | "create_work" | "propose_worker"
    reason: str
    work_request: WorkRequest | None = None
    worker_spec: WorkerSpec | None = None
    role_key: str | None = None

    def __post_init__(self) -> None:
        if self.action not in {"none", "create_work", "propose_worker"}:
            raise ValueError("Unsupported coordinator observation action")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("Observation decision reason is required")
        if self.action == "propose_worker" and self.worker_spec is None:
            raise ValueError("propose_worker requires a WorkerSpec")
        if self.action == "create_work" and self.work_request is None:
            raise ValueError("create_work requires a WorkRequest")


def _clip(text: str, limit: int = 240) -> str:
    compact = " ".join(str(text or "").split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def build_scratchpad_context(items: list[dict[str, object]]) -> dict[str, object]:
    """Ported from Rakazo `scratchpad-tools.ts`: categorize open/parked/done work within strict bounds."""
    normalized: list[dict[str, object]] = []
    lines: list[str] = []
    for raw in items[:MAX_SCRATCHPAD_ITEMS]:
        if not isinstance(raw, dict):
            continue
        state = str(raw.get("state") or "proposed")
        if state in _OPEN_STATES:
            bucket = "open"
        elif state in _PARKED_STATES:
            bucket = "parked"
        else:
            bucket = "done"
        entry = {
            "work_id": str(raw.get("work_id") or ""),
            "bucket": bucket,
            "state": state,
            "role_key": str(raw.get("role_key") or "") or None,
            "objective": _clip(str(raw.get("objective") or ""), 240),
            "summary": _clip(str(raw.get("summary") or ""), 200),
        }
        line = (
            f"[{bucket.upper()}:{entry['state']}] work={entry['work_id']}"
            + (f" role={entry['role_key']}" if entry["role_key"] else "")
            + f" objective={entry['objective']}"
            + (f" summary={entry['summary']}" if entry["summary"] else "")
        )
        candidate_rendered = "\n".join(lines + [line])
        if len(candidate_rendered) > MAX_SCRATCHPAD_CHARS:
            break
        normalized.append(entry)
        lines.append(line)
    return {
        "items": normalized,
        "rendered": "\n".join(lines)[:MAX_SCRATCHPAD_CHARS],
    }


def filter_helper_tool_names(
    *,
    requested_tools: tuple[str, ...],
    worker_spec: WorkerSpec | None = None,
) -> tuple[str, ...]:
    """Intersect requested tools with worker spec and remove recursive spawning / privilege-widening tools."""
    allowed_set = set(requested_tools) - FORBIDDEN_HELPER_TOOLS
    if worker_spec is not None:
        allowed_set &= set(worker_spec.tool_names)
    return tuple(name for name in requested_tools if name in allowed_set)


def build_helper_instructions(
    spec: WorkerSpec,
    scope: WorkScope,
    *,
    brief: dict[str, object],
    prior_session_history: list[dict[str, object]] | None = None,
) -> str:
    """Ported from Rakazo `background-helpers.prompt.ts`: private specialist prompt with strict boundaries."""
    history_lines: list[str] = []
    for entry in (prior_session_history or [])[-MAX_WORKER_HISTORY_ENTRIES:]:
        if not isinstance(entry, dict):
            continue
        w_id = _clip(str(entry.get("work_id") or ""), 64)
        obj = _clip(str(entry.get("objective") or ""), 200)
        summ = _clip(str(entry.get("summary") or ""), 240)
        history_lines.append(f"- Prior assignment {w_id}: {obj} -> {summ}")
    history_block = (
        "\nSpecialist session memory (isolated to this specialist generation):\n" + "\n".join(history_lines)
        if history_lines
        else ""
    )
    criteria = ", ".join(str(c) for c in (brief.get("success_criteria") or ()))
    return (
        f"You are private background specialist '{spec.role_key}' (worker_id={scope.worker_id}, "
        f"generation={scope.worker_generation}) executing parent assignment {scope.work_id} "
        f"(intent_version={scope.intent_version}).\n"
        f"Purpose: {spec.purpose}\n"
        f"Role instructions: {spec.instructions}\n"
        "Review the supplied Vault memory before starting. Use memory_lookup, when granted, "
        "to fill context gaps about this assignment with focused searches.\n"
        "Mandatory safety boundaries:\n"
        "1. Never spawn or delegate to other helpers, background goals, or sub-agents.\n"
        "2. Never widen your execution grants, tool scopes, or resource policies.\n"
        "3. Never speak as the owner or claim owner approval; your output and tool findings are evidence only.\n"
        "4. Return exactly one structured result for this assignment; reference shared artifacts by ID without "
        "writing private reasoning into permanent user memory.\n"
        f"Permitted brief objective: {brief.get('objective', '')}\n"
        f"Success criteria: {criteria}"
        f"{history_block}"
    )


def sanitize_helper_result(
    scope: WorkScope,
    run_id: str,
    output: dict[str, object] | None,
) -> dict[str, object]:
    """Ported from Rakazo `background-helpers.ts`: attach untrusted helper provenance and strip false approvals."""
    raw = dict(output) if isinstance(output, dict) else {}
    for forbidden_key in (
        "approve",
        "decision_id",
        "action_hash",
        "private_session_history",
        "private_transcript",
        "checkpoint_json",
    ):
        raw.pop(forbidden_key, None)
    if "approved" in raw:
        raw["approved"] = False
    if "owner_approved" in raw:
        raw["owner_approved"] = False
    raw["provenance"] = {
        "kind": "helper_result",
        "trust": "evidence_only",
        "owner_instruction": False,
        "owner_approved": False,
        "work_id": scope.work_id,
        "intent_version": scope.intent_version,
        "worker_id": scope.worker_id,
        "worker_generation": scope.worker_generation,
        "run_id": run_id,
    }
    return _json(raw)


class BackgroundCoordinator:
    def __init__(
        self,
        *,
        database_url: str,
        executor: Any,
        catalog: ToolCatalog,
        results: BackgroundResults | None = None,
        triage_evaluator: Callable[
            [OwnerScope, str, str, dict[str, object], dict[str, object]],
            CoordinatorObservationDecision | None,
        ]
        | None = None,
        auto_dispatch: bool = False,
    ) -> None:
        self._database_url = database_url
        self._repo = CoordinationRepository(database_url=database_url)
        self._authority = BackgroundAuthority(database_url=database_url)
        self._workers = WorkerRepository(database_url=database_url)
        self._executor = executor
        self._catalog = catalog
        self._results = results or BackgroundResults(database_url=database_url)
        self._triage_evaluator = triage_evaluator
        self._auto_dispatch = auto_dispatch
        self.jobs = BackgroundJobs(database_url=database_url, executor=self.execute_attempt,
                                   record_outcome=self.record_outcome, deliver_outcome=self.deliver_outcome,
                                   resume_assignments=self.resume_specialist_assignments)
        from .executor import ResumableBackgroundExecutor
        if isinstance(executor, ResumableBackgroundExecutor):
            executor.attach_jobs(self.jobs)

    def is_observation_enabled(self, scope: OwnerScope) -> bool:
        return bool(self._repo.get_preferences(scope).get("enabled", False))

    def set_observation_enabled(self, scope: OwnerScope, enabled: bool) -> dict[str, object]:
        return self._repo.set_preferences(scope, enabled=enabled)

    def resolve_work_scope(self, work_id: str) -> WorkScope:
        return self._repo.resolve_work_scope(work_id)

    def get_coordinator_view(self, scope: OwnerScope, work_id: str) -> dict[str, object]:
        """Coordinator sees only the permitted brief and terminal sanitized result, never private session history."""
        row = self._repo.get(scope, work_id)
        req_payload = (row["request_json"] or {}).get("request") or {}
        dest_payload = (row["request_json"] or {}).get("destination") or {}
        result_payload = row["result_json"] if isinstance(row["result_json"], dict) else None
        sanitized_result = None
        if result_payload is not None:
            sanitized_result = {
                "status": result_payload.get("status"),
                "summary": result_payload.get("summary"),
                "artifact_references": list(result_payload.get("artifact_references") or []),
                "verification_summary": result_payload.get("verification_summary"),
                "provenance": result_payload.get("provenance"),
            }
        return {
            "work_id": row["work_id"],
            "state": row["state"],
            "intent_version": row["intent_version"],
            "worker_id": row["worker_id"],
            "worker_generation": row["worker_generation"],
            "role_key": dest_payload.get("role_key"),
            "brief": {
                "objective": req_payload.get("objective"),
                "success_criteria": list(req_payload.get("success_criteria") or []),
                "expected_result": req_payload.get("expected_result"),
                "context_summary": req_payload.get("context_summary"),
            },
            "result": sanitized_result,
        }

    @staticmethod
    def _serialize_worker_spec(spec: WorkerSpec | dict[str, object] | None) -> dict[str, object] | None:
        if spec is None:
            return None
        if isinstance(spec, WorkerSpec):
            return _json(asdict(spec))
        if isinstance(spec, dict):
            return _json(spec)
        raise ValueError("Invalid worker_spec")

    @staticmethod
    def _deserialize_worker_spec(data: WorkerSpec | dict[str, object] | None) -> WorkerSpec | None:
        if data is None:
            return None
        if isinstance(data, WorkerSpec):
            return data
        if isinstance(data, dict):
            limits_raw = data.get("limits")
            limits = RunLimits(**limits_raw) if isinstance(limits_raw, dict) else RunLimits()
            return WorkerSpec(
                role_key=str(data["role_key"]),
                purpose=str(data["purpose"]),
                instructions=str(data["instructions"]),
                tool_names=tuple(str(t) for t in data.get("tool_names", ())),
                resource_policy=dict(data.get("resource_policy") or {}),
                limits=limits,
            )
        raise ValueError("Invalid worker_spec payload")

    @staticmethod
    def _deserialize_work_request(data: WorkRequest | dict[str, object]) -> WorkRequest:
        if isinstance(data, WorkRequest):
            return data
        if not isinstance(data, dict):
            raise ValueError("Expected WorkRequest or dict")
        req_raw = data["request"]
        if isinstance(req_raw, BackgroundRunRequest):
            req = req_raw
        else:
            limits_raw = req_raw.get("limits")
            limits = RunLimits(**limits_raw) if isinstance(limits_raw, dict) else RunLimits()
            req = BackgroundRunRequest(
                run_id=str(req_raw["run_id"]),
                objective=str(req_raw["objective"]),
                instruction_profile=str(req_raw["instruction_profile"]),
                success_criteria=tuple(str(x) for x in req_raw["success_criteria"]),
                result_schema=dict(req_raw["result_schema"]),
                recipe=ExecutionRecipe(req_raw.get("recipe", ExecutionRecipe.SELF_REVIEW)),
                autonomy=AutonomyProfile(req_raw.get("autonomy", AutonomyProfile.LIMITED)),
                limits=limits,
                goal_type=str(req_raw.get("goal_type", "general")),
                context_summary=str(req_raw.get("context_summary", "")),
                expected_result=str(req_raw.get("expected_result", "")),
                scope=str(req_raw.get("scope", "")),
                exclusions=tuple(str(x) for x in req_raw.get("exclusions", ())),
                source_requirements=str(req_raw.get("source_requirements", "")),
                workspace_destination=req_raw.get("workspace_destination"),
                original_request=str(req_raw["original_request"]),
                verification_method=str(req_raw["verification_method"]),
                completion_conditions=tuple(str(x) for x in req_raw["completion_conditions"]),
                stop_conditions=tuple(str(x) for x in req_raw.get("stop_conditions", ())),
                requested_tool_names=tuple(str(x) for x in req_raw.get("requested_tool_names", ())),
            )
        dest = dict(data.get("destination") or {})
        if isinstance(dest.get("worker_spec"), WorkerSpec):
            dest["worker_spec"] = _json(asdict(dest["worker_spec"]))
        return WorkRequest(
            request=req,
            grant_id=data.get("grant_id"),
            local_session_id=data.get("local_session_id"),
            destination=dest,
        )

    def _find_approved_worker(self, scope: OwnerScope, role_key: str) -> tuple[str, int] | None:
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            cursor.execute(
                """SELECT worker_id, generation FROM vault_private.vault_background_workers
                   WHERE user_id=%s AND workspace_id=%s AND role_key=%s AND status IN ('idle', 'active')""",
                (scope.user_id, scope.workspace_id, role_key),
            )
            row = cursor.fetchone()
            if row:
                return (str(row["worker_id"]), int(row["generation"]))
            cursor.execute(
                """SELECT action_id, action_hash, actor_user_id, workspace_id, channel, channel_generation, decision_id
                   FROM vault_private.vault_background_actions
                   WHERE user_id=%s AND workspace_id=%s AND kind='worker_create' AND state='approved'
                     AND arguments_json->>'role_key'=%s
                   ORDER BY updated_at DESC LIMIT 1""",
                (scope.user_id, scope.workspace_id, role_key),
            )
            approved_action = cursor.fetchone()
        if approved_action is not None:
            decision = ApprovalDecision(
                action_id=approved_action["action_id"],
                action_hash=approved_action["action_hash"],
                choice="allow_once",
                actor_user_id=approved_action["actor_user_id"],
                workspace_id=approved_action["workspace_id"],
                channel=approved_action["channel"],
                channel_generation=approved_action["channel_generation"],
                decision_id=approved_action["decision_id"],
            )
            worker_id = self._workers.create_from_approval(decision)
            with self._repo._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """SELECT worker_id, generation FROM vault_private.vault_background_workers
                       WHERE user_id=%s AND workspace_id=%s AND worker_id=%s AND status IN ('idle', 'active')""",
                    (scope.user_id, scope.workspace_id, worker_id),
                )
                created = cursor.fetchone()
                if created:
                    return (str(created["worker_id"]), int(created["generation"]))
        return None

    def observe(self, scope: OwnerScope, source_kind: str, source_id: str, payload: dict[str, object]) -> str:
        if not isinstance(payload, dict) or not source_kind or not source_id:
            raise ValueError("Observation requires OwnerScope, source_kind, source_id, and payload dict")
        explicit = bool(payload.get("explicit")) or source_kind in {"explicit_goal", "goal_start", "explicit", "routine"}
        if not explicit and not self.is_observation_enabled(scope):
            return ""

        source_key = f"{source_kind}:{source_id}"
        # Check if work for this source_key already exists (idempotent replay without re-running triage)
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            cursor.execute(
                """SELECT work_id FROM vault_private.vault_background_work
                   WHERE user_id=%s AND workspace_id=%s AND source_key=%s""",
                (scope.user_id, scope.workspace_id, source_key),
            )
            existing_work = cursor.fetchone()
            if existing_work is not None:
                return str(existing_work["work_id"])

        decision: CoordinatorObservationDecision | None = None
        raw_decision = payload.get("decision")
        if isinstance(raw_decision, CoordinatorObservationDecision):
            decision = raw_decision
        elif isinstance(payload.get("work_request"), (WorkRequest, dict)):
            work_req = self._deserialize_work_request(payload["work_request"])
            worker_spec = self._deserialize_worker_spec(
                payload.get("worker_spec") or work_req.destination.get("worker_spec")
            )
            role_key = str(payload.get("role_key") or work_req.destination.get("role_key") or "") or (
                worker_spec.role_key if worker_spec else None
            )
            action = "propose_worker" if (worker_spec is not None and role_key and not self._find_approved_worker(scope, role_key)) else "create_work"
            decision = CoordinatorObservationDecision(
                action=action,
                reason=str(payload.get("reason") or "Structured work request"),
                work_request=work_req,
                worker_spec=worker_spec,
                role_key=role_key,
            )
        elif self._triage_evaluator is not None:
            scratchpad = build_scratchpad_context(self._repo.list_scratchpad_items(scope))
            sanitized_event_payload = {
                k: v for k, v in payload.items()
                if k not in {"decision", "work_request", "worker_spec"}
            }
            decision = self._triage_evaluator(scope, source_kind, source_id, sanitized_event_payload, scratchpad)

        event_payload = _json({
            k: v for k, v in payload.items()
            if k not in {"decision", "work_request", "worker_spec"}
        })
        event_id = self._repo.observe(scope, source_kind, source_id, event_payload)

        if decision is None or decision.action == "none":
            return event_id

        worker_spec = decision.worker_spec
        role_key = decision.role_key or (worker_spec.role_key if worker_spec else None)
        work_req = decision.work_request
        origin_conversation_id = str(payload.get("conversation_id") or "") or None
        origin_turn_id = str(payload.get("turn_id") or "") or None
        origin_voice_session_id = str(payload.get("voice_session_id") or "") or None
        if work_req is not None:
            dest = dict(work_req.destination)
            if not origin_conversation_id and dest.get("conversation_id"):
                origin_conversation_id = str(dest["conversation_id"])
            if not origin_turn_id and dest.get("turn_id"):
                origin_turn_id = str(dest["turn_id"])
            if not origin_voice_session_id and dest.get("voice_session_id"):
                origin_voice_session_id = str(dest["voice_session_id"])
            if role_key:
                dest["role_key"] = role_key
            if worker_spec is not None:
                dest["worker_spec"] = self._serialize_worker_spec(worker_spec)
            work_req = WorkRequest(
                request=work_req.request,
                grant_id=work_req.grant_id,
                local_session_id=work_req.local_session_id,
                destination=dest,
            )
            work_id = self._repo.create_work(scope, work_req, source_key=source_key)
            if role_key and self._find_approved_worker(scope, role_key) is None and worker_spec is not None:
                prepared = self._workers.propose(
                    scope,
                    worker_spec,
                    origin_conversation_id=origin_conversation_id,
                    origin_turn_id=origin_turn_id,
                    origin_voice_session_id=origin_voice_session_id,
                )
                work_scope = self.resolve_work_scope(work_id)
                self._repo.transition(
                    work_scope,
                    WorkState.PROPOSED,
                    WorkState.WAITING_APPROVAL,
                    {"pending_action_id": prepared.action_id, "role_key": worker_spec.role_key},
                )
            elif self._auto_dispatch:
                self.plan_dispatch(work_id)
            return work_id

        if worker_spec is not None:
            prepared = self._workers.propose(
                scope,
                worker_spec,
                origin_conversation_id=origin_conversation_id,
                origin_turn_id=origin_turn_id,
                origin_voice_session_id=origin_voice_session_id,
            )
            return prepared.action_id
        return event_id

    def resume_specialist_assignments(self) -> int:
        """Recover approved specialist assignments using their original approval receipt."""
        with self._repo._connect() as connection, connection.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT w.work_id
                FROM vault_private.vault_background_work w
                JOIN vault_private.vault_background_events e
                  ON e.user_id=w.user_id AND e.workspace_id=w.workspace_id
                  AND e.source_kind='transition' AND e.payload_json->>'work_id'=w.work_id
                JOIN vault_private.vault_background_actions a
                  ON a.user_id=w.user_id AND a.workspace_id=w.workspace_id
                  AND a.action_id=e.payload_json->'detail'->>'pending_action_id'
                JOIN vault_private.vault_background_workers k
                  ON k.user_id=w.user_id AND k.workspace_id=w.workspace_id
                  AND k.worker_id=a.receipt_json->>'worker_id'
                  AND k.role_key=w.request_json->'destination'->>'role_key'
                WHERE w.state IN ('waiting_approval','ready') AND w.worker_id IS NULL
                  AND a.kind='worker_create' AND a.state='completed'
                  AND k.status IN ('active','idle')
                ORDER BY w.work_id LIMIT 100
            """)
            candidates = cursor.fetchall()
        resumed = 0
        for row in candidates:
            try:
                outcome = self.plan_dispatch(row["work_id"])
            except (BackgroundRunAuthorizationError, BackgroundRunConflictError, ValueError):
                # One unresumable assignment never stops the durable worker loop.
                continue
            if outcome.state in {WorkState.QUEUED, WorkState.RUNNING, WorkState.COMPLETED}:
                resumed += 1
        return resumed

    def plan_dispatch(self, work_id: str) -> ExecutionOutcome:
        scope = self.resolve_work_scope(work_id)
        owner = OwnerScope(scope.user_id, scope.workspace_id)
        row = self._repo.get(owner, work_id)
        work_req = self._deserialize_work_request(row["request_json"])
        dest = work_req.destination
        role_key = str(dest.get("role_key") or "") or None
        worker_spec = self._deserialize_worker_spec(dest.get("worker_spec"))

        # Check specialist assignment or role proposal requirement
        if scope.worker_id is None and (role_key or worker_spec is not None):
            target_role = role_key or (worker_spec.role_key if worker_spec else "")
            approved_worker = self._find_approved_worker(owner, target_role)
            if approved_worker is None:
                if worker_spec is None:
                    raise BackgroundRunAuthorizationError(f"Specialist role '{target_role}' is not approved")
                prepared = self._workers.propose(
                    owner,
                    worker_spec,
                    origin_conversation_id=str(dest.get("conversation_id") or "") or None,
                    origin_turn_id=str(dest.get("turn_id") or "") or None,
                    origin_voice_session_id=str(dest.get("voice_session_id") or "") or None,
                )
                current_state = WorkState(row["state"])
                if current_state in {WorkState.PROPOSED, WorkState.QUEUED}:
                    self._repo.transition(
                        scope,
                        current_state,
                        WorkState.WAITING_APPROVAL,
                        {"pending_action_id": prepared.action_id, "role_key": target_role},
                    )
                return ExecutionOutcome(
                    state=WorkState.WAITING_APPROVAL,
                    pending_action_id=prepared.action_id,
                )
            worker_id, _gen = approved_worker
            current_state = WorkState(row["state"])
            if current_state is WorkState.WAITING_APPROVAL:
                self._repo.transition(
                    scope,
                    WorkState.WAITING_APPROVAL,
                    WorkState.READY,
                    {"approved_worker_id": worker_id, "role_key": target_role},
                )
            self._repo.assign(scope, worker_id)
            scope = self.resolve_work_scope(work_id)
            row = self._repo.get(owner, work_id)

        current_state = WorkState(row["state"])
        if current_state is WorkState.PROPOSED:
            self._repo.transition(scope, current_state, WorkState.READY, {"reason": "ready_for_dispatch"})
            current_state = WorkState.READY
        if current_state is WorkState.READY:
            if not getattr(self.jobs, "_schema_ensured", False):
                self.jobs.ensure_schema()
            with self._repo._connect() as connection:
                self.jobs.enqueue(connection, work_id)
        return ExecutionOutcome(WorkState(self._repo.get(owner, work_id)["state"]))

    async def dispatch(self, work_id: str) -> ExecutionOutcome:
        return self.plan_dispatch(work_id)

    async def execute_attempt(self, attempt: JobAttempt) -> ExecutionOutcome:
        scope = attempt.scope
        owner = OwnerScope(scope.user_id, scope.workspace_id)
        work_req = self._deserialize_work_request(attempt.request)
        dest = work_req.destination
        if work_req.request.goal_type in {"reminder", "follow_up", "self_routine"} and dest.get("schedule_meta"):
            # A reminder posts its saved text; a follow-up wakes the coordinator with its note.
            return ExecutionOutcome(WorkState.COMPLETED, output={"summary": work_req.request.objective})
        if (dest.get("role_key") or dest.get("worker_spec")) and scope.worker_id is None:
            raise BackgroundRunAuthorizationError("Specialist work requires an approved assigned worker")
        active_worker_spec = self._workers.get(owner, scope.worker_id) if scope.worker_id else None
        with self._repo._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT history_json FROM vault_private.vault_background_sessions
                   WHERE user_id=%s AND workspace_id=%s AND work_id=%s AND intent_version=%s""",
                (scope.user_id, scope.workspace_id, scope.work_id, scope.intent_version),
            )
            session = cursor.fetchone()
        prior_history = session["history_json"] if session else []

        # Scoped context & tool supply assembly
        allowed_tools = filter_helper_tool_names(
            requested_tools=work_req.request.requested_tool_names,
            worker_spec=active_worker_spec,
        )
        exec_request = work_req.request
        if active_worker_spec is not None:
            helper_prompt = build_helper_instructions(
                active_worker_spec,
                scope,
                brief={
                    "objective": exec_request.objective,
                    "success_criteria": exec_request.success_criteria,
                },
                prior_session_history=prior_history,
            )
            merged_context = (
                f"{exec_request.context_summary}\n\n{helper_prompt}".strip()
                if exec_request.context_summary
                else helper_prompt
            )
            exec_request = replace(
                exec_request,
                requested_tool_names=allowed_tools,
                context_summary=merged_context[:16384],
            )
        else:
            exec_request = replace(exec_request, requested_tool_names=allowed_tools)

        explicit_names = (
            frozenset(allowed_tools)
            if allowed_tools
            else (
                frozenset({"__none__"})
                if (work_req.request.requested_tool_names or active_worker_spec is not None)
                else frozenset()
            )
        )
        tool_supply = BackgroundToolSupply(
            catalog=self._catalog,
            grant=BackgroundToolGrant(
                autonomy=exec_request.autonomy,
                explicit_names=explicit_names,
                max_calls=exec_request.limits.max_tool_calls,
            ),
            user_id=scope.user_id,
            workspace_id=scope.workspace_id,
            calls_used=attempt.tool_calls,
            background_scope=scope,
            authority=self._authority,
        )

        def cancelled() -> bool:
            try:
                self.jobs.validate_attempt(attempt)
            except (BackgroundRunAuthorizationError, BackgroundRunConflictError):
                return True
            return False

        from .executor import ResumableBackgroundExecutor
        if isinstance(self._executor, ResumableBackgroundExecutor):
            return await self._executor.run_attempt(attempt, replace(work_req, request=exec_request), tool_supply)
        return await self._executor.execute(scope, exec_request, attempt.checkpoint, tool_supply, cancelled)

    def record_outcome(self, cursor, attempt: JobAttempt, row: dict, outcome: ExecutionOutcome) -> ExecutionOutcome:
        scope = attempt.scope
        destination = attempt.request.get("destination") or {}
        if outcome.state is WorkState.WAITING_APPROVAL and (
            row.get("routine_id") or row["source_key"].startswith("routine:")
        ) and not destination.get("turn_id"):
            outcome = replace(outcome, state=WorkState.WAITING_INPUT)
        if outcome.output is not None:
            outcome = replace(outcome, output=sanitize_helper_result(scope, attempt.run_id, outcome.output))
        if scope.worker_id:
            cursor.execute(
                """SELECT session_id,history_json,source_refs_json FROM vault_private.vault_background_sessions
                   WHERE user_id=%s AND workspace_id=%s AND work_id=%s AND intent_version=%s
                     AND worker_id=%s AND worker_generation=%s FOR UPDATE""",
                (scope.user_id, scope.workspace_id, scope.work_id, scope.intent_version,
                 scope.worker_id, scope.worker_generation),
            )
            session = cursor.fetchone()
            if session:
                history = session["history_json"]
                references = session["source_refs_json"]
                if outcome.output is not None:
                    references = list(dict.fromkeys(references + outcome.output.get("artifact_references", [])))
                    history = (history + [{
                        "work_id": scope.work_id, "intent_version": scope.intent_version,
                        "objective": attempt.request["request"]["objective"],
                        "summary": outcome.output.get("summary", ""), "state": outcome.state.value,
                    }])[-MAX_WORKER_HISTORY_ENTRIES:]
                cursor.execute(
                    """UPDATE vault_private.vault_background_sessions
                       SET history_json=%s, checkpoint_json=%s,source_refs_json=%s,updated_at=now() WHERE session_id=%s""",
                    (Jsonb(history), Jsonb(outcome.checkpoint), Jsonb(references), session["session_id"]),
                )
        return outcome

    def deliver_outcome(self, attempt: JobAttempt, outcome: ExecutionOutcome) -> None:
        scope = attempt.scope
        owner = OwnerScope(scope.user_id, scope.workspace_id)
        destination = attempt.request.get("destination") or {}
        if outcome.state is WorkState.WAITING_INPUT and outcome.pending_action_id:
            from app.vault_runtime.notifications.repository import NotificationRepository
            notifications = getattr(self._results, "_notifications", None) or NotificationRepository(
                database_url=self._database_url,
            )
            notifications.create(
                user_id=scope.user_id, workspace_id=scope.workspace_id, kind="background_approval",
                title="Routine waiting for approval",
                body="This routine is paused until its pending action can be reviewed in Link.",
                payload={"workId": scope.work_id, "actionId": outcome.pending_action_id},
            )
        if outcome.state in {WorkState.COMPLETED, WorkState.CANCELLED, WorkState.FAILED}:
            from .routines import BackgroundRoutines
            BackgroundRoutines(database_url=self._database_url).cancel_followups_for_work(
                owner, scope.work_id, reason=f"parent_{outcome.state.value}",
            )
        visible_failure = outcome.state in {WorkState.FAILED, WorkState.UNKNOWN} and destination.get("conversation_id")
        if destination and (outcome.state is WorkState.COMPLETED or visible_failure):
            self._results.deliver(scope, destination, f"{attempt.run_id}:{scope.intent_version}")
            goal_type = ((attempt.request.get("request") or {}).get("goal_type"))
            if destination.get("conversation_id") and goal_type != "reminder":
                # Rakazo returns a helper's result to the bot that owns the thread; here the
                # coordinator is woken in the originating chat to act on it.
                try:
                    self.jobs.request_wake(scope.user_id, scope.workspace_id, str(destination["conversation_id"]))
                except Exception:
                    logger.warning("coordinator_wake_request_failed")
        elif (outcome.state in {WorkState.COMPLETED, WorkState.FAILED, WorkState.UNKNOWN}
              and not destination.get("conversation_id") and not destination.get("internal")):
            # Work that no chat is waiting on (a direct request through the API, for example) is
            # still reported to the coordinator, who decides whether the owner needs to know.
            self.report_to_coordinator(scope, reason="no_chat")

    def report_to_coordinator(self, scope: WorkScope, *, reason: str) -> str | None:
        """Record the work's outcome for the owner's most recently active chat and wake the
        coordinator there. Returns the conversation, or None when the owner has no open chat."""
        from uuid import uuid4
        from psycopg.types.json import Jsonb
        from .work_record import work_record
        with self._repo._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT conversation_id FROM vault_private.vault_conversations
                   WHERE user_id=%s AND workspace_id=%s AND state='open'
                   ORDER BY COALESCE(activity_at, updated_at) DESC LIMIT 1""",
                (scope.user_id, scope.workspace_id),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            conversation_id = str(row["conversation_id"])
            record = work_record(cursor, user_id=scope.user_id, workspace_id=scope.workspace_id,
                                 work_id=scope.work_id)
            if record is None:
                return None
            cursor.execute(
                """INSERT INTO vault_private.vault_background_events
                   (event_id, user_id, workspace_id, source_kind, source_id, payload_json, state)
                   VALUES (%s, %s, %s, 'coordinator_report', %s, %s, 'processed')
                   ON CONFLICT DO NOTHING""",
                (str(uuid4()), scope.user_id, scope.workspace_id, f"{scope.work_id}:{scope.intent_version}",
                 Jsonb({"conversation_id": conversation_id, "reason": reason, "record": record})),
            )
        try:
            self.jobs.request_wake(scope.user_id, scope.workspace_id, conversation_id)
        except Exception:
            logger.warning("coordinator_wake_request_failed")
        return conversation_id

    # ---- The coordinator as a bot that owns its chat's work -------------------
    # Donor behavior: Rakazo wakes the same bot on its thread for timers, helper results and
    # approval answers, with its open work in context (docs/run-execution.md,
    # packages/adapters/src/scratchpad-context.ts @83db73c). Vault keeps its own records and
    # reads "what changed" from them instead of carrying it in the wake message.

    _DECIDED = ("approved", "completed", "denied", "failed", "expired")

    def conversation_updates(self, scope: OwnerScope, conversation_id: str, *, since=None) -> list[dict[str, object]]:
        """Approval decisions and background deliveries for this chat after ``since``."""
        from datetime import datetime, timezone
        since = since or datetime(1970, 1, 1, tzinfo=timezone.utc)
        updates: list[dict[str, object]] = []
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            cursor.execute(
                """SELECT action_id, kind, title, state, receipt_json, updated_at
                   FROM vault_private.vault_background_actions
                   WHERE user_id=%s AND workspace_id=%s AND work_id IS NULL
                     AND kind IN ('worker_create','execution_grant','routine_create')
                     AND COALESCE(origin_conversation_id, origin_json->>'conversation_id')=%s
                     AND state = ANY(%s) AND updated_at > %s
                   ORDER BY updated_at LIMIT 40""",
                (scope.user_id, scope.workspace_id, conversation_id, list(self._DECIDED), since),
            )
            for row in cursor.fetchall():
                decision = "approved" if row["state"] in {"approved", "completed"} else row["state"]
                updates.append({
                    "id": f"action:{row['action_id']}:{row['state']}",
                    "type": "approval",
                    "at": row["updated_at"].isoformat(),
                    "actionId": row["action_id"], "kind": row["kind"], "decision": decision,
                    "summary": f"{row['title']} was {decision}" + (
                        " and applied" if row["state"] == "completed" else ""),
                    "receipt": row["receipt_json"] or {},
                })
            cursor.execute(
                """SELECT event_id, payload_json, created_at FROM vault_private.vault_background_events
                   WHERE user_id=%s AND workspace_id=%s AND source_kind='result_delivery' AND state='processed'
                     AND payload_json->'destination'->>'conversation_id'=%s
                     AND payload_json->>'delivered_via'='conversation' AND created_at > %s
                   ORDER BY created_at LIMIT 40""",
                (scope.user_id, scope.workspace_id, conversation_id, since),
            )
            for row in cursor.fetchall():
                payload = row["payload_json"] or {}
                destination = payload.get("destination") or {}
                projection = payload.get("projection") or {}
                goal = destination.get("goal_type")
                kind = ("routine_run" if goal == "self_routine" else "follow_up" if destination.get("internal")
                        else "reminder" if goal == "reminder" else "result")
                updates.append({
                    "id": f"delivery:{row['event_id']}",
                    "type": kind,
                    "at": row["created_at"].isoformat(),
                    "workId": projection.get("work_id"),
                    "state": projection.get("state"),
                    "summary": str(projection.get("summary") or "")[:4000],
                    **({"record": projection["record"]} if isinstance(projection.get("record"), dict) else {}),
                })
            cursor.execute(
                """SELECT event_id, payload_json, created_at FROM vault_private.vault_background_events
                   WHERE user_id=%s AND workspace_id=%s AND source_kind='coordinator_report'
                     AND payload_json->>'conversation_id'=%s AND created_at > %s
                   ORDER BY created_at LIMIT 40""",
                (scope.user_id, scope.workspace_id, conversation_id, since),
            )
            for row in cursor.fetchall():
                payload = row["payload_json"] or {}
                record = payload.get("record") or {}
                updates.append({
                    "id": f"report:{row['event_id']}",
                    "type": "work_report",
                    "at": row["created_at"].isoformat(),
                    "workId": record.get("workId"),
                    "state": record.get("state"),
                    "summary": str((record.get("outcome") or {}).get("summary") or "")[:4000],
                    "record": record,
                })
            cursor.execute(
                """SELECT event_id, payload_json, created_at FROM vault_private.vault_background_events
                   WHERE user_id=%s AND workspace_id=%s AND source_kind='coordinator_checkin'
                     AND payload_json->>'conversation_id'=%s AND created_at > %s
                   ORDER BY created_at LIMIT 5""",
                (scope.user_id, scope.workspace_id, conversation_id, since),
            )
            for row in cursor.fetchall():
                updates.append({
                    "id": f"checkin:{row['event_id']}",
                    "type": "check_in",
                    "at": row["created_at"].isoformat(),
                    "summary": str((row["payload_json"] or {}).get("prompt") or "Daily check-in on unfinished work."),
                })
        updates.sort(key=lambda item: str(item["at"]))
        return updates

    def conversation_state(self, scope: OwnerScope, conversation_id: str, *, since=None) -> dict[str, object]:
        """What the coordinator is carrying in this chat: Rakazo's open-work context, from Vault records."""
        from datetime import datetime, timezone
        state: dict[str, object] = {
            "now": datetime.now(timezone.utc).isoformat(),
            "updatesSinceLastReply": self.conversation_updates(scope, conversation_id, since=since),
        }
        from .scratchpad import CoordinatorScratchpad
        scratchpad = CoordinatorScratchpad(database_url=self._database_url).context(
            scope.user_id, scope.workspace_id, conversation_id)
        if scratchpad:
            state["scratchpad"] = scratchpad
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            cursor.execute(
                """SELECT w.work_id, w.state, w.request_json->'request'->>'objective' AS objective,
                          w.request_json->'destination'->>'role_key' AS role_key, w.routine_id, w.updated_at
                   FROM vault_private.vault_background_work w
                   WHERE w.user_id=%s AND w.workspace_id=%s
                     AND w.request_json->'destination'->>'conversation_id'=%s
                     AND w.state NOT IN ('completed','failed','cancelled','unknown')
                   ORDER BY w.updated_at DESC LIMIT 15""",
                (scope.user_id, scope.workspace_id, conversation_id),
            )
            state["openWork"] = [
                {**{k: v for k, v in row.items() if k != "updated_at"}, "objective": str(row["objective"] or "")[:300],
                 "updatedAt": row["updated_at"].isoformat()}
                for row in cursor.fetchall()
            ]
            cursor.execute(
                """SELECT routine_id, status, timezone, rule_json, next_due_at,
                          template_json->'request'->>'objective' AS objective,
                          template_json->'request'->>'goal_type' AS goal_type
                   FROM vault_private.vault_background_routines
                   WHERE user_id=%s AND workspace_id=%s AND status IN ('active','paused')
                     AND template_json->'destination'->>'conversation_id'=%s
                   ORDER BY next_due_at NULLS LAST LIMIT 20""",
                (scope.user_id, scope.workspace_id, conversation_id),
            )
            state["scheduled"] = [
                {"routineId": row["routine_id"], "status": row["status"],
                 "kind": {"reminder": "reminder", "follow_up": "follow_up", "self_routine": "your_routine"}.get(
                     row["goal_type"] or "", "specialist_routine"),
                 "objective": str(row["objective"] or "")[:300], "schedule": row["rule_json"],
                 "timezone": row["timezone"],
                 "nextRunAt": row["next_due_at"].isoformat() if row["next_due_at"] else None}
                for row in cursor.fetchall()
            ]
            cursor.execute(
                """SELECT action_id, kind, title, expires_at FROM vault_private.vault_background_actions
                   WHERE user_id=%s AND workspace_id=%s AND state='pending' AND expires_at>now()
                     AND COALESCE(origin_conversation_id, origin_json->>'conversation_id')=%s
                   ORDER BY created_at LIMIT 20""",
                (scope.user_id, scope.workspace_id, conversation_id),
            )
            state["pendingApprovals"] = [
                {"actionId": row["action_id"], "kind": row["kind"], "title": row["title"],
                 "reviewUntil": row["expires_at"].isoformat()}
                for row in cursor.fetchall()
            ]
        return state

    def daily_checkins(self, now=None) -> int:
        """Rakazo's strategic initiative (strategic-initiative.ts): one daily check-in per chat on
        stale open scratchpad items; see scratchpad.CoordinatorScratchpad.reconcile_check_ins."""
        from .scratchpad import CoordinatorScratchpad
        queued = CoordinatorScratchpad(database_url=self._database_url).reconcile_check_ins(now)
        for user_id, workspace_id, conversation_id in queued:
            try:
                self.jobs.request_wake(user_id, workspace_id, conversation_id)
            except Exception:
                logger.warning("coordinator_checkin_wake_failed")
        return len(queued)

    def pending_hand_off_approvals(self, scope: OwnerScope, conversation_ids: list[str]) -> list[dict[str, object]]:
        """Approvals waiting for the owner from work Voice handed to these chats (proposals the
        coordinator made there and actions of background work it started from them)."""
        if not conversation_ids:
            return []
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            cursor.execute(
                """SELECT a.action_id, a.title, a.detail, a.detail_lines, a.expires_at
                   FROM vault_private.vault_background_actions a
                   LEFT JOIN vault_private.vault_background_work w
                     ON w.user_id=a.user_id AND w.workspace_id=a.workspace_id AND w.work_id=a.work_id
                   WHERE a.user_id=%s AND a.workspace_id=%s AND a.state='pending' AND a.expires_at>now()
                     AND a.kind<>'owner_approval'
                     AND (COALESCE(a.origin_conversation_id, a.origin_json->>'conversation_id') = ANY(%s)
                          OR w.request_json->'destination'->>'conversation_id' = ANY(%s))
                   ORDER BY a.created_at LIMIT 10""",
                (scope.user_id, scope.workspace_id, conversation_ids, conversation_ids),
            )
            rows = cursor.fetchall()
        return [{"id": row["action_id"], "title": row["title"],
                 "detail": list(row["detail_lines"] or [line for line in str(row["detail"] or "").splitlines() if line.strip()]),
                 "choices": ["allow_once", "deny"], "expires_at": int(row["expires_at"].timestamp()),
                 "kind": "background"} for row in rows]

    def after_owner_decision(self, scope: OwnerScope, action_id: str) -> bool:
        """Wake the chat that proposed an owner-decided role, grant or routine."""
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            cursor.execute(
                """SELECT kind, work_id, COALESCE(origin_conversation_id, origin_json->>'conversation_id') AS conversation_id
                   FROM vault_private.vault_background_actions
                   WHERE user_id=%s AND workspace_id=%s AND action_id=%s""",
                (scope.user_id, scope.workspace_id, action_id),
            )
            row = cursor.fetchone()
        if row is None or row["work_id"] is not None or not row["conversation_id"]:
            return False
        if row["kind"] not in {"worker_create", "execution_grant", "routine_create"}:
            return False
        return self.jobs.request_wake(scope.user_id, scope.workspace_id, str(row["conversation_id"]))

    def notify_reply(self, scope: OwnerScope, conversation_id: str, turn_id: str, text: str) -> None:
        """A reply the coordinator sent on its own also reaches the owner's notifications."""
        from app.vault_runtime.notifications.repository import NotificationRepository
        notifications = getattr(self._results, "_notifications", None) or NotificationRepository(
            database_url=self._database_url,
        )
        notifications.create(
            user_id=scope.user_id, workspace_id=scope.workspace_id, kind="assistant_message",
            title="Vault", body=" ".join(text.split())[:400],
            payload={"conversationId": conversation_id, "turnId": turn_id},
        )

    def dispatch_sync(self, work_id: str) -> ExecutionOutcome:
        """Drain the queue for an offline integration caller."""
        self.jobs.ensure_schema()

        async def drain():
            planned = await self.dispatch(work_id)
            if planned.pending_action_id:
                return planned
            await self.jobs.run_pending()
            scope = self.resolve_work_scope(work_id)
            row = self._repo.get(OwnerScope(scope.user_id, scope.workspace_id), work_id)
            with self._repo._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    "SELECT checkpoint_json, failure_code FROM vault_private.vault_background_runs WHERE work_id=%s",
                    (work_id,),
                )
                run = cursor.fetchone() or {}
            checkpoint = run.get("checkpoint_json")
            return ExecutionOutcome(
                WorkState(row["state"]), checkpoint=checkpoint, output=row.get("result_json"),
                pending_action_id=(checkpoint or {}).get("pending_action_id"),
                failure_code=run.get("failure_code"),
            )

        return asyncio.run(drain())
