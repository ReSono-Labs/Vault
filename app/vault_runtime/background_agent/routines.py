"""Donor-derived routines, follow-up scheduler, catch-up coalescing, and quiet initiative (Task 7).

Adapted from Rakazo (`elie222/rakazo` @ `83db73c2e5fe5002487f4dc1cf488fe601a34c25`, Apache-2.0):
- `packages/server/src/AgentSession/scheduling-tools.ts`, `scheduled-tasks.ts`, `followup-scheduler.ts`:
  IANA timezone + croniter recurrence, catch-up coalescing for unstarted read/preparation recurring
  templates (excluding attempted, effect-bearing, manual-retry, and one-shot work), and follow-up
  cancellation when linked parent work finishes or is declined.
- `packages/server/src/AgentSession/initiative.ts` & `initiative-runner.ts`:
  12-hour stale open-work threshold, once-daily check-in cooldown, quiet-hours suppression,
  no repeated offer after denial, source-diff fingerprint checks, and bounded setup backoff.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta, timezone
from hashlib import sha256
import json
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from croniter import croniter
from psycopg.types.json import Jsonb

from app.vault_runtime.local_identity.models import LocalPrincipal

from .contracts import AutonomyProfile, BackgroundRunRequest, ExecutionRecipe, RunLimits
from .coordination_contracts import OwnerScope, WorkRequest, WorkScope, WorkState
from .coordination_repository import CoordinationRepository, _json
from .output_contract import background_output_schema
from .errors import BackgroundRunAuthorizationError, BackgroundRunConflictError

LATE_WRITE_THRESHOLD_SECONDS = 300
MAX_CATCH_UP_STEPS = 512


@dataclass(frozen=True, slots=True)
class CatchUpPlan:
    occurrences_to_dispatch: tuple[datetime, ...]
    coalesced: bool
    coalesced_count: int
    lateness_seconds: float
    next_due_utc: datetime | None
    requires_revalidation_if_late: bool


def _require_aware_utc(dt: datetime) -> datetime:
    if not isinstance(dt, datetime) or dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("Scheduled time must be timezone-aware")
    return dt.astimezone(timezone.utc)


def compute_next_due_utc(
    *,
    rule: dict[str, object],
    timezone_name: str,
    after_utc: datetime,
) -> datetime | None:
    after_utc = _require_aware_utc(after_utc)
    zone = ZoneInfo(timezone_name)
    kind = str(rule.get("kind") or "cron")
    if kind == "once":
        raw_at = rule.get("run_at") or rule.get("scheduled_for")
        if not isinstance(raw_at, str) or not raw_at.strip():
            return None
        target = _require_aware_utc(datetime.fromisoformat(raw_at.replace("Z", "+00:00")))
        return target if target > after_utc else None

    expr = str(rule.get("cron") or "").strip()
    if not expr or not croniter.is_valid(expr):
        raise ValueError("Valid 5-field cron expression is required")
    local_after = after_utc.astimezone(zone)
    itr = croniter(expr, local_after, ret_type=datetime)
    next_local = itr.get_next(datetime)
    if next_local.tzinfo is None:
        next_local = next_local.replace(tzinfo=zone)
    return next_local.astimezone(timezone.utc)


def _is_coalesce_eligible(
    rule: dict[str, object],
    template: dict[str, object],
    *,
    has_started_or_attempted: bool,
) -> bool:
    if has_started_or_attempted:
        return False
    if str(rule.get("kind") or "cron") != "cron":
        return False
    if bool(template.get("effect_bearing")) or bool(template.get("manual_retry")) or bool(template.get("one_shot")):
        return False
    req = template.get("request") if isinstance(template.get("request"), dict) else {}
    if str(req.get("autonomy") or "limited") != "limited":
        return False
    return True


def compute_catch_up_occurrences(
    *,
    rule: dict[str, object],
    timezone_name: str,
    next_due_utc: datetime,
    now_utc: datetime,
    template: dict[str, object],
    has_started_or_attempted: bool = False,
) -> CatchUpPlan:
    due = _require_aware_utc(next_due_utc)
    now = _require_aware_utc(now_utc)
    if due > now:
        return CatchUpPlan(
            occurrences_to_dispatch=(),
            coalesced=False,
            coalesced_count=0,
            lateness_seconds=0.0,
            next_due_utc=due,
            requires_revalidation_if_late=False,
        )

    missed: list[datetime] = []
    cursor_time: datetime | None = due
    steps = 0
    while cursor_time is not None and cursor_time <= now and steps < MAX_CATCH_UP_STEPS:
        missed.append(cursor_time)
        cursor_time = compute_next_due_utc(rule=rule, timezone_name=timezone_name, after_utc=cursor_time)
        steps += 1

    lateness = max(0.0, (now - missed[0]).total_seconds())
    eligible = _is_coalesce_eligible(rule, template, has_started_or_attempted=has_started_or_attempted)
    req = template.get("request") if isinstance(template.get("request"), dict) else {}
    effect_bearing = bool(template.get("effect_bearing")) or str(req.get("autonomy") or "limited") != "limited"

    if eligible and len(missed) > 1:
        return CatchUpPlan(
            occurrences_to_dispatch=(missed[0],),
            coalesced=True,
            coalesced_count=len(missed),
            lateness_seconds=lateness,
            next_due_utc=cursor_time,
            requires_revalidation_if_late=False,
        )

    return CatchUpPlan(
        occurrences_to_dispatch=(missed[0],),
        coalesced=False,
        coalesced_count=1,
        lateness_seconds=lateness,
        next_due_utc=cursor_time,
        requires_revalidation_if_late=effect_bearing and lateness > LATE_WRITE_THRESHOLD_SECONDS,
    )


def _parse_hhmm(value: str) -> time:
    parts = str(value).strip().split(":")
    if len(parts) != 2:
        raise ValueError("Quiet hours time must be HH:MM")
    return time(int(parts[0]), int(parts[1]))


def source_fingerprint_changed(
    previous_fingerprint: str | None,
    current_payload: object,
) -> tuple[bool, str]:
    canonical = json.dumps(_json(current_payload), sort_keys=True, separators=(",", ":"))
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    return (previous_fingerprint != digest, digest)


def _tools_line(names) -> str:
    if "*" in names:
        return "all background tools (agent-to-agent sends stay with the coordinator)"
    return ", ".join(names) or "none"


class BackgroundRoutines:
    def __init__(self, *, database_url: str, jobs: Any = None) -> None:
        self._database_url = database_url
        self._repo = CoordinationRepository(database_url=database_url)
        self._jobs = jobs

    def attach_jobs(self, jobs: Any) -> None:
        self._jobs = jobs

    @staticmethod
    def _build_work_request(
        routine_id: str,
        version: int,
        scheduled_for: datetime,
        grant_id: str,
        template: dict[str, object],
        schedule_meta: dict[str, object],
    ) -> WorkRequest:
        req_raw = dict(template.get("request") or {})
        limits_raw = req_raw.get("limits")
        limits = RunLimits(**limits_raw) if isinstance(limits_raw, dict) else RunLimits()
        run_id = f"routine-{routine_id}-v{version}-{int(scheduled_for.timestamp())}"
        run_req = BackgroundRunRequest(
            run_id=run_id[:128],
            objective=str(req_raw.get("objective") or "Scheduled background routine"),
            instruction_profile=str(req_raw.get("instruction_profile") or "background-routine"),
            success_criteria=tuple(str(x) for x in (req_raw.get("success_criteria") or ("Routine completed",))),
            result_schema=dict(req_raw.get("result_schema") or background_output_schema()),
            recipe=ExecutionRecipe(req_raw.get("recipe", ExecutionRecipe.SELF_REVIEW)),
            autonomy=AutonomyProfile(req_raw.get("autonomy", AutonomyProfile.LIMITED)),
            limits=limits,
            goal_type=str(req_raw.get("goal_type", "routine")),
            context_summary=str(req_raw.get("context_summary", "")),
            expected_result=str(req_raw.get("expected_result", "")),
            scope=str(req_raw.get("scope", "")),
            exclusions=tuple(str(x) for x in req_raw.get("exclusions", ())),
            source_requirements=str(req_raw.get("source_requirements", "")),
            workspace_destination=req_raw.get("workspace_destination"),
            original_request=str(req_raw.get("original_request") or req_raw.get("objective") or "Scheduled routine"),
            verification_method=str(req_raw.get("verification_method") or "Verify against routine criteria"),
            completion_conditions=tuple(
                str(x) for x in (req_raw.get("completion_conditions") or ("Routine verified",))
            ),
            stop_conditions=tuple(str(x) for x in req_raw.get("stop_conditions", ())),
            requested_tool_names=tuple(str(x) for x in req_raw.get("requested_tool_names", ())),
        )
        dest = dict(template.get("destination") or {"kind": "activity"})
        dest["schedule_meta"] = _json(schedule_meta)
        return WorkRequest(
            request=run_req,
            grant_id=grant_id,
            local_session_id=None,
            destination=dest,
        )

    def propose(
        self,
        principal: LocalPrincipal,
        *,
        rule: dict[str, object],
        timezone: str,
        template: dict[str, object],
        grant_id: str | None,
        origin_conversation_id: str | None = None,
        origin_turn_id: str | None = None,
        origin_voice_session_id: str | None = None,
    ):
        from .actions import ACTION_TTL, BackgroundActions
        from .authority import proposal_hash
        from .coordination_contracts import PreparedAction

        if not isinstance(rule, dict) or not isinstance(template, dict) or not timezone:
            raise ValueError("Routine requires a rule, timezone, and template")
        ZoneInfo(timezone)
        anchor_raw = rule.get("anchor_utc")
        anchor = (
            _require_aware_utc(datetime.fromisoformat(str(anchor_raw).replace("Z", "+00:00")))
            if isinstance(anchor_raw, str) and anchor_raw.strip()
            else datetime.now(tz=ZoneInfo("UTC"))
        )
        if compute_next_due_utc(rule=rule, timezone_name=timezone, after_utc=anchor) is None:
            raise ValueError("Choose a future time for the one-time schedule.")
        scope = OwnerScope(principal.user_id, principal.workspace_id)
        proposal = _json({
            "rule": rule,
            "timezone": timezone,
            "template": template,
            "grant_id": grant_id,
        })
        if grant_id is None:
            request = template.get("request") or {}
            names = request.get("requested_tool_names", [])
            if (not isinstance(names, list) or len(names) > 20
                    or any(not isinstance(name, str) or not name.strip() for name in names)
                    or len(set(names)) != len(names)):
                raise ValueError("Routine tools must be explicit and bounded")
            proposal["execution_policy"] = {"tool_names": names, "resource_policy": {}}
        fingerprint = proposal_hash("routine_create", proposal)
        operation = f"routine-create:{fingerprint}"
        req = template.get("request") if isinstance(template.get("request"), dict) else {}
        objective = str(req.get("objective") or "Scheduled routine").strip()[:240]
        schedule = rule.get("cron") or rule.get("run_at") or rule.get("scheduled_for")
        detail_lines = [
            f"Objective: {objective}",
            f"Schedule: {schedule} ({timezone})",
            f"Tools: {_tools_line(req.get('requested_tool_names') or [])}",
        ]
        origin_meta = {
            k: v
            for k, v in (
                ("conversation_id", origin_conversation_id),
                ("turn_id", origin_turn_id),
                ("voice_session_id", origin_voice_session_id),
            )
            if isinstance(v, str) and v
        }
        now_utc = datetime.now(tz=ZoneInfo("UTC"))
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            self._repo._authority(cursor, scope, principal.session_id, None)
            if grant_id is not None:
                self._repo._authority(cursor, scope, None, grant_id)
            cursor.execute(
                """INSERT INTO vault_private.vault_background_actions
                   (action_id,user_id,workspace_id,kind,action_hash,arguments_json,title,detail,detail_lines,
                    expires_at,operation_key,origin_json)
                   VALUES (%s,%s,%s,'routine_create',%s,%s,%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(user_id,workspace_id,operation_key) DO NOTHING RETURNING *""",
                (
                    str(uuid4()),
                    scope.user_id,
                    scope.workspace_id,
                    fingerprint,
                    Jsonb(proposal),
                    f"Create routine: {objective[:120]}",
                    "\n".join(detail_lines),
                    Jsonb(detail_lines),
                    now_utc + ACTION_TTL,
                    operation,
                    Jsonb(origin_meta),
                ),
            )
            row = cursor.fetchone() or BackgroundActions._latest(cursor, scope, operation)
            if not (row["state"] == "approved" or (row["state"] == "pending" and row["expires_at"] > now_utc)):
                raise BackgroundRunConflictError("This routine proposal was already decided or expired; the owner must reopen it")
            return PreparedAction(
                row["action_id"], row["action_hash"], None, row["kind"],
                row["title"], row["detail"], row["expires_at"],
            )

    def create_from_approval(self, principal: LocalPrincipal, decision) -> str:
        from .authority import approved_record

        scope = OwnerScope(principal.user_id, principal.workspace_id)
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            self._repo._authority(cursor, scope, principal.session_id, None)
            row = approved_record(cursor, decision, "routine_create")
            if row["state"] == "completed":
                return str(row["receipt_json"]["routine_id"])
            args = row["arguments_json"]
            rule = args["rule"]
            timezone = str(args["timezone"])
            template = args["template"]
            grant_id = args["grant_id"]
            if grant_id is None:
                grant_id = str(uuid4())
                cursor.execute(
                    """INSERT INTO vault_private.vault_background_execution_grants
                       (grant_id,user_id,workspace_id,purpose,policy_json)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (grant_id, scope.user_id, scope.workspace_id, row["title"], Jsonb(args["execution_policy"])),
                )
            else:
                self._repo._authority(cursor, scope, None, grant_id)
            ZoneInfo(timezone)
            anchor_raw = rule.get("anchor_utc")
            anchor = (
                _require_aware_utc(datetime.fromisoformat(str(anchor_raw).replace("Z", "+00:00")))
                if isinstance(anchor_raw, str) and anchor_raw.strip()
                else datetime.now(tz=ZoneInfo("UTC"))
            )
            next_due = compute_next_due_utc(rule=rule, timezone_name=timezone, after_utc=anchor)
            if next_due is None or (rule.get("kind") == "once" and next_due <= datetime.now(ZoneInfo("UTC"))):
                raise BackgroundRunConflictError("That one-time schedule has already passed. Choose a new time.")
            routine_id = str(uuid4())
            cursor.execute(
                """INSERT INTO vault_private.vault_background_routines
                   (routine_id, user_id, workspace_id, version, rule_json, timezone, next_due_at,
                    grant_id, template_json, status)
                   VALUES (%s, %s, %s, 1, %s, %s, %s, %s, %s, 'active')""",
                (
                    routine_id,
                    scope.user_id,
                    scope.workspace_id,
                    Jsonb(_json(rule)),
                    timezone,
                    next_due,
                    grant_id,
                    Jsonb(_json(template)),
                ),
            )
            cursor.execute(
                """UPDATE vault_private.vault_background_actions
                   SET state='completed', receipt_json=%s, updated_at=now()
                   WHERE action_id=%s""",
                (Jsonb({"routine_id": routine_id}), decision.action_id),
            )
            return routine_id

    def create_owner_requested(
        self,
        principal: LocalPrincipal,
        *,
        rule: dict[str, object],
        timezone: str,
        template: dict[str, object],
    ) -> tuple[str, datetime]:
        """A specialist's routine the owner asked for in this turn is saved at once.

        Same grant and routine an approval would create (``create_from_approval``), without the
        approval card: the owner's own request is the decision. The specialist still runs only the
        tools named here, and any outward step it takes still asks for approval."""
        request = template.get("request") if isinstance(template.get("request"), dict) else {}
        destination = template.get("destination") if isinstance(template.get("destination"), dict) else {}
        names = request.get("requested_tool_names", [])
        if (not isinstance(names, list) or len(names) > 20
                or any(not isinstance(name, str) or not name.strip() for name in names)
                or len(set(names)) != len(names)):
            raise ValueError("Routine tools must be explicit and bounded")
        if not destination.get("role_key"):
            raise ValueError("Only a specialist's routine uses this path")
        ZoneInfo(timezone)
        now_utc = datetime.now(tz=ZoneInfo("UTC"))
        next_due = compute_next_due_utc(rule=rule, timezone_name=timezone, after_utc=now_utc)
        if next_due is None:
            raise ValueError("Choose a future time.")
        scope = OwnerScope(principal.user_id, principal.workspace_id)
        routine_id, grant_id = str(uuid4()), str(uuid4())
        objective = str(request.get("objective") or "Scheduled routine").strip()
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            self._repo._authority(cursor, scope, principal.session_id, None)
            cursor.execute(
                """INSERT INTO vault_private.vault_background_execution_grants
                   (grant_id,user_id,workspace_id,purpose,policy_json) VALUES (%s,%s,%s,%s,%s)""",
                (grant_id, scope.user_id, scope.workspace_id, f"Create routine: {objective[:120]}",
                 Jsonb({"tool_names": names, "resource_policy": {}})),
            )
            cursor.execute(
                """INSERT INTO vault_private.vault_background_routines
                   (routine_id, user_id, workspace_id, version, rule_json, timezone, next_due_at,
                    grant_id, template_json, status)
                   VALUES (%s, %s, %s, 1, %s, %s, %s, %s, %s, 'active')""",
                (routine_id, scope.user_id, scope.workspace_id, Jsonb(_json(rule)), timezone, next_due,
                 grant_id, Jsonb(_json(template))),
            )
        return routine_id, next_due

    def create(
        self,
        principal: LocalPrincipal,
        rule: dict[str, object],
        timezone: str,
        template: dict[str, object],
        grant_id: str,
    ) -> str:
        if not isinstance(rule, dict) or not isinstance(template, dict) or not timezone or not grant_id:
            raise ValueError("Routine requires rule, timezone, template, and grant_id")
        ZoneInfo(timezone)
        anchor_raw = rule.get("anchor_utc")
        anchor = (
            _require_aware_utc(datetime.fromisoformat(str(anchor_raw).replace("Z", "+00:00")))
            if isinstance(anchor_raw, str) and anchor_raw.strip()
            else datetime.now(tz=ZoneInfo("UTC"))
        )
        next_due = compute_next_due_utc(rule=rule, timezone_name=timezone, after_utc=anchor)
        scope = OwnerScope(principal.user_id, principal.workspace_id)
        routine_id = str(uuid4())
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            self._repo._authority(cursor, scope, principal.session_id, None)
            self._repo._authority(cursor, scope, None, grant_id)
            cursor.execute(
                """INSERT INTO vault_private.vault_background_routines
                   (routine_id, user_id, workspace_id, version, rule_json, timezone, next_due_at,
                    grant_id, template_json, status)
                   VALUES (%s, %s, %s, 1, %s, %s, %s, %s, %s, 'active')""",
                (
                    routine_id,
                    scope.user_id,
                    scope.workspace_id,
                    Jsonb(_json(rule)),
                    timezone,
                    next_due,
                    grant_id,
                    Jsonb(_json(template)),
                ),
            )
        return routine_id

    def create_tool_free(
        self,
        principal: LocalPrincipal,
        *,
        rule: dict[str, object],
        timezone: str,
        template: dict[str, object],
        purpose: str,
    ) -> tuple[str, datetime]:
        """Save a reminder or the coordinator's own follow-up without an approval.

        Rakazo's bot schedules its own reminders and follow-ups from chat. Here that is limited to
        work with no tools that only posts into, or wakes the coordinator in, the owner's own chat:
        the grant created with it allows no tools. Anything with tools still uses ``propose``."""
        request = template.get("request") if isinstance(template.get("request"), dict) else {}
        destination = template.get("destination") if isinstance(template.get("destination"), dict) else {}
        if (request.get("goal_type") not in {"reminder", "follow_up", "self_routine"} or request.get("requested_tool_names")
                or destination.get("kind") != "conversation" or not destination.get("conversation_id")
                or destination.get("role_key") or destination.get("worker_spec")):
            raise ValueError("Only tool-free reminders and follow-ups in a chat skip approval")
        ZoneInfo(timezone)
        now_utc = datetime.now(tz=ZoneInfo("UTC"))
        next_due = compute_next_due_utc(rule=rule, timezone_name=timezone, after_utc=now_utc)
        if next_due is None:
            raise ValueError("Choose a future time.")
        scope = OwnerScope(principal.user_id, principal.workspace_id)
        routine_id, grant_id = str(uuid4()), str(uuid4())
        parent_work_id = rule.get("parent_work_id") or template.get("parent_work_id")
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            self._repo._authority(cursor, scope, principal.session_id, None)
            cursor.execute(
                """SELECT count(*) AS open FROM vault_private.vault_background_routines
                   WHERE user_id=%s AND workspace_id=%s AND status='active'
                     AND template_json->'request'->>'goal_type' IN ('reminder','follow_up','self_routine')""",
                (scope.user_id, scope.workspace_id),
            )
            if cursor.fetchone()["open"] >= 200:
                raise BackgroundRunConflictError("Too many reminders and follow-ups are scheduled. Cancel some first.")
            cursor.execute(
                """SELECT count(*) AS recent FROM vault_private.vault_background_routines
                   WHERE user_id=%s AND workspace_id=%s AND created_at > now() - interval '1 hour'
                     AND template_json->'request'->>'goal_type'=%s
                     AND template_json->'destination'->>'conversation_id'=%s""",
                (scope.user_id, scope.workspace_id, request.get("goal_type"), destination.get("conversation_id")),
            )
            # Bounds a chain of self-wakes that keeps scheduling more of itself.
            if cursor.fetchone()["recent"] >= 12:
                raise BackgroundRunConflictError("This chat already scheduled 12 of these in the last hour. Wait or cancel some.")
            if isinstance(parent_work_id, str) and parent_work_id:
                cursor.execute(
                    """SELECT state FROM vault_private.vault_background_work
                       WHERE user_id=%s AND workspace_id=%s AND work_id=%s""",
                    (scope.user_id, scope.workspace_id, parent_work_id),
                )
                parent = cursor.fetchone()
                if parent is None:
                    raise BackgroundRunAuthorizationError("That work item is unavailable")
                if parent["state"] in {"completed", "cancelled", "failed", "unknown"}:
                    raise BackgroundRunConflictError("That work item is already finished")
            cursor.execute(
                """INSERT INTO vault_private.vault_background_execution_grants
                   (grant_id,user_id,workspace_id,purpose,policy_json) VALUES (%s,%s,%s,%s,%s)""",
                (grant_id, scope.user_id, scope.workspace_id, purpose[:240],
                 Jsonb({"tool_names": [], "resource_policy": {}})),
            )
            cursor.execute(
                """INSERT INTO vault_private.vault_background_routines
                   (routine_id, user_id, workspace_id, version, rule_json, timezone, next_due_at,
                    grant_id, template_json, status)
                   VALUES (%s, %s, %s, 1, %s, %s, %s, %s, %s, 'active')""",
                (routine_id, scope.user_id, scope.workspace_id, Jsonb(_json(rule)), timezone, next_due,
                 grant_id, Jsonb(_json(template))),
            )
        return routine_id, next_due

    def update_schedule(
        self,
        principal: LocalPrincipal,
        routine_id: str,
        *,
        rule: dict[str, object],
        timezone: str,
    ) -> int:
        ZoneInfo(timezone)
        anchor_raw = rule.get("anchor_utc")
        anchor = (
            _require_aware_utc(datetime.fromisoformat(str(anchor_raw).replace("Z", "+00:00")))
            if isinstance(anchor_raw, str) and anchor_raw.strip()
            else datetime.now(tz=ZoneInfo("UTC"))
        )
        next_due = compute_next_due_utc(rule=rule, timezone_name=timezone, after_utc=anchor)
        scope = OwnerScope(principal.user_id, principal.workspace_id)
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            self._repo._authority(cursor, scope, principal.session_id, None)
            cursor.execute(
                """UPDATE vault_private.vault_background_routines
                   SET version=version+1, rule_json=%s, timezone=%s, next_due_at=%s, updated_at=now()
                   WHERE user_id=%s AND workspace_id=%s AND routine_id=%s AND status<>'deleted'
                   RETURNING version""",
                (Jsonb(_json(rule)), timezone, next_due, scope.user_id, scope.workspace_id, routine_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise BackgroundRunAuthorizationError("Routine is unavailable")
            return int(row["version"])

    def schedule_followup(
        self,
        principal: LocalPrincipal,
        *,
        parent_work_id: str,
        due_at: datetime,
        template: dict[str, object],
        grant_id: str,
    ) -> str:
        due_utc = _require_aware_utc(due_at)
        scope = OwnerScope(principal.user_id, principal.workspace_id)
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            cursor.execute(
                """SELECT state FROM vault_private.vault_background_work
                   WHERE user_id=%s AND workspace_id=%s AND work_id=%s""",
                (scope.user_id, scope.workspace_id, parent_work_id),
            )
            parent = cursor.fetchone()
            if parent is None:
                raise BackgroundRunAuthorizationError("Parent work is unavailable")
            if parent["state"] in {"completed", "cancelled"}:
                raise BackgroundRunConflictError("Parent work is already finished")
        followup_template = dict(template)
        followup_template["one_shot"] = True
        followup_template["parent_work_id"] = parent_work_id
        rule = {
            "kind": "once",
            "run_at": due_utc.isoformat(),
            "anchor_utc": (due_utc - timedelta(seconds=1)).isoformat(),
            "parent_work_id": parent_work_id,
        }
        return self.create(principal, rule=rule, timezone="UTC", template=followup_template, grant_id=grant_id)

    def cancel_followups_for_work(self, scope: OwnerScope, parent_work_id: str, *, reason: str = "parent_closed") -> int:
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            cursor.execute(
                """UPDATE vault_private.vault_background_routines
                   SET status='deleted', next_due_at=NULL, updated_at=now()
                   WHERE user_id=%s AND workspace_id=%s AND status<>'deleted'
                     AND (rule_json->>'parent_work_id'=%s OR template_json->>'parent_work_id'=%s)
                   RETURNING routine_id""",
                (scope.user_id, scope.workspace_id, parent_work_id, parent_work_id),
            )
            routine_ids = [r["routine_id"] for r in cursor.fetchall()]
            if routine_ids:
                cursor.execute(
                    """UPDATE vault_private.vault_background_work
                       SET state='cancelled', updated_at=now()
                       WHERE user_id=%s AND workspace_id=%s
                         AND (parent_work_id=%s OR routine_id = ANY(%s))
                         AND state NOT IN ('completed', 'failed', 'cancelled', 'unknown')""",
                    (scope.user_id, scope.workspace_id, parent_work_id, routine_ids),
                )
            return len(routine_ids)

    def tick(self, now: datetime) -> int:
        now_utc = _require_aware_utc(now)
        created_count = 0
        with self._repo._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM vault_private.vault_background_routines
                   WHERE status='active' AND next_due_at IS NOT NULL AND next_due_at <= %s
                   ORDER BY next_due_at ASC LIMIT 64
                   FOR UPDATE SKIP LOCKED""",
                (now_utc,),
            )
            due_routines = cursor.fetchall()
            for routine in due_routines:
                scope = OwnerScope(routine["user_id"], routine["workspace_id"])
                try:
                    self._repo._owner(cursor, scope)
                    self._repo._authority(cursor, scope, None, routine["grant_id"])
                except BackgroundRunAuthorizationError:
                    cursor.execute(
                        """UPDATE vault_private.vault_background_routines
                           SET status='paused', updated_at=now() WHERE routine_id=%s""",
                        (routine["routine_id"],),
                    )
                    continue

                rule = routine["rule_json"] if isinstance(routine["rule_json"], dict) else {}
                template = routine["template_json"] if isinstance(routine["template_json"], dict) else {}
                parent_work_id = rule.get("parent_work_id") or template.get("parent_work_id")
                if isinstance(parent_work_id, str) and parent_work_id:
                    cursor.execute(
                        """SELECT state FROM vault_private.vault_background_work
                           WHERE user_id=%s AND workspace_id=%s AND work_id=%s""",
                        (scope.user_id, scope.workspace_id, parent_work_id),
                    )
                    parent_row = cursor.fetchone()
                    if parent_row is None or parent_row["state"] in {"completed", "cancelled", "failed"}:
                        cursor.execute(
                            """UPDATE vault_private.vault_background_routines
                               SET status='deleted', next_due_at=NULL, updated_at=now() WHERE routine_id=%s""",
                            (routine["routine_id"],),
                        )
                        continue

                cursor.execute(
                    """SELECT 1 FROM vault_private.vault_background_work
                       WHERE user_id=%s AND workspace_id=%s AND routine_id=%s
                         AND state IN ('running', 'waiting_approval', 'waiting_input') LIMIT 1""",
                    (scope.user_id, scope.workspace_id, routine["routine_id"]),
                )
                has_started = cursor.fetchone() is not None

                plan = compute_catch_up_occurrences(
                    rule=rule,
                    timezone_name=routine["timezone"],
                    next_due_utc=routine["next_due_at"],
                    now_utc=now_utc,
                    template=template,
                    has_started_or_attempted=has_started,
                )
                for scheduled_for in plan.occurrences_to_dispatch:
                    cursor.execute(
                        """INSERT INTO vault_private.vault_background_occurrences
                           (occurrence_id, user_id, workspace_id, routine_id, routine_version, scheduled_for)
                           VALUES (%s, %s, %s, %s, %s, %s)
                           ON CONFLICT(user_id, workspace_id, routine_id, routine_version, scheduled_for) DO NOTHING
                           RETURNING occurrence_id""",
                        (
                            str(uuid4()),
                            scope.user_id,
                            scope.workspace_id,
                            routine["routine_id"],
                            routine["version"],
                            scheduled_for,
                        ),
                    )
                    occ = cursor.fetchone()
                    if occ is None:
                        continue

                    schedule_meta = {
                        "routine_id": routine["routine_id"],
                        "routine_version": routine["version"],
                        "scheduled_for": scheduled_for.isoformat(),
                        "dispatched_at": now_utc.isoformat(),
                        "lateness_seconds": plan.lateness_seconds,
                        "coalesced": plan.coalesced,
                        "coalesced_count": plan.coalesced_count,
                        "requires_revalidation": plan.requires_revalidation_if_late,
                    }
                    work_req = self._build_work_request(
                        routine["routine_id"],
                        routine["version"],
                        scheduled_for,
                        routine["grant_id"],
                        template,
                        schedule_meta,
                    )
                    work_id = str(uuid4())
                    dest = work_req.destination if isinstance(work_req.destination, dict) else {}
                    requested_role = str(dest.get("role_key") or "").strip() or None
                    approved_worker_id: str | None = None
                    if requested_role or dest.get("worker_spec"):
                        if requested_role:
                            cursor.execute(
                                """SELECT worker_id FROM vault_private.vault_background_workers
                                   WHERE user_id=%s AND workspace_id=%s AND role_key=%s AND status='idle'
                                   FOR UPDATE""",
                                (scope.user_id, scope.workspace_id, requested_role),
                            )
                            w_row = cursor.fetchone()
                            if w_row is not None:
                                approved_worker_id = str(w_row["worker_id"])
                    if plan.requires_revalidation_if_late:
                        initial_state = WorkState.WAITING_APPROVAL.value
                    elif (requested_role or dest.get("worker_spec")) and approved_worker_id is None:
                        # Routine specialist work never bypasses WorkerRepository approval or assignment.
                        initial_state = WorkState.WAITING_INPUT.value
                    else:
                        initial_state = WorkState.READY.value
                    source_key = f"routine:{routine['routine_id']}:v{routine['version']}:{scheduled_for.isoformat()}"
                    cursor.execute(
                        """INSERT INTO vault_private.vault_background_work
                           (work_id, user_id, workspace_id, source_key, request_json, state,
                            grant_id, parent_work_id, routine_id)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (
                            work_id,
                            scope.user_id,
                            scope.workspace_id,
                            source_key,
                            Jsonb(_json(work_req.payload())),
                            initial_state,
                            routine["grant_id"],
                            parent_work_id if isinstance(parent_work_id, str) else None,
                            routine["routine_id"],
                        ),
                    )
                    cursor.execute(
                        """UPDATE vault_private.vault_background_occurrences
                           SET work_id=%s WHERE occurrence_id=%s""",
                        (work_id, occ["occurrence_id"]),
                    )
                    if approved_worker_id is not None and initial_state == WorkState.READY.value:
                        from .coordination_contracts import WorkScope
                        self._repo._assign(
                            cursor,
                            WorkScope(
                                scope.user_id,
                                scope.workspace_id,
                                work_id,
                                1,
                                None,
                                None,
                                routine["grant_id"],
                            ),
                            approved_worker_id,
                        )
                    if self._jobs is not None and initial_state == WorkState.READY.value:
                        self._jobs.enqueue(connection, work_id)
                    created_count += 1

                next_status = "deleted" if (str(rule.get("kind") or "cron") == "once") else "active"
                cursor.execute(
                    """UPDATE vault_private.vault_background_routines
                       SET next_due_at=%s, status=%s, updated_at=now()
                       WHERE routine_id=%s""",
                    (plan.next_due_utc, next_status, routine["routine_id"]),
                )
        return created_count

    def _invalidate_routine_work(self, connection, cursor, scope: OwnerScope, routine_id: str) -> None:
        cursor.execute(
            """SELECT work_id FROM vault_private.vault_background_work
               WHERE user_id=%s AND workspace_id=%s AND routine_id=%s
                 AND state NOT IN ('completed', 'failed', 'cancelled', 'unknown')
               FOR UPDATE""",
            (scope.user_id, scope.workspace_id, routine_id),
        )
        work_ids = [r["work_id"] for r in cursor.fetchall()]
        for work_id in work_ids:
            if self._jobs is not None:
                self._jobs.cancel(connection, work_id)
            else:
                cursor.execute(
                    """UPDATE vault_private.vault_background_work
                       SET state='cancelled', updated_at=now() WHERE work_id=%s""",
                    (work_id,),
                )
                cursor.execute(
                    """UPDATE vault_private.vault_background_runs
                       SET cancellation_requested=true, state='cancelled', updated_at=now()
                       WHERE work_id=%s AND state NOT IN ('completed', 'failed', 'cancelled')""",
                    (work_id,),
                )
        cursor.execute(
            """UPDATE vault_private.vault_background_actions
               SET state='expired', updated_at=now()
               WHERE user_id=%s AND workspace_id=%s AND state IN ('pending', 'approved')
                 AND work_id = ANY(%s)""",
            (scope.user_id, scope.workspace_id, work_ids),
        )

    def run_now(self, principal: LocalPrincipal, routine_id: str, *, call_key: str, jobs) -> tuple[str, str]:
        """Save and enqueue a manual occurrence without changing the schedule."""
        scope = OwnerScope(principal.user_id, principal.workspace_id)
        source_key = f"routine-manual:{routine_id}:{call_key}"
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            self._repo._authority(cursor, scope, principal.session_id, None)
            cursor.execute(
                """SELECT * FROM vault_private.vault_background_routines
                   WHERE user_id=%s AND workspace_id=%s AND routine_id=%s AND status<>'deleted' FOR UPDATE""",
                (scope.user_id, scope.workspace_id, routine_id),
            )
            routine = cursor.fetchone()
            if routine is None:
                raise BackgroundRunAuthorizationError("Routine is unavailable")
            self._repo._authority(cursor, scope, None, routine["grant_id"])
            cursor.execute(
                """SELECT work_id,state FROM vault_private.vault_background_work
                   WHERE user_id=%s AND workspace_id=%s AND source_key=%s""",
                (scope.user_id, scope.workspace_id, source_key),
            )
            existing = cursor.fetchone()
            if existing is not None:
                return existing["work_id"], existing["state"]
            now = datetime.now(ZoneInfo("UTC"))
            work = self._build_work_request(
                routine_id, routine["version"], now, routine["grant_id"], routine["template_json"],
                {"kind": "manual", "dispatched_at": now.isoformat()},
            )
            work_id = str(uuid4())
            work = replace(work, request=replace(work.request, run_id=work_id))
            role_key = str(work.destination.get("role_key") or "").strip()
            worker_id = None
            if role_key or work.destination.get("worker_spec"):
                cursor.execute(
                    """SELECT worker_id FROM vault_private.vault_background_workers
                       WHERE user_id=%s AND workspace_id=%s AND role_key=%s
                         AND status IN ('idle','active') FOR UPDATE""",
                    (scope.user_id, scope.workspace_id, role_key),
                )
                worker = cursor.fetchone()
                if worker is None:
                    raise BackgroundRunAuthorizationError(f"Specialist role '{role_key}' is unavailable")
                worker_id = worker["worker_id"]
            cursor.execute(
                """INSERT INTO vault_private.vault_background_work
                   (work_id,user_id,workspace_id,source_key,request_json,grant_id,routine_id,state)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,'ready')""",
                (work_id, scope.user_id, scope.workspace_id, source_key,
                 Jsonb(_json(work.payload())), work.grant_id, routine_id),
            )
            if worker_id is not None:
                self._repo._assign(
                    cursor,
                    WorkScope(scope.user_id, scope.workspace_id, work_id, 1, None, None, routine["grant_id"]),
                    worker_id,
                )
            jobs.enqueue(connection, work_id)
            return work_id, WorkState.QUEUED.value

    def pause(self, principal: LocalPrincipal, routine_id: str) -> None:
        scope = OwnerScope(principal.user_id, principal.workspace_id)
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            self._repo._authority(cursor, scope, principal.session_id, None)
            cursor.execute(
                """UPDATE vault_private.vault_background_routines
                   SET status='paused', updated_at=now()
                   WHERE user_id=%s AND workspace_id=%s AND routine_id=%s AND status<>'deleted'
                   RETURNING routine_id""",
                (scope.user_id, scope.workspace_id, routine_id),
            )
            if cursor.fetchone() is None:
                raise BackgroundRunAuthorizationError("Routine is unavailable")
            self._invalidate_routine_work(connection, cursor, scope, routine_id)

    def resume(self, principal: LocalPrincipal, routine_id: str) -> None:
        scope = OwnerScope(principal.user_id, principal.workspace_id)
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            self._repo._authority(cursor, scope, principal.session_id, None)
            cursor.execute(
                """SELECT status, rule_json, timezone, grant_id FROM vault_private.vault_background_routines
                   WHERE user_id=%s AND workspace_id=%s AND routine_id=%s AND status<>'deleted'
                   FOR UPDATE""",
                (scope.user_id, scope.workspace_id, routine_id),
            )
            routine = cursor.fetchone()
            if routine is None:
                raise BackgroundRunAuthorizationError("Routine is unavailable")
            self._repo._authority(cursor, scope, None, routine["grant_id"])
            if routine["status"] == "active":
                return
            due = compute_next_due_utc(
                rule=routine["rule_json"], timezone_name=routine["timezone"],
                after_utc=datetime.now(ZoneInfo("UTC")),
            )
            if due is None:
                raise ValueError("The one-time schedule has passed. Set a new time before resuming.")
            cursor.execute(
                """UPDATE vault_private.vault_background_routines
                   SET status='active',version=version+1,next_due_at=%s,updated_at=now()
                   WHERE user_id=%s AND workspace_id=%s AND routine_id=%s""",
                (due, scope.user_id, scope.workspace_id, routine_id),
            )

    def cancel(self, principal: LocalPrincipal, routine_id: str) -> None:
        scope = OwnerScope(principal.user_id, principal.workspace_id)
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            self._repo._authority(cursor, scope, principal.session_id, None)
            cursor.execute(
                """UPDATE vault_private.vault_background_routines
                   SET status='deleted', next_due_at=NULL, updated_at=now()
                   WHERE user_id=%s AND workspace_id=%s AND routine_id=%s
                   RETURNING routine_id""",
                (scope.user_id, scope.workspace_id, routine_id),
            )
            if cursor.fetchone() is None:
                raise BackgroundRunAuthorizationError("Routine is unavailable")
            self._invalidate_routine_work(connection, cursor, scope, routine_id)

    def observe_source_change(
        self,
        scope: OwnerScope,
        *,
        source_kind: str,
        source_id: str,
        items: object,
        now: datetime,
    ) -> bool:
        now_utc = _require_aware_utc(now)
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            fp_key = f"{source_kind}:{source_id}"
            cursor.execute(
                """SELECT payload_json FROM vault_private.vault_background_events
                   WHERE user_id=%s AND workspace_id=%s AND source_kind='source_fingerprint'
                     AND source_id=%s FOR UPDATE""",
                (scope.user_id, scope.workspace_id, fp_key),
            )
            prior = cursor.fetchone()
            prev_fp = prior["payload_json"].get("fingerprint") if (prior and isinstance(prior["payload_json"], dict)) else None
            changed, new_fp = source_fingerprint_changed(prev_fp, items)
            if not changed:
                return False
            cursor.execute(
                """INSERT INTO vault_private.vault_background_events
                   (event_id, user_id, workspace_id, source_kind, source_id, payload_json, state)
                   VALUES (%s, %s, %s, 'source_fingerprint', %s, %s, 'processed')
                   ON CONFLICT(user_id, workspace_id, source_kind, source_id) DO UPDATE SET
                     payload_json=EXCLUDED.payload_json, state='processed'""",
                (
                    str(uuid4()),
                    scope.user_id,
                    scope.workspace_id,
                    fp_key,
                    Jsonb({"fingerprint": new_fp, "updated_at": now_utc.isoformat()}),
                ),
            )
            return True

    def reconcile_after_restore(
        self,
        scope: OwnerScope,
        *,
        now: datetime,
        calendar_snapshots: dict[str, object] | None = None,
        mail_snapshots: dict[str, object] | None = None,
    ) -> None:
        now_utc = _require_aware_utc(now)
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            # Restore starts automation paused until grants/integrations/destinations are reconciled
            cursor.execute(
                """UPDATE vault_private.vault_background_routines
                   SET status='paused', updated_at=now()
                   WHERE user_id=%s AND workspace_id=%s AND status='active'""",
                (scope.user_id, scope.workspace_id),
            )
            for cal_id, items in (calendar_snapshots or {}).items():
                _changed, fp = source_fingerprint_changed(None, items)
                cursor.execute(
                    """INSERT INTO vault_private.vault_background_events
                       (event_id, user_id, workspace_id, source_kind, source_id, payload_json, state)
                       VALUES (%s, %s, %s, 'source_fingerprint', %s, %s, 'processed')
                       ON CONFLICT(user_id, workspace_id, source_kind, source_id) DO UPDATE SET
                         payload_json=EXCLUDED.payload_json, state='processed'""",
                    (
                        str(uuid4()),
                        scope.user_id,
                        scope.workspace_id,
                        f"calendar_sync:{cal_id}",
                        Jsonb({"fingerprint": fp, "updated_at": now_utc.isoformat(), "reconciled_on_restore": True}),
                    ),
                )
            for mail_id, items in (mail_snapshots or {}).items():
                _changed, fp = source_fingerprint_changed(None, items)
                cursor.execute(
                    """INSERT INTO vault_private.vault_background_events
                       (event_id, user_id, workspace_id, source_kind, source_id, payload_json, state)
                       VALUES (%s, %s, %s, 'source_fingerprint', %s, %s, 'processed')
                       ON CONFLICT(user_id, workspace_id, source_kind, source_id) DO UPDATE SET
                         payload_json=EXCLUDED.payload_json, state='processed'""",
                    (
                        str(uuid4()),
                        scope.user_id,
                        scope.workspace_id,
                        f"mail_sync:{mail_id}",
                        Jsonb({"fingerprint": fp, "updated_at": now_utc.isoformat(), "reconciled_on_restore": True}),
                    ),
                )
