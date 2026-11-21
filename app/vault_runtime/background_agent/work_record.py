"""The record of one piece of background work, as the coordinator sees it.

Who started it (a routine and its schedule, the owner in a chat, or a direct request through
Vault's API), why (the request), who did it (the specialist), what it did (model turns and the
tools it used), how it ended and why, and what kind of problem a failure is. Built from Vault's
own run records; nothing here comes from the model.
"""
from __future__ import annotations

from typing import Any

# What a failure means for the coordinator's next step.
_NEEDS_OWNER = {"approval_denied", "approval_expired", "not_granted", "tool_not_granted",
                "authenticationerror", "permissiondeniederror"}
_TASK = {"agent_incomplete", "budget_exhausted", "tool_budget_exceeded", "max_model_turns_exceeded",
         "run_timeout"}
_TEMPORARY = {"ratelimiterror", "apitimeouterror", "apiconnectionerror", "internalservererror",
              "serviceunavailableerror", "timeout", "timeouterror"}
_UNCONFIRMED = {"effect_outcome_unknown", "execution_outcome_unknown", "stalled_outcome_unknown",
                "cancelled_during_effect", "runtime_interrupted", "execution_interrupted"}

FAILURE_KINDS = {
    "needs_owner": "The owner has to act (an approval, a permission or a sign-in). Ask them; retrying alone won't help.",
    "task": "The work itself could not be done as asked. The reason says why; adjust the task or ask the owner.",
    "temporary": "A temporary provider problem (rate limit, timeout, outage). Retrying later usually works.",
    "unconfirmed": "Vault cannot confirm whether an action happened before the run stopped. Check before redoing it.",
    "vault": "A problem inside Vault, not in the task. Retrying will likely fail the same way; tell the owner once.",
}


def failure_kind(code: str | None) -> str | None:
    if not code:
        return None
    code = code.lower()
    for kind, codes in (("needs_owner", _NEEDS_OWNER), ("task", _TASK), ("temporary", _TEMPORARY),
                        ("unconfirmed", _UNCONFIRMED)):
        if code in codes:
            return kind
    return "vault"


def _reason(message: str | None) -> str:
    """The first meaningful line of a failure, short. Model provider errors can be long."""
    text = " ".join((message or "").split())
    return text[:400]


def _started_by(cursor: Any, work: dict[str, Any]) -> dict[str, object]:
    source = str(work.get("source_key") or "")
    routine_id = work.get("routine_id")
    if routine_id or source.startswith("routine:"):
        routine_id = routine_id or source.split(":", 2)[1]
        cursor.execute(
            """SELECT rule_json, timezone, created_at, template_json->'request'->>'goal_type' AS goal_type,
                      template_json->'destination'->>'conversation_id' AS conversation_id
               FROM vault_private.vault_background_routines WHERE routine_id=%s AND user_id=%s AND workspace_id=%s""",
            (routine_id, work["user_id"], work["workspace_id"]),
        )
        routine = cursor.fetchone()
        started: dict[str, object] = {"kind": "routine", "routineId": routine_id}
        if routine:
            started.update(schedule=routine["rule_json"], timezone=routine["timezone"],
                           routineCreatedAt=routine["created_at"].isoformat() if routine["created_at"] else None,
                           routineKind=routine["goal_type"] or "specialist_routine",
                           setUpInConversation=routine["conversation_id"])
        return started
    if source.startswith("explicit_goal:chat:"):
        return {"kind": "owner_request_in_chat", "conversationId": source.split(":", 2)[2].split(":")[0]}
    if source.startswith("direct_run:"):
        return {"kind": "direct_request",
                "note": "Started through Vault's API with the owner's sign-in, not from a chat "
                        "(for example a connected app or agent). The request text may say who sent it."}
    return {"kind": source.split(":", 1)[0] or "unknown"}


def work_record(cursor: Any, *, user_id: str, workspace_id: str, work_id: str) -> dict[str, object] | None:
    """The record for one piece of work, or None when it does not exist in this scope.
    ``cursor`` must return rows as dictionaries."""
    cursor.execute(
        """SELECT w.work_id, w.user_id, w.workspace_id, w.source_key, w.state, w.routine_id, w.parent_work_id,
                  w.request_json, w.result_json, w.created_at, w.updated_at, wk.role_key
           FROM vault_private.vault_background_work w
           LEFT JOIN vault_private.vault_background_workers wk ON wk.worker_id=w.worker_id
           WHERE w.work_id=%s AND w.user_id=%s AND w.workspace_id=%s""",
        (work_id, user_id, workspace_id),
    )
    work = cursor.fetchone()
    if work is None:
        return None
    request = (work["request_json"] or {}).get("request") or {}
    result = work["result_json"] if isinstance(work["result_json"], dict) else {}
    cursor.execute(
        """SELECT run_id, state, failure_code, failure_message, model_turns, tool_calls, created_at, completed_at
           FROM vault_private.vault_background_runs WHERE work_id=%s AND user_id=%s AND workspace_id=%s
           ORDER BY created_at""",
        (work_id, user_id, workspace_id),
    )
    runs = cursor.fetchall()
    last = runs[-1] if runs else {}
    tools: list[str] = []
    failed_tools = 0
    if runs:
        cursor.execute(
            """SELECT event_type, detail_json->>'name' AS name FROM vault_private.vault_background_run_events
               WHERE run_id = ANY(%s) AND event_type IN ('tool_started','tool_failed')""",
            ([run["run_id"] for run in runs],),
        )
        for row in cursor.fetchall():
            if row["event_type"] == "tool_failed":
                failed_tools += 1
            elif row["name"] and row["name"] not in tools:
                tools.append(str(row["name"]))
    code = last.get("failure_code") if work["state"] in {"failed", "unknown"} else None
    kind = failure_kind(code) if work["state"] in {"failed", "unknown"} else None
    return {
        "workId": work["work_id"],
        "state": work["state"],
        "startedBy": _started_by(cursor, work),
        "request": str(request.get("objective") or "")[:400],
        "originalRequest": str(request.get("original_request") or "")[:400],
        "doneBy": work["role_key"] or "Background Agent",
        "outcome": {
            "state": work["state"],
            "summary": str(result.get("summary") or "")[:600],
            **({"failureCode": code, "failureKind": kind, "meaning": FAILURE_KINDS.get(kind or ""),
                "reason": _reason(last.get("failure_message"))} if kind else {}),
        },
        "activity": {"attempts": len(runs), "modelTurns": sum(int(r["model_turns"] or 0) for r in runs),
                     "toolCalls": sum(int(r["tool_calls"] or 0) for r in runs), "toolsUsed": tools[:20],
                     "toolFailures": failed_tools},
        "partOf": work["parent_work_id"],
        "startedAt": work["created_at"].isoformat() if work["created_at"] else None,
        "finishedAt": (last.get("completed_at") or work["updated_at"]).isoformat()
        if (last.get("completed_at") or work["updated_at"]) else None,
    }


def render(record: dict[str, object]) -> str:
    """Compact text for a wake message (the full record is in coordinatorState)."""
    started = record.get("startedBy") or {}
    outcome = record.get("outcome") or {}
    activity = record.get("activity") or {}
    who = {"routine": f"routine {started.get('routineId')} (schedule {started.get('schedule')}, {started.get('timezone')})",
           "owner_request_in_chat": "the owner, in a chat",
           "direct_request": "a direct request through Vault's API (not a chat)"}.get(
        str(started.get("kind")), str(started.get("kind")))
    lines = [f"Started by: {who}", f"Done by: {record.get('doneBy')}", f"Request: {record.get('request')}",
             f"Outcome: {outcome.get('state')}"]
    if outcome.get("failureKind"):
        lines += [f"Failure kind: {outcome.get('failureKind')} - {outcome.get('meaning')}",
                  f"Reason: {outcome.get('reason') or outcome.get('failureCode')}"]
    lines.append(f"Activity: {activity.get('attempts')} attempt(s), {activity.get('modelTurns')} model turns, "
                 f"{activity.get('toolCalls')} tool calls"
                 + (f" ({', '.join(activity.get('toolsUsed') or [])})" if activity.get("toolsUsed") else "")
                 + (f", {activity.get('toolFailures')} tool failures" if activity.get("toolFailures") else ""))
    lines.append(f"When: {record.get('startedAt')} to {record.get('finishedAt')}")
    return "\n".join(lines)
