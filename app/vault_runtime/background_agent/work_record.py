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


_SYSTEM_TURN = "vault-wake:"
_VOICE_PREFIX = "[Spoken on a voice call]"
_AUTOMATED = "[Automated message from Vault, not from the user]"
# Work that only wakes the coordinator in its chat (its own routines, follow-ups and reminders).
_COORDINATOR_GOALS = frozenset({"self_routine", "follow_up", "reminder"})


def _coordinator_turn(cursor: Any, work: dict[str, Any], conversation_id: str | None,
                      objective: str) -> dict[str, object] | None:
    """The chat turn in which Vault woke the coordinator to do this work, and what it did there:
    its tool calls (from the turn's own events), its reply and how the turn ended."""
    if not conversation_id or not objective.strip():
        return None
    cursor.execute("SELECT to_regclass('vault_private.vault_conversation_turns') IS NOT NULL AS present")
    present = cursor.fetchone()
    if not present or not present["present"]:
        return None
    cursor.execute(
        """SELECT t.turn_id, t.state, t.created_at, t.updated_at, c.title
           FROM vault_private.vault_conversation_turns t
           JOIN vault_private.vault_conversations c
             ON c.user_id=t.user_id AND c.workspace_id=t.workspace_id AND c.conversation_id=t.conversation_id
           WHERE t.user_id=%s AND t.workspace_id=%s AND t.conversation_id=%s
             AND t.submission_key LIKE 'vault-wake:%%' AND t.created_at >= %s - interval '5 seconds'
             AND t.created_at < %s + interval '6 hours' AND strpos(t.input_text, %s) > 0
           ORDER BY t.created_at LIMIT 1""",
        (work["user_id"], work["workspace_id"], conversation_id, work["updated_at"], work["updated_at"],
         objective.strip()[:160]),
    )
    turn = cursor.fetchone()
    if turn is None:
        return None
    cursor.execute(
        """SELECT kind, payload FROM vault_private.vault_conversation_events
           WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND turn_id=%s
             AND kind IN ('tool_status','model_response','assistant_final')
           ORDER BY sequence""",
        (work["user_id"], work["workspace_id"], conversation_id, turn["turn_id"]),
    )
    names: list[str] = []
    calls = failures = responses = 0
    reply = ""
    for row in cursor.fetchall():
        payload = row["payload"] if isinstance(row["payload"], dict) else {}
        if row["kind"] == "model_response":
            responses += 1
        elif row["kind"] == "assistant_final":
            reply = str(payload.get("text") or "")
        elif payload.get("state") == "invoking":
            calls += 1
            if payload.get("name") and payload["name"] not in names:
                names.append(str(payload["name"]))
        elif payload.get("state") in {"denied", "failed"} or (
                payload.get("state") == "succeeded" and payload.get("isError")):
            failures += 1
    return {
        "chat": turn["title"] or "untitled chat", "conversationId": conversation_id, "turnId": turn["turn_id"],
        "turnState": turn["state"], "at": turn["created_at"].isoformat(),
        "reply": " ".join(reply.split())[:600],
        "activity": {"attempts": 1, "modelTurns": responses, "toolCalls": calls, "toolsUsed": names[:20],
                     "toolFailures": failures},
    }


def turn_origin(cursor: Any, turn_id: str | None) -> dict[str, object] | None:
    """Who acted in a chat turn: the owner (and where), or the coordinator on its own in a turn
    Vault started (a routine, a result or a follow-up woke it)."""
    if not turn_id:
        return None
    cursor.execute(
        """SELECT submission_key, input_text, created_at FROM vault_private.vault_conversation_turns
           WHERE turn_id=%s""", (turn_id,),
    )
    turn = cursor.fetchone()
    if turn is None:
        return None
    key, text = str(turn["submission_key"] or ""), str(turn["input_text"] or "")
    at = turn["created_at"].isoformat() if turn["created_at"] else None
    if key.startswith(_SYSTEM_TURN):
        woken_by = " ".join(text.replace(_AUTOMATED, "").split())[:200]
        return {"by": "coordinator", "how": "on its own, in a turn Vault started", "wokenBy": woken_by, "at": at}
    channel = "voice call" if text.startswith(_VOICE_PREFIX) else "Link" if key.startswith("link:") else "web chat"
    return {"by": "owner", "how": f"a message in {channel}", "message": " ".join(text.split())[:200], "at": at}


def _routine_setup(cursor: Any, work: dict[str, Any], routine_id: str) -> dict[str, object] | None:
    cursor.execute(
        """SELECT origin_json->>'turn_id' AS turn_id, created_at FROM vault_private.vault_background_actions
           WHERE user_id=%s AND workspace_id=%s AND kind='routine_create' AND receipt_json->>'routine_id'=%s
           ORDER BY created_at DESC LIMIT 1""",
        (work["user_id"], work["workspace_id"], routine_id),
    )
    action = cursor.fetchone()
    return turn_origin(cursor, action["turn_id"]) if action else None


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
        setup = _routine_setup(cursor, work, str(routine_id))
        if setup is not None:
            started["setUpBy"] = setup
        return started
    if source.startswith("explicit_goal:chat:"):
        destination = (work.get("request_json") or {}).get("destination") or {}
        started = {"kind": "chat", "conversationId": source.split(":", 2)[2].split(":")[0]}
        origin = turn_origin(cursor, destination.get("turn_id"))
        if origin is not None:
            started["decidedBy"] = origin
        return started
    if source.startswith("direct_run:"):
        run_id = source.split(":", 1)[1].split(":")[0]
        cursor.execute("SELECT to_regclass('vault_private.vault_a2a_inbound_tasks') IS NOT NULL AS present")
        a2a = cursor.fetchone()
        if a2a and a2a["present"]:
            cursor.execute("SELECT 1 FROM vault_private.vault_a2a_inbound_tasks WHERE run_id=%s", (run_id,))
        if a2a and a2a["present"] and cursor.fetchone() is not None:
            return {"kind": "connected_agent",
                    "note": "A message from a connected agent over A2A. Vault cannot tell which agent: they "
                            "share one inbound key, so only the message text names the sender."}
        return {"kind": "direct_request",
                "note": "Started through Vault's API with the owner's sign-in, not from a chat. "
                        "The request text may say who sent it."}
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
    done_by = work["role_key"] or "Background Agent"
    summary = str(result.get("summary") or "")[:600]
    activity = {"attempts": len(runs), "modelTurns": sum(int(r["model_turns"] or 0) for r in runs),
                "toolCalls": sum(int(r["tool_calls"] or 0) for r in runs), "toolsUsed": tools[:20],
                "toolFailures": failed_tools}
    handled = None
    if request.get("goal_type") in _COORDINATOR_GOALS:
        # The run only woke the coordinator; the work happened in that chat turn.
        destination = (work["request_json"] or {}).get("destination") or {}
        handled = _coordinator_turn(cursor, work, destination.get("conversation_id"),
                                    str(request.get("objective") or ""))
        done_by = "the coordinator (you), in its chat"
        if handled is None:
            summary = "Vault woke the coordinator to do this in its chat; no turn for it has run yet."
            activity = {"attempts": 0, "modelTurns": 0, "toolCalls": 0, "toolsUsed": [], "toolFailures": 0}
        else:
            done_by = f"the coordinator (you), in chat \"{handled['chat']}\""
            summary = handled.pop("reply") or summary
            activity = handled.pop("activity")
    return {
        "workId": work["work_id"],
        "state": work["state"],
        "startedBy": _started_by(cursor, work),
        "request": str(request.get("objective") or "")[:400],
        "originalRequest": str(request.get("original_request") or "")[:400],
        "doneBy": done_by,
        **({"handledIn": handled} if handled is not None else {}),
        "outcome": {
            "state": work["state"],
            "summary": summary,
            **({"failureCode": code, "failureKind": kind, "meaning": FAILURE_KINDS.get(kind or ""),
                "reason": _reason(last.get("failure_message"))} if kind else {}),
        },
        "activity": activity,
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
    def actor(origin: object) -> str:
        if not isinstance(origin, dict):
            return "unknown"
        if origin.get("by") == "coordinator":
            return f"the coordinator {origin.get('how')} (woken by: {origin.get('wokenBy')})"
        return f"the owner, {origin.get('how')}: \"{origin.get('message')}\""

    kind = str(started.get("kind"))
    if kind == "routine":
        who = (f"routine {started.get('routineId')} on its schedule ({started.get('schedule')}, "
               f"{started.get('timezone')})"
               + (f"; set up by {actor(started['setUpBy'])}" if started.get("setUpBy") else ""))
    elif kind == "chat":
        who = actor(started.get("decidedBy")) if started.get("decidedBy") else "a chat turn"
    elif kind == "connected_agent":
        who = "a connected agent over A2A (not identified)"
    elif kind == "direct_request":
        who = "a direct request through Vault's API (not a chat)"
    else:
        who = kind
    lines = [f"Started by: {who}", f"Done by: {record.get('doneBy')}", f"Request: {record.get('request')}",
             f"Outcome: {outcome.get('state')}"]
    handled = record.get("handledIn")
    if isinstance(handled, dict) and handled.get("turnState") != "completed":
        lines.append(f"Coordinator turn: {handled.get('turnState')}")
    if outcome.get("failureKind"):
        lines += [f"Failure kind: {outcome.get('failureKind')} - {outcome.get('meaning')}",
                  f"Reason: {outcome.get('reason') or outcome.get('failureCode')}"]
    lines.append(f"Activity: {activity.get('attempts')} attempt(s), {activity.get('modelTurns')} model turns, "
                 f"{activity.get('toolCalls')} tool calls"
                 + (f" ({', '.join(activity.get('toolsUsed') or [])})" if activity.get("toolsUsed") else "")
                 + (f", {activity.get('toolFailures')} tool failures" if activity.get("toolFailures") else ""))
    lines.append(f"When: {record.get('startedAt')} to {record.get('finishedAt')}")
    return "\n".join(lines)
