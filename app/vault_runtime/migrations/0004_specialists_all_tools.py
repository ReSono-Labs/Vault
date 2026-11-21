"""0004: existing specialists and their routines get all background tools ("*").

The owner decided (2026-11-21) that specialists work with the coordinator's tools instead of the
short lists chosen when each was created. "*" means every background tool except the ones that stay
with the coordinator (agent-to-agent sends, Link setup); see background_agent/coordinator.py.
Restricted lists can still be set again later. Each specialist's spec_hash is recomputed the same
way Vault hashes a specialist proposal.

Idempotent. Do not edit after release; add a new migration.
"""

from __future__ import annotations

import json
from hashlib import sha256


def _spec_hash(spec: dict) -> str:
    value = json.dumps({"kind": "worker_create", "arguments": spec}, sort_keys=True,
                       ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return sha256(value.encode()).hexdigest()


def apply(cursor) -> None:
    cursor.execute("SELECT to_regclass('vault_private.vault_background_workers')")
    if cursor.fetchone()[0] is None:
        return
    cursor.execute(
        """SELECT worker_id, spec_json FROM vault_private.vault_background_workers
           WHERE status <> 'deleted' AND NOT (spec_json->'tool_names' ? '*')"""
    )
    for worker_id, spec in cursor.fetchall():
        spec = dict(spec)
        spec["tool_names"] = ["*"]
        cursor.execute(
            """UPDATE vault_private.vault_background_workers SET spec_json=%s::jsonb, spec_hash=%s,
                      updated_at=now() WHERE worker_id=%s""",
            (json.dumps(spec), _spec_hash(spec), worker_id),
        )
    # Specialist routines (they name a role): the saved request and the routine's grant.
    cursor.execute(
        """UPDATE vault_private.vault_background_routines
           SET template_json=jsonb_set(template_json, '{request,requested_tool_names}', '["*"]'::jsonb, true),
               updated_at=now()
           WHERE status <> 'deleted' AND coalesce(template_json->'destination'->>'role_key', '') <> ''
             AND NOT (coalesce(template_json->'request'->'requested_tool_names', '[]'::jsonb) ? '*')"""
    )
    cursor.execute(
        """UPDATE vault_private.vault_background_execution_grants g
           SET policy_json=jsonb_set(g.policy_json, '{tool_names}', '["*"]'::jsonb, true), version=g.version+1
           FROM vault_private.vault_background_routines r
           WHERE r.grant_id=g.grant_id AND r.status <> 'deleted' AND g.status='active'
             AND coalesce(r.template_json->'destination'->>'role_key', '') <> ''
             AND NOT (coalesce(g.policy_json->'tool_names', '[]'::jsonb) ? '*')"""
    )
