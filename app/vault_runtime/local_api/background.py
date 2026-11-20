"""Authenticated, CSRF-protected browser routes for Background Activity, specialist profiles, routines, actions, and preferences (Task 9)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.vault_runtime.background_agent.actions import BackgroundActions
from app.vault_runtime.background_agent.authority import BackgroundAuthority
from app.vault_runtime.background_agent.contracts import RunLimits
from app.vault_runtime.background_agent.coordination_contracts import (
    ApprovalDecision,
    OwnerScope,
    WorkerSpec,
    WorkState,
)
from app.vault_runtime.background_agent.coordination_repository import CoordinationRepository, _json
from app.vault_runtime.background_agent.errors import (
    BackgroundRunAuthorizationError,
    BackgroundRunConflictError,
)
from app.vault_runtime.background_agent.routines import BackgroundRoutines, _parse_hhmm
from app.vault_runtime.background_agent.worker_repository import WorkerRepository
from app.vault_runtime.local_identity.models import LocalPrincipal
from zoneinfo import ZoneInfo

_LOG = logging.getLogger(__name__)

STANDING_SCOPE_TEXT = (
    "Allows read and preparation checks on committed Chat/Voice turns and connected mail/calendar. "
    "Specialist creation and external writes still require your approval."
)

_FORBIDDEN_DECISION_KEYS = frozenset({
    "approve",
    "approved",
    "owner_approved",
    "actor_user_id",
    "actorUserId",
    "workspace_id",
    "workspaceId",
    "channel",
    "channel_generation",
    "channelGeneration",
})


def canonical_status_label(state: str) -> str:
    """Map internal work state to canonical UI status label: queued/running/needs-you/done/failed/unknown."""
    s = str(state or "").strip().lower()
    if s in {"proposed", "ready", "queued"}:
        return "queued"
    if s == "running":
        return "running"
    if s in {"waiting_approval", "waiting_input", "waiting_event"}:
        return "needs-you"
    if s == "completed":
        return "done"
    if s in {"failed", "cancelled"}:
        return "failed"
    return "unknown"


def _sanitize_result_projection(result_json: Any) -> dict[str, Any] | None:
    if not isinstance(result_json, dict):
        return None
    cards = result_json.get("cards")
    return {
        "status": result_json.get("status"),
        "summary": str(result_json.get("summary") or ""),
        "artifact_references": [
            str(r) for r in (result_json.get("artifact_references") or []) if isinstance(r, str)
        ],
        "verification_summary": str(result_json.get("verification_summary") or ""),
        "cards": list(cards) if isinstance(cards, list) else [],
    }


def _resolve_database_url(app: Any) -> str:
    for attr in ("_background_runs", "_tasks", "_notifications", "_link_companion"):
        obj = getattr(app, attr, None)
        url = getattr(obj, "_database_url", None)
        if isinstance(url, str) and url:
            return url
    identity_repo = getattr(getattr(app, "_identity_service", None), "_repository", None)
    url = getattr(identity_repo, "_database_url", None)
    if isinstance(url, str) and url:
        return url
    raise RuntimeError("Background coordination database is unavailable.")


def _validate_task_in_scope(cursor, scope: OwnerScope, task_id: str) -> dict[str, Any]:
    cursor.execute("SELECT to_regclass('vault_private.vault_tasks') AS reg")
    if (cursor.fetchone() or {}).get("reg") is None:
        raise BackgroundRunAuthorizationError("Task is not available in this scope")
    cursor.execute(
        """SELECT task_id, task_text, status, created_at, updated_at, completed_at
           FROM vault_private.vault_tasks
           WHERE user_id=%s AND workspace_id=%s AND task_id=%s""",
        (scope.user_id, scope.workspace_id, task_id),
    )
    row = cursor.fetchone()
    if row is None:
        raise BackgroundRunAuthorizationError("Task is not available in this scope")
    return {
        "taskId": str(row["task_id"]),
        "text": str(row["task_text"]),
        "status": str(row["status"]),
        "createdAt": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
        "updatedAt": row["updated_at"].isoformat() if hasattr(row["updated_at"], "isoformat") else str(row["updated_at"]),
        "completedAt": (
            row["completed_at"].isoformat()
            if row["completed_at"] is not None and hasattr(row["completed_at"], "isoformat")
            else (str(row["completed_at"]) if row["completed_at"] is not None else None)
        ),
    }


def _lookup_task_if_valid(cursor, scope: OwnerScope, task_id: str | None) -> dict[str, Any] | None:
    if not isinstance(task_id, str) or not task_id.strip():
        return None
    try:
        return _validate_task_in_scope(cursor, scope, task_id.strip())
    except BackgroundRunAuthorizationError:
        return None


def _work_item_payload(cursor, scope: OwnerScope, row: dict[str, Any]) -> dict[str, Any]:
    req_wrapper = row["request_json"] if isinstance(row["request_json"], dict) else {}
    req = req_wrapper.get("request") if isinstance(req_wrapper.get("request"), dict) else {}
    dest = req_wrapper.get("destination") if isinstance(req_wrapper.get("destination"), dict) else {}

    raw_task_id = row.get("task_id") or dest.get("task_id") or dest.get("taskId")
    task_obj = _lookup_task_if_valid(cursor, scope, str(raw_task_id) if raw_task_id else None)
    validated_task_id = task_obj["taskId"] if task_obj is not None else None

    role_key = row.get("worker_role_key") or dest.get("role_key")
    if not role_key and row.get("worker_id"):
        cursor.execute(
            """SELECT role_key FROM vault_private.vault_background_workers
               WHERE user_id=%s AND workspace_id=%s AND worker_id=%s""",
            (scope.user_id, scope.workspace_id, row["worker_id"]),
        )
        w_row = cursor.fetchone()
        if w_row:
            role_key = w_row["role_key"]

    cursor.execute(
        """SELECT action_id, action_hash, kind, title, detail, detail_lines, expires_at
           FROM vault_private.vault_background_actions
           WHERE user_id=%s AND workspace_id=%s AND work_id=%s
             AND state='pending' AND expires_at > now()
           ORDER BY created_at DESC LIMIT 1""",
        (scope.user_id, scope.workspace_id, row["work_id"]),
    )
    pending_act = cursor.fetchone()

    return {
        "workId": row["work_id"],
        "state": row["state"],
        "statusLabel": canonical_status_label(row["state"]),
        "intentVersion": int(row["intent_version"]),
        "objective": str(req.get("objective") or ""),
        "workerId": row["worker_id"],
        "workerGeneration": row["worker_generation"],
        "roleKey": role_key,
        "taskId": validated_task_id,
        "task": task_obj,
        "routineId": row["routine_id"],
        "parentWorkId": row["parent_work_id"],
        "pendingActionId": pending_act["action_id"] if pending_act else None,
        "result": _sanitize_result_projection(row.get("result_json")),
        "createdAt": row["created_at"].isoformat(),
        "updatedAt": row["updated_at"].isoformat(),
        "startedAt": row["started_at"].isoformat() if row.get("started_at") else None,
        "activeSeconds": row.get("elapsed_seconds"),
        # Run details for the Background work page (present when the query joins the run).
        "runId": row.get("run_id"),
        "failureCode": row.get("run_failure_code"),
        "completedAt": row["run_completed_at"].isoformat() if row.get("run_completed_at") else None,
        "modelTurns": row.get("run_model_turns"),
        "toolCalls": row.get("run_tool_calls"),
    }


def _action_item_payload(principal: LocalPrincipal, row: dict[str, Any]) -> dict[str, Any]:
    detail_lines = row.get("detail_lines")
    if not isinstance(detail_lines, list) or not detail_lines:
        detail_lines = [line for line in str(row.get("detail") or "").splitlines() if line.strip()]
    origin = row.get("origin_json") or {}
    rule = (row.get("arguments_json") or {}).get("rule") or {}
    channels = ["browser", "link"] if principal.is_device_owner else ["browser"]
    return {
        "actionId": row["action_id"],
        "actionHash": row["action_hash"],
        "workId": row.get("work_id"),
        "kind": row["kind"],
        "title": row["title"],
        "detail": row["detail"],
        "detailLines": [str(x) for x in detail_lines],
        "state": row["state"],
        "expiresAt": row["expires_at"].isoformat() if hasattr(row["expires_at"], "isoformat") else str(row["expires_at"]),
        "channels": channels,
        "scheduleKind": rule.get("kind") if row["kind"] == "routine_create" else None,
        "conversationId": row.get("origin_conversation_id") or origin.get("conversation_id"),
        "voiceSessionId": row.get("origin_voice_session_id") or origin.get("voice_session_id"),
    }


def handle_background_coordination_api(
    app: Any,
    principal: LocalPrincipal,
    *,
    method: str,
    path: str,
    payload: dict[str, Any],
    respond: Any,
):
    database_url = _resolve_database_url(app)
    repo = CoordinationRepository(database_url=database_url)
    scope = OwnerScope(principal.user_id, principal.workspace_id)

    # 1. Preferences: GET/POST /background/preferences
    if path == "/background/preferences":
        if method == "GET":
            prefs = repo.get_preferences(scope)
            enabled = bool(prefs.get("enabled", False))
            return respond(200, {
                "enabled": enabled,
                "optIn": enabled,
                "quietHours": dict(prefs.get("quiet_hours") or {}),
                "approvedGrantIds": list(prefs.get("approved_grant_ids") or []),
                "standingScope": STANDING_SCOPE_TEXT,
            })
        if method == "POST":
            enabled: bool | None = None
            if "enabled" in payload:
                if not isinstance(payload["enabled"], bool):
                    raise ValueError("enabled must be a boolean")
                enabled = payload["enabled"]
            elif "optIn" in payload:
                if not isinstance(payload["optIn"], bool):
                    raise ValueError("optIn must be a boolean")
                enabled = payload["optIn"]

            quiet_hours: dict[str, object] | None = None
            raw_qh = payload.get("quietHours") if "quietHours" in payload else payload.get("quiet_hours")
            if raw_qh is not None:
                if not isinstance(raw_qh, dict):
                    raise ValueError("quietHours must be an object")
                if raw_qh:
                    start_s = str(raw_qh.get("start") or "").strip()
                    end_s = str(raw_qh.get("end") or "").strip()
                    tz_s = str(raw_qh.get("timezone") or "UTC").strip()
                    if start_s:
                        _parse_hhmm(start_s)
                    if end_s:
                        _parse_hhmm(end_s)
                    ZoneInfo(tz_s)
                    quiet_hours = {"start": start_s, "end": end_s, "timezone": tz_s}
                else:
                    quiet_hours = {}

            raw_grants = payload.get("approvedGrantIds") if "approvedGrantIds" in payload else payload.get("approved_grant_ids")
            grant_ids: list[str] | None = None
            if raw_grants is not None:
                if not isinstance(raw_grants, list) or any(not isinstance(g, str) for g in raw_grants):
                    raise ValueError("approvedGrantIds must be a list of strings")
                grant_ids = [g.strip() for g in raw_grants if g.strip()]

            prefs = repo.set_preferences(
                scope,
                enabled=enabled,
                quiet_hours=quiet_hours,
                approved_grant_ids=grant_ids,
            )
            now_enabled = bool(prefs.get("enabled", False))
            return respond(200, {
                "enabled": now_enabled,
                "optIn": now_enabled,
                "quietHours": dict(prefs.get("quiet_hours") or {}),
                "approvedGrantIds": list(prefs.get("approved_grant_ids") or []),
                "standingScope": STANDING_SCOPE_TEXT,
            })
        return None

    # 2. Workers: GET/POST /background/workers, POST /background/workers/{id}/{pause|reset|delete}
    if path == "/background/workers":
        if method == "GET":
            with repo._connect() as connection, connection.cursor() as cursor:
                repo._owner(cursor, scope)
                cursor.execute(
                    """SELECT worker_id, role_key, spec_json, generation, status, created_at, updated_at
                       FROM vault_private.vault_background_workers
                       WHERE user_id=%s AND workspace_id=%s AND status<>'deleted'
                       ORDER BY created_at ASC, worker_id ASC""",
                    (scope.user_id, scope.workspace_id),
                )
                rows = cursor.fetchall()
            items = []
            for r in rows:
                spec_j = r["spec_json"] if isinstance(r["spec_json"], dict) else {}
                items.append({
                    "workerId": r["worker_id"],
                    "roleKey": r["role_key"],
                    "purpose": str(spec_j.get("purpose") or ""),
                    "instructions": str(spec_j.get("instructions") or ""),
                    "toolNames": list(spec_j.get("tool_names") or []),
                    "resourcePolicy": dict(spec_j.get("resource_policy") or {}),
                    "generation": int(r["generation"]),
                    "status": r["status"],
                    "createdAt": r["created_at"].isoformat(),
                    "updatedAt": r["updated_at"].isoformat(),
                })
            return respond(200, {"items": items})

        if method == "POST":
            role_key = str(payload.get("roleKey") or payload.get("role_key") or "").strip()
            purpose = str(payload.get("purpose") or "").strip()
            instructions = str(payload.get("instructions") or purpose).strip()
            raw_tools = payload.get("toolNames") if "toolNames" in payload else payload.get("tool_names", [])
            if not isinstance(raw_tools, list) or any(not isinstance(t, str) for t in raw_tools):
                raise ValueError("toolNames must be a list of strings")
            resource_policy = payload.get("resourcePolicy") if "resourcePolicy" in payload else payload.get("resource_policy", {})
            if not isinstance(resource_policy, dict):
                raise ValueError("resourcePolicy must be an object")
            limits_raw = payload.get("limits")
            limits = RunLimits(**limits_raw) if isinstance(limits_raw, dict) else RunLimits()

            spec = WorkerSpec(
                role_key=role_key,
                purpose=purpose,
                instructions=instructions,
                tool_names=tuple(t.strip() for t in raw_tools if t.strip()),
                resource_policy=resource_policy,
                limits=limits,
            )
            workers = WorkerRepository(database_url=database_url)
            prepared = workers.propose(scope, spec)
            detail_lines = [
                f"Role: {spec.role_key}",
                f"Purpose: {spec.purpose}",
                f"Tools: {', '.join(spec.tool_names) if spec.tool_names else 'none'}",
            ]
            with repo._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE vault_private.vault_background_actions
                       SET detail_lines=%s WHERE action_id=%s AND user_id=%s AND workspace_id=%s
                       RETURNING *""",
                    (Jsonb(detail_lines), prepared.action_id, scope.user_id, scope.workspace_id),
                )
                row = cursor.fetchone()
            return respond(202, {"action": _action_item_payload(principal, row)})
        return None

    if path.startswith("/background/workers/"):
        suffix = path.removeprefix("/background/workers/").strip("/")
        worker_id, _, op = suffix.partition("/")
        if method == "POST" and worker_id and op in {"pause", "reset", "delete"}:
            gen = payload.get("generation")
            if not isinstance(gen, int) or isinstance(gen, bool) or gen < 1:
                raise ValueError("generation must be a positive integer")
            target_state = {"pause": "paused", "reset": "reset", "delete": "deleted"}[op]
            workers = WorkerRepository(database_url=database_url)
            new_gen = workers.set_state(scope, worker_id, gen, target_state)
            return respond(200, {
                "workerId": worker_id,
                "generation": new_gen,
                "status": "idle" if op == "reset" else target_state,
            })
        return None

    # 3. Actions: GET /background/actions, POST /background/actions/{id}/decision
    if path == "/background/actions" and method == "GET":
        with repo._connect() as connection, connection.cursor() as cursor:
            repo._owner(cursor, scope)
            cursor.execute(
                """SELECT * FROM vault_private.vault_background_actions
                   WHERE user_id=%s AND workspace_id=%s
                     AND state='pending' AND expires_at > now()
                   ORDER BY created_at DESC, action_id DESC""",
                (scope.user_id, scope.workspace_id),
            )
            rows = cursor.fetchall()
        return respond(200, {"items": [_action_item_payload(principal, r) for r in rows]})

    if path.startswith("/background/actions/"):
        suffix = path.removeprefix("/background/actions/").strip("/")
        action_id, _, op = suffix.partition("/")
        if method == "POST" and action_id and op == "decision":
            if set(payload).intersection(_FORBIDDEN_DECISION_KEYS):
                raise ValueError("Untrusted approval fields are not accepted")
            action_hash = str(payload.get("actionHash") or payload.get("action_hash") or "").strip()
            choice = str(payload.get("choice") or "").strip()
            decision_id = str(payload.get("decisionId") or payload.get("decision_id") or "").strip()
            if not action_hash or not choice or not decision_id:
                raise ValueError("actionHash, choice, and decisionId are required")

            decision = ApprovalDecision(
                action_id=action_id,
                action_hash=action_hash,
                choice=choice,
                actor_user_id=principal.user_id,
                workspace_id=principal.workspace_id,
                channel="browser",
                channel_generation=principal.session_id,
                decision_id=decision_id,
            )
            actions = BackgroundActions(database_url=database_url)
            recorded_decision_id = actions.decide(principal, decision)

            with repo._connect() as connection, connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM vault_private.vault_background_actions
                       WHERE user_id=%s AND workspace_id=%s AND action_id=%s""",
                    (scope.user_id, scope.workspace_id, action_id),
                )
                row = cursor.fetchone()

            if row is None:
                raise BackgroundRunAuthorizationError("Action unavailable")

            result_payload: dict[str, Any] = {
                "actionId": action_id,
                "decisionId": recorded_decision_id,
                "state": row["state"],
            }
            coordinator = getattr(getattr(app, "_conversation_runtime", None), "background_coordinator", None)
            if choice == "allow_once":
                if row["kind"] == "worker_create":
                    worker_id = WorkerRepository(database_url=database_url).create_from_approval(decision)
                    result_payload["workerId"] = worker_id
                    result_payload["state"] = "completed"
                    role_key = (
                        (row["arguments_json"] or {}).get("role_key")
                        if isinstance(row["arguments_json"], dict)
                        else None
                    )
                    if coordinator is not None and role_key:
                        with repo._connect() as connection, connection.cursor() as cursor:
                            cursor.execute(
                                """SELECT work_id FROM vault_private.vault_background_work
                                   WHERE user_id=%s AND workspace_id=%s AND state='waiting_approval'
                                     AND worker_id IS NULL AND (request_json->'destination'->>'role_key')=%s""",
                                (scope.user_id, scope.workspace_id, role_key),
                            )
                            waiting_work = [r["work_id"] for r in cursor.fetchall()]
                        for waiting_id in waiting_work:
                            try:
                                coordinator.plan_dispatch(waiting_id)
                            except Exception as exc:
                                _LOG.warning("background_approval_dispatch_failed work_id=%s error=%s", waiting_id, type(exc).__name__)
                elif row["kind"] == "execution_grant":
                    grant_id = BackgroundAuthority(database_url=database_url).grant(
                        principal, row["arguments_json"], decision
                    )
                    result_payload["grantId"] = grant_id
                    result_payload["state"] = "completed"
                elif row["kind"] == "routine_create":
                    routine_id = BackgroundRoutines(database_url=database_url).create_from_approval(
                        principal, decision
                    )
                    result_payload["routineId"] = routine_id
                    result_payload["state"] = "completed"
                elif row.get("work_id"):
                    if coordinator is not None and coordinator.jobs.health().get("state") == "running":
                        try:
                            coordinator.jobs.resume_decided()
                        except Exception as exc:
                            _LOG.warning("background_approval_resume_failed action_id=%s work_id=%s error=%s", action_id, row.get("work_id"), type(exc).__name__)
                    else:
                        try:
                            work_scope = repo.resolve_work_scope(row["work_id"])
                            repo.transition(
                                work_scope,
                                WorkState.WAITING_APPROVAL,
                                WorkState.READY,
                                {"approved_action_id": action_id, "decision_id": recorded_decision_id},
                            )
                        except Exception as exc:
                            _LOG.warning("background_approval_ready_failed action_id=%s work_id=%s error=%s", action_id, row["work_id"], type(exc).__name__)
            elif choice == "deny" and row["kind"] == "worker_create":
                role_key = (
                    (row["arguments_json"] or {}).get("role_key")
                    if isinstance(row["arguments_json"], dict)
                    else None
                )
                if role_key:
                    with repo._connect() as connection, connection.cursor() as cursor:
                        cursor.execute(
                            """SELECT work_id FROM vault_private.vault_background_work
                               WHERE user_id=%s AND workspace_id=%s AND state='waiting_approval'
                                 AND worker_id IS NULL AND (request_json->'destination'->>'role_key')=%s""",
                            (scope.user_id, scope.workspace_id, role_key),
                        )
                        waiting_work = [r["work_id"] for r in cursor.fetchall()]
                    for waiting_id in waiting_work:
                        try:
                            repo.transition(
                                repo.resolve_work_scope(waiting_id),
                                WorkState.WAITING_APPROVAL,
                                WorkState.FAILED,
                                {"denied_action_id": action_id, "role_key": role_key},
                            )
                        except Exception as exc:
                            _LOG.warning("background_denial_fail_work_failed work_id=%s error=%s", waiting_id, type(exc).__name__)
            elif choice == "deny" and row.get("work_id"):
                if coordinator is not None and coordinator.jobs.health().get("state") == "running":
                    try:
                        coordinator.jobs.resume_decided()
                    except Exception as exc:
                        _LOG.warning("background_denial_resume_failed action_id=%s work_id=%s error=%s", action_id, row.get("work_id"), type(exc).__name__)
                else:
                    try:
                        work_scope = repo.resolve_work_scope(row["work_id"])
                        repo.transition(
                            work_scope,
                            WorkState.WAITING_APPROVAL,
                            WorkState.WAITING_INPUT,
                            {"denied_action_id": action_id, "decision_id": recorded_decision_id},
                        )
                    except Exception as exc:
                        _LOG.warning("background_denial_waiting_input_failed action_id=%s work_id=%s error=%s", action_id, row["work_id"], type(exc).__name__)
            if coordinator is not None:
                try:
                    coordinator.after_owner_decision(scope, action_id)
                except Exception:
                    pass  # The decision stands; the next chat turn still sees it in its updates.
            return respond(200, result_payload)
        return None

    # 4. Work Activity: GET /background/work, GET /background/work/{id}, POST /background/work/{id}/cancel, POST /background/work/{id}/task
    if path == "/background/work" and method == "GET":
        with repo._connect() as connection, connection.cursor() as cursor:
            repo._owner(cursor, scope)
            cursor.execute(
                """SELECT w.*, k.role_key AS worker_role_key,
                          r.first_started_at AS started_at,
                          r.run_id, r.failure_code AS run_failure_code, r.completed_at AS run_completed_at,
                          r.model_turns AS run_model_turns, r.tool_calls AS run_tool_calls,
                          r.active_seconds + CASE WHEN r.state='running'
                            THEN GREATEST(0, EXTRACT(EPOCH FROM now()-r.updated_at))
                            ELSE 0 END AS elapsed_seconds
                   FROM vault_private.vault_background_work w
                   LEFT JOIN vault_private.vault_background_runs r
                     ON r.user_id=w.user_id AND r.workspace_id=w.workspace_id AND r.work_id=w.work_id
                   LEFT JOIN vault_private.vault_background_workers k
                     ON k.user_id=w.user_id AND k.workspace_id=w.workspace_id AND k.worker_id=w.worker_id
                   WHERE w.user_id=%s AND w.workspace_id=%s
                   ORDER BY (w.state IN ('running','queued','ready','waiting_approval','waiting_input')) DESC,
                            w.updated_at DESC, w.created_at DESC LIMIT 100""",
                (scope.user_id, scope.workspace_id),
            )
            rows = cursor.fetchall()
            items = [_work_item_payload(cursor, scope, r) for r in rows]
        return respond(200, {"items": items})

    if path.startswith("/background/work/"):
        suffix = path.removeprefix("/background/work/").strip("/")
        work_id, _, op = suffix.partition("/")
        if not work_id:
            return None

        if method == "GET" and not op:
            with repo._connect() as connection, connection.cursor() as cursor:
                repo._owner(cursor, scope)
                cursor.execute(
                    """SELECT w.*, k.role_key AS worker_role_key,
                              r.first_started_at AS started_at,
                              r.run_id, r.failure_code AS run_failure_code, r.completed_at AS run_completed_at,
                              r.model_turns AS run_model_turns, r.tool_calls AS run_tool_calls,
                              r.active_seconds + CASE WHEN r.state='running'
                                THEN GREATEST(0, EXTRACT(EPOCH FROM now()-r.updated_at))
                                ELSE 0 END AS elapsed_seconds
                       FROM vault_private.vault_background_work w
                       LEFT JOIN vault_private.vault_background_runs r
                         ON r.user_id=w.user_id AND r.workspace_id=w.workspace_id AND r.work_id=w.work_id
                       LEFT JOIN vault_private.vault_background_workers k
                         ON k.user_id=w.user_id AND k.workspace_id=w.workspace_id AND k.worker_id=w.worker_id
                       WHERE w.user_id=%s AND w.workspace_id=%s AND w.work_id=%s""",
                    (scope.user_id, scope.workspace_id, work_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise BackgroundRunAuthorizationError("Work is not available in this scope")
                item = _work_item_payload(cursor, scope, row)
                req_wrapper = row["request_json"] if isinstance(row["request_json"], dict) else {}
                req = req_wrapper.get("request") if isinstance(req_wrapper.get("request"), dict) else {}
                item["brief"] = {
                    "objective": req.get("objective"),
                    "successCriteria": list(req.get("success_criteria") or []),
                    "expectedResult": req.get("expected_result"),
                    "contextSummary": req.get("context_summary"),
                }
                cursor.execute(
                    """SELECT event_id, payload_json, created_at
                       FROM vault_private.vault_background_events
                       WHERE user_id=%s AND workspace_id=%s AND source_kind='result_delivery'
                         AND state='processed' AND source_id LIKE %s
                       ORDER BY created_at DESC""",
                    (scope.user_id, scope.workspace_id, f"{work_id}:%"),
                )
                deliveries = []
                for d in cursor.fetchall():
                    pj = d["payload_json"] if isinstance(d["payload_json"], dict) else {}
                    deliveries.append({
                        "deliveryId": d["event_id"],
                        "deliveredVia": pj.get("delivered_via"),
                        "projection": pj.get("projection"),
                        "createdAt": d["created_at"].isoformat(),
                    })
                item["deliveries"] = deliveries
                reasoning = []
                if row.get("run_id"):
                    cursor.execute(
                        """SELECT event_type, detail_json, created_at
                           FROM vault_private.vault_background_run_events
                           WHERE user_id=%s AND workspace_id=%s AND run_id=%s
                             AND event_type IN ('reasoning_summary','agent_evidence')
                           ORDER BY event_index""",
                        (scope.user_id, scope.workspace_id, row["run_id"]),
                    )
                    reasoning = [{"type": e["event_type"], "createdAt": e["created_at"].isoformat(),
                                  "detail": e["detail_json"] if isinstance(e["detail_json"], dict) else {}}
                                 for e in cursor.fetchall()]
                item["reasoningEntries"] = reasoning
            return respond(200, item)

        if method == "POST" and op == "task":
            raw_task_id = payload.get("taskId") if "taskId" in payload else payload.get("task_id")
            with repo._connect() as connection, connection.cursor() as cursor:
                repo._owner(cursor, scope)
                cursor.execute(
                    """SELECT * FROM vault_private.vault_background_work
                       WHERE user_id=%s AND workspace_id=%s AND work_id=%s FOR UPDATE""",
                    (scope.user_id, scope.workspace_id, work_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise BackgroundRunAuthorizationError("Work is not available in this scope")
                task_id_val: str | None = None
                if raw_task_id is not None:
                    if not isinstance(raw_task_id, str) or not raw_task_id.strip():
                        raise ValueError("taskId must be a non-empty string or null")
                    task_id_val = raw_task_id.strip()
                    _validate_task_in_scope(cursor, scope, task_id_val)
                cursor.execute(
                    """UPDATE vault_private.vault_background_work
                       SET task_id=%s, updated_at=now()
                       WHERE user_id=%s AND workspace_id=%s AND work_id=%s
                       RETURNING *""",
                    (task_id_val, scope.user_id, scope.workspace_id, work_id),
                )
                updated_row = cursor.fetchone()
                item = _work_item_payload(cursor, scope, updated_row)
            return respond(200, item)

        if method == "POST" and op == "cancel":
            with repo._connect() as connection, connection.cursor() as cursor:
                repo._owner(cursor, scope)
                cursor.execute(
                    """SELECT * FROM vault_private.vault_background_work
                       WHERE user_id=%s AND workspace_id=%s AND work_id=%s FOR UPDATE""",
                    (scope.user_id, scope.workspace_id, work_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise BackgroundRunAuthorizationError("Work is not available in this scope")
                coordinator = getattr(getattr(app, "_conversation_runtime", None), "background_coordinator", None)
                if coordinator is not None:
                    coordinator.jobs.cancel(connection, work_id)
                    cursor.execute("SELECT * FROM vault_private.vault_background_work WHERE work_id=%s", (work_id,))
                    row = cursor.fetchone()
                elif row["state"] not in {"completed", "failed", "cancelled", "unknown"}:
                    cursor.execute(
                        """UPDATE vault_private.vault_background_work
                           SET state='cancelled', updated_at=now()
                           WHERE user_id=%s AND workspace_id=%s AND work_id=%s
                           RETURNING *""",
                        (scope.user_id, scope.workspace_id, work_id),
                    )
                    row = cursor.fetchone()
                cursor.execute(
                    """UPDATE vault_private.vault_background_runs
                       SET cancellation_requested=true,
                           state=CASE WHEN state IN ('completed','failed','cancelled') THEN state ELSE 'cancelled' END,
                           updated_at=now()
                       WHERE user_id=%s AND workspace_id=%s AND work_id=%s""",
                    (scope.user_id, scope.workspace_id, work_id),
                )
                cursor.execute(
                    """UPDATE vault_private.vault_background_actions
                       SET state='expired', updated_at=now()
                       WHERE user_id=%s AND workspace_id=%s AND work_id=%s AND state IN ('pending','approved')""",
                    (scope.user_id, scope.workspace_id, work_id),
                )
                if row.get("worker_id"):
                    cursor.execute(
                        """UPDATE vault_private.vault_background_workers
                           SET status='idle', updated_at=now()
                           WHERE user_id=%s AND workspace_id=%s AND worker_id=%s AND status='active'""",
                        (scope.user_id, scope.workspace_id, row["worker_id"]),
                    )
                item = _work_item_payload(cursor, scope, row)
            try:
                BackgroundRoutines(database_url=database_url).cancel_followups_for_work(
                    scope, work_id, reason="user_cancelled"
                )
            except Exception as exc:
                _LOG.warning("background_cancel_followups_failed work_id=%s error=%s", work_id, type(exc).__name__)
            return respond(200, item)

        return None

    # 5. Routines: GET/POST /background/routines, POST /background/routines/{id}/{pause|cancel}
    if path == "/background/routines":
        routines = BackgroundRoutines(database_url=database_url)
        if method == "GET":
            with repo._connect() as connection, connection.cursor() as cursor:
                repo._owner(cursor, scope)
                cursor.execute(
                    """SELECT * FROM vault_private.vault_background_routines
                       WHERE user_id=%s AND workspace_id=%s AND status<>'deleted'
                       ORDER BY created_at DESC, routine_id DESC""",
                    (scope.user_id, scope.workspace_id),
                )
                rows = cursor.fetchall()
            items = []
            for r in rows:
                tmpl = r["template_json"] if isinstance(r["template_json"], dict) else {}
                req = tmpl.get("request") if isinstance(tmpl.get("request"), dict) else {}
                items.append({
                    "routineId": r["routine_id"],
                    "version": int(r["version"]),
                    "rule": dict(r["rule_json"] or {}),
                    "timezone": r["timezone"],
                    "nextDueAt": r["next_due_at"].isoformat() if r["next_due_at"] else None,
                    "grantId": r["grant_id"],
                    "status": r["status"],
                    "objective": str(req.get("objective") or "Scheduled routine"),
                    "createdAt": r["created_at"].isoformat(),
                    "updatedAt": r["updated_at"].isoformat(),
                })
            return respond(200, {"items": items})

        if method == "POST":
            rule = payload.get("rule")
            timezone_name = str(payload.get("timezone") or "").strip()
            template = payload.get("template")
            grant_id = str(payload.get("grantId") or payload.get("grant_id") or "").strip()
            if not isinstance(rule, dict) or not isinstance(template, dict) or not timezone_name or not grant_id:
                raise ValueError("rule, timezone, template, and grantId are required")
            if bool(payload.get("propose")):
                prepared = routines.propose(
                    principal,
                    rule=rule,
                    timezone=timezone_name,
                    template=template,
                    grant_id=grant_id,
                )
                with repo._connect() as connection, connection.cursor() as cursor:
                    cursor.execute(
                        """SELECT * FROM vault_private.vault_background_actions
                           WHERE user_id=%s AND workspace_id=%s AND action_id=%s""",
                        (scope.user_id, scope.workspace_id, prepared.action_id),
                    )
                    action_row = cursor.fetchone()
                return respond(202, {
                    "action": _action_item_payload(principal, action_row),
                    "status": "waiting_approval",
                })
            routine_id = routines.create(
                principal,
                rule=rule,
                timezone=timezone_name,
                template=template,
                grant_id=grant_id,
            )
            return respond(201, {"routineId": routine_id, "status": "active"})
        return None

    if path.startswith("/background/routines/"):
        suffix = path.removeprefix("/background/routines/").strip("/")
        routine_id, _, op = suffix.partition("/")
        routines = BackgroundRoutines(database_url=database_url)
        if method == "POST" and routine_id and op == "pause":
            routines.pause(principal, routine_id)
            return respond(200, {"routineId": routine_id, "status": "paused"})
        if method == "POST" and routine_id and op == "cancel":
            routines.cancel(principal, routine_id)
            return respond(200, {"routineId": routine_id, "status": "deleted"})
        return None

    return None
