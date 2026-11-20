"""Coordinator-approved result delivery, quiet suppression, and source-ref invalidation (Task 6).

Adapted from Rakazo (`elie222/rakazo` @ `83db73c2e5fe5002487f4dc1cf488fe601a34c25`, Apache-2.0):
- `packages/server/src/AgentSession/run-notifications.ts`: one-result delivery dedup, quiet-outcome
  suppression, and originating-conversation vs notification fallback.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from .coordination_contracts import WorkScope, WorkState
from .coordination_repository import CoordinationRepository, _json
from .errors import BackgroundRunAuthorizationError, BackgroundRunConflictError

_LOG = logging.getLogger(__name__)


class BackgroundResults:
    def __init__(self, *, database_url: str, notifications: Any = None) -> None:
        self._database_url = database_url
        self._repo = CoordinationRepository(database_url=database_url)
        self._notifications = notifications

    def deliver(self, scope: WorkScope, destination: dict[str, object], result_id: str) -> str:
        if not isinstance(destination, dict) or not result_id or not result_id.strip():
            raise ValueError("Delivery requires a destination object and result_id")
        result_id = result_id.strip()
        delivery_key = f"{scope.work_id}:{scope.intent_version}:{result_id}"

        with self._repo._connect() as connection, connection.cursor() as cursor:
            row = self._repo._work(cursor, scope)
            state = row["state"]
            if state == WorkState.CANCELLED.value or state not in {
                WorkState.COMPLETED.value,
                WorkState.FAILED.value,
                WorkState.UNKNOWN.value,
                WorkState.WAITING_INPUT.value,
            }:
                raise BackgroundRunAuthorizationError("Work is not in a deliverable state")

            result_json = row["result_json"] if isinstance(row["result_json"], dict) else {}
            source_refs = set()
            for ref in result_json.get("artifact_references") or []:
                if isinstance(ref, str) and ref:
                    source_refs.add(ref)
            for ref in result_json.get("source_refs") or []:
                if isinstance(ref, str) and ref:
                    source_refs.add(ref)

            cursor.execute(
                """SELECT source_refs_json FROM vault_private.vault_background_sessions
                   WHERE user_id=%s AND workspace_id=%s AND work_id=%s AND intent_version=%s""",
                (scope.user_id, scope.workspace_id, scope.work_id, scope.intent_version),
            )
            sess = cursor.fetchone()
            if sess and isinstance(sess["source_refs_json"], list):
                for ref in sess["source_refs_json"]:
                    if isinstance(ref, str) and ref:
                        source_refs.add(ref)

            # Check whether this work or any referenced source was invalidated
            invalidation_keys = [f"{scope.work_id}:*"] + [
                f"{scope.work_id}:{ref}" for ref in source_refs
            ] + [f"source:{ref}" for ref in source_refs]
            cursor.execute(
                """SELECT 1 FROM vault_private.vault_background_events
                   WHERE user_id=%s AND workspace_id=%s AND source_kind='source_invalidated'
                     AND source_id = ANY(%s) LIMIT 1""",
                (scope.user_id, scope.workspace_id, invalidation_keys),
            )
            if cursor.fetchone() is not None:
                raise BackgroundRunAuthorizationError("Result depends on an invalidated source")

            # Idempotent delivery check
            cursor.execute(
                """SELECT event_id, state, payload_json FROM vault_private.vault_background_events
                   WHERE user_id=%s AND workspace_id=%s AND source_kind='result_delivery' AND source_id=%s
                   FOR UPDATE""",
                (scope.user_id, scope.workspace_id, delivery_key),
            )
            existing = cursor.fetchone()
            if existing is not None:
                if existing["state"] == "cancelled":
                    raise BackgroundRunAuthorizationError("Result delivery was invalidated")
                return str(existing["event_id"])

            schedule_meta = destination.get("schedule_meta") or {}
            quiet = schedule_meta.get("kind") != "manual" and bool(
                destination.get("quiet") or (
                    state == WorkState.COMPLETED.value
                    and schedule_meta
                    and result_json.get("quiet") is True
                )
            )
            summary = str(result_json.get("summary") or "")
            if not summary and state in {WorkState.FAILED.value, WorkState.UNKNOWN.value}:
                request = row["request_json"].get("request", {})
                objective = str(request.get("objective") or "Background work")[:180]
                if state == WorkState.FAILED.value:
                    summary = f"Background run failed: {objective}"
                else:
                    summary = f"Background run ended with an unconfirmed outcome: {objective}"
            projection = {
                "work_id": scope.work_id,
                "intent_version": scope.intent_version,
                "result_id": result_id,
                "state": state,
                "summary": summary,
                "artifact_references": [
                    str(r) for r in (result_json.get("artifact_references") or []) if isinstance(r, str)
                ],
                "verification_summary": str(result_json.get("verification_summary") or ""),
                "cards": result_json.get("cards") if isinstance(result_json.get("cards"), list) else [],
            }

            delivered_via = "activity"
            conversation_ordinal = None
            conversation_id = destination.get("conversation_id")
            if quiet:
                delivered_via = "quiet_suppressed"
            elif isinstance(conversation_id, str) and conversation_id.strip():
                conversation_id = conversation_id.strip()
                cursor.execute(
                    """SELECT user_id, workspace_id, state, next_turn_ordinal
                       FROM vault_private.vault_conversations WHERE conversation_id=%s FOR UPDATE""",
                    (conversation_id,),
                )
                conv = cursor.fetchone()
                if conv is None or (conv["user_id"], conv["workspace_id"]) != (scope.user_id, scope.workspace_id):
                    raise BackgroundRunAuthorizationError("Destination conversation is outside work scope")
                if conv["state"] == "open":
                    delivered_via = "conversation"
                    conversation_ordinal = conv["next_turn_ordinal"]
                    cursor.execute(
                        """UPDATE vault_private.vault_conversations
                           SET next_turn_ordinal=next_turn_ordinal+1
                           WHERE conversation_id=%s""",
                        (conversation_id,),
                    )
                else:
                    # Closed conversation falls back to notification/work link rather than injecting into another chat
                    delivered_via = "notification_fallback"

            elif destination.get("kind") == "notification":
                delivered_via = "notification"

            delivery_id = str(uuid4())
            payload = _json({
                "delivery_id": delivery_id,
                "delivered_via": delivered_via,
                "conversation_ordinal": conversation_ordinal,
                "destination": {
                    k: v for k, v in destination.items()
                    if k in {"kind", "conversation_id", "turn_id", "voice_session_id", "role_key", "internal", "goal_type"}
                    and isinstance(v, (str, int, bool, type(None)))
                },
                "projection": projection,
                "source_refs": sorted(source_refs),
            })
            cursor.execute(
                """INSERT INTO vault_private.vault_background_events
                   (event_id, user_id, workspace_id, source_kind, source_id, payload_json, state)
                   VALUES (%s, %s, %s, 'result_delivery', %s, %s, 'processed')""",
                (delivery_id, scope.user_id, scope.workspace_id, delivery_key, Jsonb(payload)),
            )

        if (not quiet and not destination.get("internal")
                and delivered_via in {"conversation", "notification", "notification_fallback"} and self._notifications is not None):
            try:
                title = f"Background work {state}"
                body = projection["summary"] or f"Background work {scope.work_id} finished ({state})."
                self._notifications.create(
                    user_id=scope.user_id,
                    workspace_id=scope.workspace_id,
                    kind="background_result",
                    title=title[:160],
                    body=body[:1000],
                    payload={"workId": scope.work_id, "deliveryId": delivery_id, "state": state,
                             "conversationId": conversation_id},
                )
            except Exception as exc:
                _LOG.warning("background_result_notification_failed work_id=%s delivery_id=%s error=%s", scope.work_id, delivery_id, type(exc).__name__)
        return delivery_id

    def invalidate(self, scope: WorkScope, source_ref: str) -> None:
        if not isinstance(source_ref, str) or not source_ref.strip():
            raise ValueError("source_ref must be a non-empty string")
        source_ref = source_ref.strip()
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            for key in (f"{scope.work_id}:{source_ref}", f"source:{source_ref}"):
                cursor.execute(
                    """INSERT INTO vault_private.vault_background_events
                       (event_id, user_id, workspace_id, source_kind, source_id, payload_json, state)
                       VALUES (%s, %s, %s, 'source_invalidated', %s, %s, 'processed')
                       ON CONFLICT(user_id, workspace_id, source_kind, source_id) DO UPDATE SET
                         state='processed', payload_json=EXCLUDED.payload_json""",
                    (
                        str(uuid4()),
                        scope.user_id,
                        scope.workspace_id,
                        key,
                        Jsonb({"work_id": scope.work_id, "source_ref": source_ref}),
                    ),
                )
            cursor.execute(
                """UPDATE vault_private.vault_background_sessions
                   SET checkpoint_json=NULL, history_json='[]'::jsonb, source_refs_json='[]'::jsonb, updated_at=now()
                   WHERE user_id=%s AND workspace_id=%s
                     AND (work_id=%s OR source_refs_json ? %s)""",
                (scope.user_id, scope.workspace_id, scope.work_id, source_ref),
            )
            cursor.execute(
                """UPDATE vault_private.vault_background_runs
                   SET checkpoint_json=NULL, updated_at=now()
                   WHERE user_id=%s AND workspace_id=%s AND work_id=%s""",
                (scope.user_id, scope.workspace_id, scope.work_id),
            )
            cursor.execute(
                """UPDATE vault_private.vault_background_events
                   SET state='cancelled'
                   WHERE user_id=%s AND workspace_id=%s AND source_kind='result_delivery'
                     AND (source_id LIKE %s OR payload_json->'source_refs' ? %s)""",
                (scope.user_id, scope.workspace_id, f"{scope.work_id}:%", source_ref),
            )
