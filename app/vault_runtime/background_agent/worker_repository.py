"""User-approved persistent profiles, never additional public agents or credentials."""
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from psycopg.types.json import Jsonb

from .authority import approved_record, proposal_hash, validate_resource_policy
from .contracts import RunLimits
from .coordination_contracts import OwnerScope, PreparedAction, WorkerSpec
from .coordination_repository import CoordinationRepository, _json
from .errors import BackgroundRunAuthorizationError, BackgroundRunConflictError


class WorkerRepository:
    def __init__(self, *, database_url):
        self._repo = CoordinationRepository(database_url=database_url)

    def propose(
        self,
        scope: OwnerScope,
        spec: WorkerSpec,
        *,
        origin_conversation_id: str | None = None,
        origin_turn_id: str | None = None,
        origin_voice_session_id: str | None = None,
    ) -> PreparedAction:
        from .actions import ACTION_TTL, BackgroundActions
        validate_resource_policy(spec.resource_policy)
        payload = _json(asdict(spec))
        fingerprint = proposal_hash("worker_create", payload)
        operation = f"worker-create:{spec.role_key}:{fingerprint}"
        detail_lines = [
            f"Role: {spec.role_key}",
            f"Purpose: {spec.purpose}",
            f"Tools: {'all background tools (agent-to-agent sends stay with the coordinator)' if '*' in spec.tool_names else (', '.join(spec.tool_names) if spec.tool_names else 'none')}",
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
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            cursor.execute("""INSERT INTO vault_private.vault_background_actions
              (action_id,user_id,workspace_id,kind,action_hash,arguments_json,title,detail,detail_lines,
               expires_at,operation_key,origin_json)
              VALUES (%s,%s,%s,'worker_create',%s,%s,%s,%s,%s,%s,%s,%s)
              ON CONFLICT(user_id,workspace_id,operation_key) DO NOTHING RETURNING *""",
              (str(uuid4()), scope.user_id, scope.workspace_id, fingerprint, Jsonb(payload),
               f"Create {spec.role_key} specialist", spec.purpose, Jsonb(detail_lines),
               datetime.now(timezone.utc)+ACTION_TTL,
               operation, Jsonb(origin_meta)))
            row = cursor.fetchone()
            if row is None:
                row = BackgroundActions._latest(cursor, scope, operation)
                if row is not None and row["state"] == "pending" and origin_meta:
                    merged_origin = {**(row.get("origin_json") or {}), **origin_meta}
                    cursor.execute("""UPDATE vault_private.vault_background_actions
                        SET origin_json = %s, updated_at = now()
                        WHERE action_id = %s RETURNING *""",
                        (Jsonb(merged_origin), row["action_id"]))
                    row = cursor.fetchone()
            if not (row["state"] == "approved" or (row["state"] == "pending" and row["expires_at"] > datetime.now(timezone.utc))):
                raise BackgroundRunConflictError("This specialist proposal was already decided or expired; the owner must reopen it")
            return PreparedAction(row["action_id"], row["action_hash"], None, row["kind"], row["title"], row["detail"], row["expires_at"])

    def propose_memory_lookup(self, scope: OwnerScope, role_key: str, *,
                              conversation_id: str, turn_id: str) -> PreparedAction | None:
        from .actions import BackgroundActions

        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            cursor.execute("""SELECT worker_id,generation,spec_json FROM vault_private.vault_background_workers
                WHERE user_id=%s AND workspace_id=%s AND role_key=%s AND status IN ('idle','paused')""",
                (scope.user_id, scope.workspace_id, role_key))
            row = cursor.fetchone()
        if row is None:
            raise BackgroundRunConflictError("Select an idle or paused specialist.")
        if {"memory_lookup", "*"} & set(row["spec_json"]["tool_names"]):
            return None
        return BackgroundActions(database_url=self._repo._database_url).prepare(
            scope, "worker_create", {
                "role_key": role_key,
                "worker_id": row["worker_id"],
                "expected_generation": row["generation"],
                "expected_spec_hash": proposal_hash("worker_create", row["spec_json"]),
                "add_read_tool": "memory_lookup",
                "summary": f"Give {role_key} read-only Vault Memory search in this workspace.",
            }, None, None, origin={"conversation_id": conversation_id, "turn_id": turn_id},
        )

    def create_from_approval(self, decision) -> str:
        with self._repo._connect() as connection, connection.cursor() as cursor:
            row = approved_record(cursor, decision, "worker_create")
            if row["state"] == "completed":
                return row["receipt_json"]["worker_id"]
            payload = row["arguments_json"]
            if payload.get("add_read_tool") == "memory_lookup":
                cursor.execute("""SELECT worker_id,spec_json,generation,status
                    FROM vault_private.vault_background_workers
                    WHERE user_id=%s AND workspace_id=%s AND worker_id=%s AND role_key=%s FOR UPDATE""",
                    (decision.actor_user_id, decision.workspace_id, payload["worker_id"], payload["role_key"]))
                worker = cursor.fetchone()
                if (worker is None or worker["status"] not in {"idle", "paused"}
                        or worker["generation"] != payload["expected_generation"]
                        or proposal_hash("worker_create", worker["spec_json"]) != payload["expected_spec_hash"]):
                    raise BackgroundRunConflictError("Specialist changed or is running. Request a new approval.")
                spec = dict(worker["spec_json"])
                spec["tool_names"] = [*spec["tool_names"], "memory_lookup"]
                cursor.execute("""UPDATE vault_private.vault_background_workers
                    SET spec_json=%s,spec_hash=%s,updated_at=now() WHERE worker_id=%s""",
                    (Jsonb(spec), proposal_hash("worker_create", spec), worker["worker_id"]))
                cursor.execute("""UPDATE vault_private.vault_background_actions
                    SET state='completed',receipt_json=%s,updated_at=now() WHERE action_id=%s""",
                    (Jsonb({"worker_id": worker["worker_id"]}), decision.action_id))
                return worker["worker_id"]
            spec = WorkerSpec(**(payload | {"tool_names": tuple(payload["tool_names"]), "limits": RunLimits(**payload["limits"])}))
            validate_resource_policy(spec.resource_policy)
            cursor.execute("""SELECT worker_id FROM vault_private.vault_background_workers
              WHERE user_id=%s AND workspace_id=%s AND role_key=%s AND status<>'deleted'""",
              (decision.actor_user_id, decision.workspace_id, spec.role_key))
            if cursor.fetchone() is not None:
                raise BackgroundRunConflictError("Specialist role already exists")
            worker_id = str(uuid4())
            cursor.execute("""INSERT INTO vault_private.vault_background_workers
              (worker_id,user_id,workspace_id,role_key,spec_json,spec_hash) VALUES (%s,%s,%s,%s,%s,%s)""",
              (worker_id, decision.actor_user_id, decision.workspace_id, spec.role_key, Jsonb(payload), decision.action_hash))
            cursor.execute("UPDATE vault_private.vault_background_actions SET state='completed',receipt_json=%s,updated_at=now() WHERE action_id=%s",
                           (Jsonb({"worker_id": worker_id}), decision.action_id))
            return worker_id

    def create_direct(self, scope: OwnerScope, spec: WorkerSpec) -> str:
        """Create a specialist the owner asked for in this turn, without a card.

        Rakazo's spawn_bot and run_subagent are approval-exempt (core/src/runs/action-approval.ts
        @83db73c); what a specialist then does still goes through Vault's prepared-action approvals.
        Turns the owner did not start keep using ``propose`` (Rakazo's outside-run gating)."""
        validate_resource_policy(spec.resource_policy)
        payload = _json(asdict(spec))
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            cursor.execute("""SELECT worker_id FROM vault_private.vault_background_workers
              WHERE user_id=%s AND workspace_id=%s AND role_key=%s AND status<>'deleted'""",
              (scope.user_id, scope.workspace_id, spec.role_key))
            if cursor.fetchone() is not None:
                raise BackgroundRunConflictError("Specialist role already exists")
            worker_id = str(uuid4())
            cursor.execute("""INSERT INTO vault_private.vault_background_workers
              (worker_id,user_id,workspace_id,role_key,spec_json,spec_hash) VALUES (%s,%s,%s,%s,%s,%s)""",
              (worker_id, scope.user_id, scope.workspace_id, spec.role_key, Jsonb(payload),
               proposal_hash("worker_create", payload)))
            return worker_id

    def get(self, scope: OwnerScope, worker_id) -> WorkerSpec:
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            cursor.execute("""SELECT spec_json FROM vault_private.vault_background_workers
              WHERE user_id=%s AND workspace_id=%s AND worker_id=%s AND status<>'deleted'""", (scope.user_id, scope.workspace_id, worker_id))
            row = cursor.fetchone()
            if row is None:
                raise BackgroundRunAuthorizationError("Specialist is unavailable")
            payload = row["spec_json"]
            return WorkerSpec(**(payload | {"tool_names": tuple(payload["tool_names"]), "limits": RunLimits(**payload["limits"])}))

    def set_state(self, scope, worker_id, expected_generation, state) -> int:
        if state not in {"idle", "paused", "reset", "deleted"}:
            raise ValueError("Unsupported specialist control")
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            cursor.execute("""SELECT generation,status,role_key FROM vault_private.vault_background_workers
              WHERE user_id=%s AND workspace_id=%s AND worker_id=%s FOR UPDATE""", (scope.user_id, scope.workspace_id, worker_id))
            row = cursor.fetchone()
            if row is None:
                raise BackgroundRunAuthorizationError("Specialist is unavailable")
            if row["generation"] != expected_generation or row["status"] == "deleted":
                raise BackgroundRunConflictError("Specialist generation changed")
            cursor.execute("""UPDATE vault_private.vault_background_workers SET status=%s,generation=generation+1,updated_at=now()
              WHERE user_id=%s AND workspace_id=%s AND worker_id=%s RETURNING generation""",
              ("idle" if state == "reset" else state, scope.user_id, scope.workspace_id, worker_id))
            generation = cursor.fetchone()["generation"]
            cursor.execute("""UPDATE vault_private.vault_background_runs r SET cancellation_requested=true
              WHERE r.user_id=%s AND r.workspace_id=%s AND EXISTS (SELECT 1 FROM vault_private.vault_background_work w
              WHERE w.work_id=r.work_id AND w.worker_id=%s)""", (scope.user_id, scope.workspace_id, worker_id))
            cursor.execute("""UPDATE vault_private.vault_background_actions SET state='expired',updated_at=now()
              WHERE user_id=%s AND workspace_id=%s AND state IN ('pending','approved') AND
              (work_id IN (SELECT work_id FROM vault_private.vault_background_work WHERE user_id=%s AND workspace_id=%s AND worker_id=%s)
               OR (kind='worker_create' AND arguments_json->>'role_key'=%s))""",
              (scope.user_id, scope.workspace_id, scope.user_id, scope.workspace_id, worker_id, row["role_key"]))
            if state in {"reset", "deleted"}:
                cursor.execute("""UPDATE vault_private.vault_background_sessions SET checkpoint_json=NULL,
                  history_json='[]'::jsonb,source_refs_json='[]'::jsonb,updated_at=now()
                  WHERE user_id=%s AND workspace_id=%s AND worker_id=%s""", (scope.user_id, scope.workspace_id, worker_id))
                cursor.execute("""UPDATE vault_private.vault_background_runs r SET checkpoint_json=NULL
                  WHERE r.user_id=%s AND r.workspace_id=%s AND EXISTS (SELECT 1 FROM vault_private.vault_background_work w
                  WHERE w.work_id=r.work_id AND w.worker_id=%s)""", (scope.user_id, scope.workspace_id, worker_id))
            if state == "deleted":
                cursor.execute("""UPDATE vault_private.vault_background_workers SET spec_json='{}'::jsonb
                  WHERE user_id=%s AND workspace_id=%s AND worker_id=%s""", (scope.user_id, scope.workspace_id, worker_id))
            return generation
