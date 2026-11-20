"""Revocable unattended authority; never inferred from conversation/model text."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from uuid import uuid4

from psycopg.types.json import Jsonb

from .coordination_contracts import OwnerScope, WorkState
from .coordination_repository import CoordinationRepository
from .errors import BackgroundRunAuthorizationError


def proposal_hash(kind, arguments):
    value = json.dumps({"kind": kind, "arguments": arguments}, sort_keys=True,
                       ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return sha256(value.encode()).hexdigest()


def validate_resource_policy(policy):
    if not isinstance(policy, dict) or set(policy) - {"tool_arguments"}:
        raise ValueError("Unsupported resource policy")
    rules = policy.get("tool_arguments", {})
    if not isinstance(rules, dict) or len(rules) > 50:
        raise ValueError("Invalid resource rules")
    for tool, fields in rules.items():
        if not isinstance(tool, str) or not tool or not isinstance(fields, dict) or len(fields) > 50:
            raise ValueError("Invalid tool resource rule")
        for name, allowed in fields.items():
            if not isinstance(name, str) or not name or not isinstance(allowed, list) or len(allowed) > 128:
                raise ValueError("Invalid argument resource rule")
            if any(not isinstance(value, str) for value in allowed):
                raise ValueError("Resource bounds require exact string values")


def _resource_allowed(policy, tool_name, arguments):
    validate_resource_policy(policy)
    rules = policy.get("tool_arguments", {}).get(tool_name, {})
    return not rules or (isinstance(arguments, dict) and all(
        isinstance(arguments.get(name), str) and arguments[name] in values for name, values in rules.items()
    ))


def validate_approval_channel(cursor, scope, channel, generation):
    if channel not in {"browser", "link"}:
        raise BackgroundRunAuthorizationError("A current trusted decision is required")
    CoordinationRepository._authority(cursor, scope, generation, None)
    if channel == "link":
        cursor.execute("SELECT to_regclass('vault_private.link_companion_link') AS binding")
        if cursor.fetchone()["binding"] is None:
            raise BackgroundRunAuthorizationError("Link binding is unavailable")
        cursor.execute("SELECT 1 FROM vault_private.link_companion_link WHERE session_id=%s", (generation,))
        if cursor.fetchone() is None:
            raise BackgroundRunAuthorizationError("Link binding changed")


def approved_record(cursor, decision, kind):
    """Consume decisions recorded by trusted UI/domain code, never supplied approval claims."""
    scope = OwnerScope(decision.actor_user_id, decision.workspace_id)
    CoordinationRepository._owner(cursor, scope)
    if decision.choice != "allow_once":
        raise BackgroundRunAuthorizationError("A current trusted decision is required")
    validate_approval_channel(cursor, scope, decision.channel, decision.channel_generation)
    cursor.execute("""SELECT * FROM vault_private.vault_background_actions
      WHERE action_id=%s AND user_id=%s AND workspace_id=%s FOR UPDATE""",
      (decision.action_id, decision.actor_user_id, decision.workspace_id))
    row = cursor.fetchone()
    if row is None or row["kind"] != kind or row["state"] not in {"approved", "completed"} or row["expires_at"] <= datetime.now(timezone.utc):
        raise BackgroundRunAuthorizationError("An unchanged approved action is required")
    bound = {"action_hash": decision.action_hash, "decision_id": decision.decision_id,
             "actor_user_id": decision.actor_user_id, "channel": decision.channel, "channel_generation": decision.channel_generation}
    if any(row[key] != value for key, value in bound.items()) or proposal_hash(kind, row["arguments_json"]) != decision.action_hash:
        raise BackgroundRunAuthorizationError("Approval does not match the prepared action")
    return row


class BackgroundAuthority:
    def __init__(self, *, database_url):
        self._repo = CoordinationRepository(database_url=database_url)

    def _restrictions(self, cursor, scope, row):
        names = None
        policies = []
        if scope.grant_id:
            cursor.execute("""SELECT policy_json FROM vault_private.vault_background_execution_grants
              WHERE user_id=%s AND workspace_id=%s AND grant_id=%s""", (scope.user_id, scope.workspace_id, scope.grant_id))
            grant = cursor.fetchone()["policy_json"]
            names = set(grant.get("tool_names", []))
            policies.append(grant.get("resource_policy", {}))
        requested = row["request_json"]["request"].get("requested_tool_names", [])
        if requested:
            names = set(requested) if names is None else names.intersection(requested)
        worker_status = None
        if row["worker_id"]:
            cursor.execute("""SELECT spec_json,status FROM vault_private.vault_background_workers
              WHERE user_id=%s AND workspace_id=%s AND worker_id=%s""", (scope.user_id, scope.workspace_id, row["worker_id"]))
            worker = cursor.fetchone()
            worker_status = worker["status"]
            tools = worker["spec_json"].get("tool_names", [])
            names = set(tools) if names is None else names.intersection(tools)
            policies.append(worker["spec_json"].get("resource_policy", {}))
        return names, policies, worker_status

    def allowed_tool_names(self, scope):
        with self._repo._connect() as connection, connection.cursor() as cursor:
            row = self._repo._work(cursor, scope, lock=False)
            names, _policies, _status = self._restrictions(cursor, scope, row)
            return None if names is None else frozenset(names)

    def validate(self, scope, tool_name=None, resource=None):
        with self._repo._connect() as connection, connection.cursor() as cursor:
            row = self._repo._work(cursor, scope, lock=False)
            if row["state"] in {WorkState.COMPLETED, WorkState.FAILED, WorkState.CANCELLED, WorkState.UNKNOWN}:
                raise BackgroundRunAuthorizationError("Work is no longer executable")
            names, policies, worker_status = self._restrictions(cursor, scope, row)
            if tool_name is not None and (row["state"] != WorkState.RUNNING.value or
                    (names is not None and tool_name not in names) or
                    (worker_status is not None and worker_status != "active") or
                    not all(_resource_allowed(policy, tool_name, resource) for policy in policies)):
                raise BackgroundRunAuthorizationError("Tool/resource is not granted to this work")

    def grant(self, principal, proposal, decision):
        scope = OwnerScope(principal.user_id, principal.workspace_id)
        if set(proposal) - {"purpose", "tool_names", "resource_policy", "expires_at"} or not proposal.get("purpose"):
            raise ValueError("Invalid execution grant proposal")
        tools = proposal.get("tool_names")
        if not isinstance(tools, list) or len(tools) > 50 or any(not isinstance(t, str) or not t.strip() for t in tools) or len(set(tools)) != len(tools):
            raise ValueError("Grant tools must be explicit and bounded")
        validate_resource_policy(proposal.get("resource_policy", {}))
        expiry = datetime.fromisoformat(proposal["expires_at"]) if proposal.get("expires_at") else None
        if expiry and (expiry.tzinfo is None or expiry <= datetime.now(timezone.utc)):
            raise ValueError("Grant expiry must be a future aware datetime")
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            self._repo._authority(cursor, scope, principal.session_id, None)
            if (decision.actor_user_id, decision.workspace_id) != (scope.user_id, scope.workspace_id):
                raise BackgroundRunAuthorizationError("Decision belongs to another owner")
            row = approved_record(cursor, decision, "execution_grant")
            if row["arguments_json"] != proposal:
                raise BackgroundRunAuthorizationError("Grant differs from the approved policy")
            if row["state"] == "completed":
                return row["receipt_json"]["grant_id"]
            grant_id = str(uuid4())
            cursor.execute("""INSERT INTO vault_private.vault_background_execution_grants
              (grant_id,user_id,workspace_id,purpose,policy_json,expires_at) VALUES (%s,%s,%s,%s,%s,%s)""",
              (grant_id, scope.user_id, scope.workspace_id, proposal["purpose"],
               Jsonb({"tool_names": tools, "resource_policy": proposal.get("resource_policy", {})}), expiry))
            cursor.execute("UPDATE vault_private.vault_background_actions SET state='completed',receipt_json=%s,updated_at=now() WHERE action_id=%s",
                           (Jsonb({"grant_id": grant_id}), decision.action_id))
            return grant_id

    def revoke(self, principal, grant_id):
        scope = OwnerScope(principal.user_id, principal.workspace_id)
        with self._repo._connect() as connection, connection.cursor() as cursor:
            self._repo._owner(cursor, scope)
            self._repo._authority(cursor, scope, principal.session_id, None)
            cursor.execute("""UPDATE vault_private.vault_background_execution_grants SET status='revoked',version=version+1
              WHERE user_id=%s AND workspace_id=%s AND grant_id=%s RETURNING grant_id""", (scope.user_id, scope.workspace_id, grant_id))
            if cursor.fetchone() is None:
                raise BackgroundRunAuthorizationError("Grant is unavailable")
            cursor.execute("""UPDATE vault_private.vault_background_runs SET cancellation_requested=true
              WHERE user_id=%s AND workspace_id=%s AND execution_grant_id=%s""", (scope.user_id, scope.workspace_id, grant_id))
            cursor.execute("""UPDATE vault_private.vault_background_routines
              SET status='paused', version=version+1, updated_at=now()
              WHERE user_id=%s AND workspace_id=%s AND grant_id=%s AND status='active'""",
              (scope.user_id, scope.workspace_id, grant_id))
            cursor.execute("""UPDATE vault_private.vault_background_actions
              SET state='expired', updated_at=now()
              WHERE user_id=%s AND workspace_id=%s AND state IN ('pending','approved')
                AND work_id IN (
                  SELECT work_id FROM vault_private.vault_background_work
                  WHERE user_id=%s AND workspace_id=%s AND grant_id=%s
                )""", (scope.user_id, scope.workspace_id, scope.user_id, scope.workspace_id, grant_id))
            cursor.execute("""UPDATE vault_private.vault_background_work
              SET state='cancelled', updated_at=now()
              WHERE user_id=%s AND workspace_id=%s AND grant_id=%s
                AND state NOT IN ('completed','failed','cancelled','unknown')""",
              (scope.user_id, scope.workspace_id, grant_id))
