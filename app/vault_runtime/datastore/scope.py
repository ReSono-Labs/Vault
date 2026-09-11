from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb


def upsert_scope(cur, *, account_id: str, workspace_id: str, payload: dict[str, Any]) -> None:
    cur.execute(
        """
        INSERT INTO vault_private.vault_accounts (account_id, source_payload, updated_at)
        VALUES (%s, %s, now())
        ON CONFLICT (account_id) DO UPDATE
        SET source_payload = vault_private.vault_accounts.source_payload || EXCLUDED.source_payload,
            updated_at = now()
        """,
        (account_id, Jsonb(_account_scope_payload(payload))),
    )
    cur.execute(
        """
        INSERT INTO vault_private.vault_workspaces (workspace_id, account_id, source_payload, updated_at)
        VALUES (%s, %s, %s, now())
        ON CONFLICT (workspace_id) DO UPDATE
        SET account_id = EXCLUDED.account_id,
            source_payload = vault_private.vault_workspaces.source_payload || EXCLUDED.source_payload,
            updated_at = now()
        """,
        (workspace_id, account_id, Jsonb(_workspace_scope_payload(payload))),
    )


def _account_scope_payload(payload: dict[str, Any]) -> dict[str, Any]:
    runtime_profile = payload.get("runtimeProfile") if isinstance(payload.get("runtimeProfile"), dict) else {}
    return {
        key: value
        for key, value in {
            "accountId": payload.get("accountId"),
            "accountDisplayName": runtime_profile.get("accountDisplayName"),
            "accountTimezone": runtime_profile.get("accountTimezone"),
            "preferredTimezone": runtime_profile.get("preferredTimezone"),
            "preferredLocale": runtime_profile.get("preferredLocale"),
        }.items()
        if value is not None
    }


def _workspace_scope_payload(payload: dict[str, Any]) -> dict[str, Any]:
    runtime_profile = payload.get("runtimeProfile") if isinstance(payload.get("runtimeProfile"), dict) else {}
    return {
        key: value
        for key, value in {
            "accountId": payload.get("accountId"),
            "workspaceId": payload.get("workspaceId"),
            "workspaceDisplayName": runtime_profile.get("workspaceDisplayName"),
            "workspaceDefaultTimezone": runtime_profile.get("workspaceDefaultTimezone"),
        }.items()
        if value is not None
    }
