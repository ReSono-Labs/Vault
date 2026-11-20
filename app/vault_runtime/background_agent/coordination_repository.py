"""Canonical work/session records. Scopes come from authenticated server code, not clients."""
from __future__ import annotations

import json
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.vault_runtime.local_identity.authority import has_current_session_scope
from .coordination_contracts import OwnerScope, WorkScope, WorkRequest, WorkState, ExecutionOutcome, WORK_TRANSITIONS
from .errors import BackgroundRunAuthorizationError, BackgroundRunConflictError
from .schema import ensure_background_schema


def _json(value):
    return json.loads(json.dumps(value, allow_nan=False))


class CoordinationRepository:
    def __init__(self, *, database_url: str):
        self._database_url = database_url

    def _connect(self):
        return psycopg.connect(self._database_url, connect_timeout=5, row_factory=dict_row)

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                ensure_background_schema(cursor)

    @staticmethod
    def _owner(cursor, scope: OwnerScope) -> None:
        cursor.execute("""SELECT 1 FROM vault_private.local_workspace_memberships m
          JOIN vault_private.local_users u ON u.user_id=m.user_id
          JOIN vault_private.local_workspaces w ON w.workspace_id=m.workspace_id
          WHERE m.user_id=%s AND m.workspace_id=%s AND m.status='active'
          AND u.status='active' AND w.status='active' FOR SHARE OF m,u,w""",
          (scope.user_id, scope.workspace_id))
        if cursor.fetchone() is None:
            raise BackgroundRunAuthorizationError("Work is not available in this scope")

    @staticmethod
    def _authority(cursor, scope: OwnerScope, session_id: str | None, grant_id: str | None) -> None:
        if session_id is not None and grant_id is None:
            if has_current_session_scope(cursor, user_id=scope.user_id, workspace_id=scope.workspace_id,
                                         local_session_id=session_id, lock=True):
                return
        elif grant_id is not None and session_id is None:
            cursor.execute("""SELECT 1 FROM vault_private.vault_background_execution_grants
              WHERE user_id=%s AND workspace_id=%s AND grant_id=%s AND status='active'
              AND (expires_at IS NULL OR expires_at>now()) FOR SHARE""",
              (scope.user_id, scope.workspace_id, grant_id))
            if cursor.fetchone() is not None:
                return
        raise BackgroundRunAuthorizationError("Work execution authority is unavailable")

    def observe(self, scope: OwnerScope, source_kind: str, source_id: str, payload: dict) -> str:
        if not source_kind or not source_id or not isinstance(payload, dict):
            raise ValueError("Observation requires source identity and an object")
        payload = _json(payload)
        with self._connect() as connection, connection.cursor() as cursor:
            self._owner(cursor, scope)
            return self._event(cursor, scope, source_kind, source_id, payload)

    @staticmethod
    def _event(cursor, scope, kind, source, payload) -> str:
        cursor.execute("""INSERT INTO vault_private.vault_background_events
          (event_id,user_id,workspace_id,source_kind,source_id,payload_json)
          VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(user_id,workspace_id,source_kind,source_id) DO NOTHING
          RETURNING event_id""", (str(uuid4()), scope.user_id, scope.workspace_id, kind, source, Jsonb(payload)))
        created = cursor.fetchone()
        if created:
            return created["event_id"]
        cursor.execute("""SELECT event_id,payload_json FROM vault_private.vault_background_events
          WHERE user_id=%s AND workspace_id=%s AND source_kind=%s AND source_id=%s FOR UPDATE""",
          (scope.user_id, scope.workspace_id, kind, source))
        prior = cursor.fetchone()
        if prior is None or prior["payload_json"] != payload:
            raise BackgroundRunConflictError("Source identity was reused with different content")
        return prior["event_id"]

    def create_work(self, scope: OwnerScope, request: WorkRequest, source_key: str) -> str:
        if not source_key or len(source_key) > 512:
            raise ValueError("Work source key is required and bounded")
        payload = _json(request.payload())
        with self._connect() as connection, connection.cursor() as cursor:
            self._owner(cursor, scope)
            self._authority(cursor, scope, request.local_session_id, request.grant_id)
            cursor.execute("""INSERT INTO vault_private.vault_background_work
              (work_id,user_id,workspace_id,source_key,request_json,local_session_id,grant_id)
              VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(user_id,workspace_id,source_key) DO NOTHING
              RETURNING work_id""", (str(uuid4()), scope.user_id, scope.workspace_id, source_key,
                                      Jsonb(payload), request.local_session_id, request.grant_id))
            created = cursor.fetchone()
            if created:
                return created["work_id"]
            cursor.execute("""SELECT work_id,request_json FROM vault_private.vault_background_work
              WHERE user_id=%s AND workspace_id=%s AND source_key=%s FOR UPDATE""",
              (scope.user_id, scope.workspace_id, source_key))
            prior = cursor.fetchone()
            if prior is None or prior["request_json"] != payload:
                raise BackgroundRunConflictError("Work source key was reused with a different request")
            return prior["work_id"]

    def get(self, scope: OwnerScope, work_id: str) -> dict:
        with self._connect() as connection, connection.cursor() as cursor:
            self._owner(cursor, scope)
            cursor.execute("""SELECT * FROM vault_private.vault_background_work
              WHERE user_id=%s AND workspace_id=%s AND work_id=%s""", (scope.user_id, scope.workspace_id, work_id))
            row = cursor.fetchone()
            if row is None:
                raise BackgroundRunAuthorizationError("Work is not available in this scope")
            return row

    def _work(self, cursor, scope: WorkScope, *, assigning: str | None = None, cancelling=False, lock=True):
        """The work row under current authority. ``lock=False`` is for read-only checks that may run
        while another connection of the same call holds the row (they must not wait on it); every
        effect transaction keeps the default lock and rechecks there."""
        self._owner(cursor, scope)
        cursor.execute("""SELECT * FROM vault_private.vault_background_work
          WHERE user_id=%s AND workspace_id=%s AND work_id=%s""", (scope.user_id, scope.workspace_id, scope.work_id))
        prior = cursor.fetchone()
        if prior is None or prior["intent_version"] != scope.intent_version or prior["grant_id"] != scope.grant_id:
            raise BackgroundRunAuthorizationError("Work scope or intent changed")
        if not (assigning and scope.worker_id is None) and (
            prior["worker_id"], prior["worker_generation"]
        ) != (scope.worker_id, scope.worker_generation):
            raise BackgroundRunAuthorizationError("Worker assignment changed")
        if not cancelling:
            self._authority(cursor, scope, prior["local_session_id"], prior["grant_id"])
            worker_id = assigning or prior["worker_id"]
            if assigning and prior["worker_id"] not in (None, assigning):
                raise BackgroundRunConflictError("Work already has a different specialist")
            if worker_id:
                worker_lock = " FOR UPDATE" if assigning else (" FOR SHARE" if lock else "")
                cursor.execute(f"""SELECT generation,status FROM vault_private.vault_background_workers
                  WHERE user_id=%s AND workspace_id=%s AND worker_id=%s{worker_lock}""",
                  (scope.user_id, scope.workspace_id, worker_id))
                worker = cursor.fetchone()
                if worker is None or worker["status"] in {"paused", "deleted"}:
                    raise BackgroundRunAuthorizationError("Specialist is unavailable")
                if prior["worker_id"] and worker["generation"] != prior["worker_generation"]:
                    raise BackgroundRunAuthorizationError("Specialist generation changed")
                if assigning and prior["worker_id"] is None and worker["status"] != "idle":
                    raise BackgroundRunConflictError("Specialist already has active work")
        cursor.execute("""SELECT * FROM vault_private.vault_background_work
          WHERE user_id=%s AND workspace_id=%s AND work_id=%s""" + (" FOR UPDATE" if lock else ""),
          (scope.user_id, scope.workspace_id, scope.work_id))
        row = cursor.fetchone()
        keys = ("intent_version", "grant_id", "local_session_id", "worker_id", "worker_generation")
        if row is None or any(row[key] != prior[key] for key in keys):
            raise BackgroundRunConflictError("Work changed while acquiring execution scope")
        return row

    def assign(self, scope: WorkScope, worker_id: str) -> str:
        with self._connect() as connection, connection.cursor() as cursor:
            return self._assign(cursor, scope, worker_id)

    def _assign(self, cursor, scope: WorkScope, worker_id: str) -> str:
        row = self._work(cursor, scope, assigning=worker_id)
        cursor.execute("""SELECT session_id,worker_id,worker_generation FROM vault_private.vault_background_sessions
          WHERE user_id=%s AND workspace_id=%s AND work_id=%s AND intent_version=%s""",
          (scope.user_id, scope.workspace_id, scope.work_id, scope.intent_version))
        prior = cursor.fetchone()
        if prior:
            if (prior["worker_id"], prior["worker_generation"]) != (worker_id, row["worker_generation"]):
                raise BackgroundRunConflictError("Saved session belongs to a different assignment")
            cursor.execute("""UPDATE vault_private.vault_background_workers SET status='active',updated_at=now()
              WHERE user_id=%s AND workspace_id=%s AND worker_id=%s AND generation=%s AND status='idle'""",
              (scope.user_id, scope.workspace_id, worker_id, row["worker_generation"]))
            return prior["session_id"]
        if WorkState(row["state"]) not in {WorkState.PROPOSED, WorkState.READY, WorkState.QUEUED}:
            raise BackgroundRunConflictError("Work cannot be assigned in this state")
        cursor.execute("""UPDATE vault_private.vault_background_workers SET status='active',updated_at=now()
          WHERE user_id=%s AND workspace_id=%s AND worker_id=%s RETURNING generation""",
          (scope.user_id, scope.workspace_id, worker_id))
        generation = cursor.fetchone()["generation"]
        cursor.execute("""SELECT history_json,source_refs_json FROM vault_private.vault_background_sessions
          WHERE user_id=%s AND workspace_id=%s AND worker_id=%s AND worker_generation=%s
          ORDER BY updated_at DESC LIMIT 1""",
          (scope.user_id, scope.workspace_id, worker_id, generation))
        previous_session = cursor.fetchone()
        history_json = previous_session["history_json"] if previous_session else []
        source_refs_json = previous_session["source_refs_json"] if previous_session else []
        session_id = str(uuid4())
        cursor.execute("""INSERT INTO vault_private.vault_background_sessions
          (session_id,user_id,workspace_id,worker_id,work_id,worker_generation,intent_version,history_json,source_refs_json)
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
          (session_id, scope.user_id, scope.workspace_id, worker_id, scope.work_id, generation,
           scope.intent_version, Jsonb(history_json), Jsonb(source_refs_json)))
        cursor.execute("""UPDATE vault_private.vault_background_work SET worker_id=%s,worker_generation=%s,updated_at=now()
          WHERE user_id=%s AND workspace_id=%s AND work_id=%s""",
          (worker_id, generation, scope.user_id, scope.workspace_id, scope.work_id))
        return session_id

    def transition(self, scope: WorkScope, expected_state: WorkState, next_state: WorkState, detail: dict) -> bool:
        expected_state, next_state = WorkState(expected_state), WorkState(next_state)
        if next_state not in WORK_TRANSITIONS[expected_state]:
            raise ValueError("Illegal work transition")
        detail = _json(detail)
        with self._connect() as connection, connection.cursor() as cursor:
            row = self._work(cursor, scope, cancelling=next_state is WorkState.CANCELLED)
            if row["state"] != expected_state.value:
                return False
            cursor.execute("""UPDATE vault_private.vault_background_work SET state=%s,updated_at=now()
              WHERE user_id=%s AND workspace_id=%s AND work_id=%s""",
              (next_state.value, scope.user_id, scope.workspace_id, scope.work_id))
            self._event(cursor, scope, "transition", str(uuid4()),
                        {"work_id": scope.work_id, "from": expected_state.value, "to": next_state.value, "detail": detail})
            return True

    def accept_result(self, scope: WorkScope, run_id: str, outcome: ExecutionOutcome) -> bool:
        with self._connect() as connection, connection.cursor() as cursor:
            return self._accept_result(cursor, scope, run_id, outcome)

    def _accept_result(self, cursor, scope: WorkScope, run_id: str, outcome: ExecutionOutcome) -> bool:
        # Waiting checkpoints use transition/save; only terminal helper results return to the coordinator.
        if outcome.state not in {WorkState.COMPLETED, WorkState.FAILED, WorkState.CANCELLED, WorkState.UNKNOWN}:
            raise ValueError("Only terminal execution outcomes are result deliveries")
        row = self._work(cursor, scope)
        if row["state"] != WorkState.RUNNING.value:
            return False
        cursor.execute("""SELECT 1 FROM vault_private.vault_background_runs
          WHERE run_id=%s AND user_id=%s AND workspace_id=%s AND work_id=%s
          AND execution_grant_id IS NOT DISTINCT FROM %s FOR SHARE""",
          (run_id, scope.user_id, scope.workspace_id, scope.work_id, scope.grant_id))
        if cursor.fetchone() is None:
            raise BackgroundRunAuthorizationError("Execution does not belong to this work")
        self._event(cursor, scope, "result", f"{run_id}:{scope.intent_version}",
                    {"work_id": scope.work_id, "state": outcome.state.value, "output": _json(outcome.output),
                     "failure_code": outcome.failure_code})
        cursor.execute("""UPDATE vault_private.vault_background_work SET state=%s,result_json=%s,updated_at=now()
          WHERE user_id=%s AND workspace_id=%s AND work_id=%s""",
          (outcome.state.value, Jsonb(outcome.output), scope.user_id, scope.workspace_id, scope.work_id))
        if row["worker_id"]:
            cursor.execute("""UPDATE vault_private.vault_background_workers SET status='idle',updated_at=now()
              WHERE user_id=%s AND workspace_id=%s AND worker_id=%s AND generation=%s AND status='active'""",
              (scope.user_id, scope.workspace_id, row["worker_id"], row["worker_generation"]))
        return True

    def resolve_work_scope(self, work_id: str) -> WorkScope:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM vault_private.vault_background_work WHERE work_id=%s", (work_id,))
            row = cursor.fetchone()
            if row is None:
                raise BackgroundRunAuthorizationError("Work is not available in this scope")
            scope = WorkScope(
                row["user_id"], row["workspace_id"], row["work_id"], row["intent_version"],
                row["worker_id"], row["worker_generation"], row["grant_id"],
            )
            self._work(cursor, scope, lock=False)
            return scope

    def get_preferences(self, scope: OwnerScope) -> dict[str, object]:
        with self._connect() as connection, connection.cursor() as cursor:
            self._owner(cursor, scope)
            cursor.execute("""SELECT payload_json FROM vault_private.vault_background_events
              WHERE user_id=%s AND workspace_id=%s AND source_kind='preferences' AND source_id='workspace'""",
              (scope.user_id, scope.workspace_id))
            row = cursor.fetchone()
            base = {"enabled": False, "quiet_hours": {}, "approved_grant_ids": []}
            if row and isinstance(row["payload_json"], dict):
                base.update(row["payload_json"])
            return base

    def set_preferences(
        self, scope: OwnerScope, *, enabled: bool | None = None,
        quiet_hours: dict[str, object] | None = None, approved_grant_ids: list[str] | None = None,
    ) -> dict[str, object]:
        with self._connect() as connection, connection.cursor() as cursor:
            self._owner(cursor, scope)
            cursor.execute("""SELECT payload_json FROM vault_private.vault_background_events
              WHERE user_id=%s AND workspace_id=%s AND source_kind='preferences' AND source_id='workspace' FOR UPDATE""",
              (scope.user_id, scope.workspace_id))
            row = cursor.fetchone()
            prefs: dict[str, object] = {"enabled": False, "quiet_hours": {}, "approved_grant_ids": []}
            if row and isinstance(row["payload_json"], dict):
                prefs.update(row["payload_json"])
            if enabled is not None:
                prefs["enabled"] = bool(enabled)
            if quiet_hours is not None:
                prefs["quiet_hours"] = _json(quiet_hours)
            if approved_grant_ids is not None:
                prefs["approved_grant_ids"] = list(approved_grant_ids)
            cursor.execute("""INSERT INTO vault_private.vault_background_events
              (event_id,user_id,workspace_id,source_kind,source_id,payload_json,state)
              VALUES (%s,%s,%s,'preferences','workspace',%s,'processed')
              ON CONFLICT(user_id,workspace_id,source_kind,source_id) DO UPDATE SET
                payload_json=EXCLUDED.payload_json, state='processed'""",
              (str(uuid4()), scope.user_id, scope.workspace_id, Jsonb(prefs)))
            return prefs

    def list_scratchpad_items(self, scope: OwnerScope, *, limit: int = 12) -> list[dict[str, object]]:
        with self._connect() as connection, connection.cursor() as cursor:
            self._owner(cursor, scope)
            cursor.execute("""SELECT w.work_id, w.state, w.intent_version, w.request_json, w.result_json,
                k.role_key, w.updated_at
              FROM vault_private.vault_background_work w
              LEFT JOIN vault_private.vault_background_workers k
                ON k.user_id=w.user_id AND k.workspace_id=w.workspace_id AND k.worker_id=w.worker_id
              WHERE w.user_id=%s AND w.workspace_id=%s
              ORDER BY w.updated_at DESC LIMIT %s""",
              (scope.user_id, scope.workspace_id, max(1, min(limit, 50))))
            items: list[dict[str, object]] = []
            for row in cursor.fetchall():
                req = (row["request_json"] or {}).get("request") or {}
                dest = (row["request_json"] or {}).get("destination") or {}
                res = row["result_json"] if isinstance(row["result_json"], dict) else {}
                items.append({
                    "work_id": row["work_id"],
                    "state": row["state"],
                    "intent_version": row["intent_version"],
                    "objective": str(req.get("objective") or ""),
                    "role_key": row["role_key"] or dest.get("role_key"),
                    "summary": str(res.get("summary") or ""),
                })
            return items
