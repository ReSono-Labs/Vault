"""0003: device-wide settings the device owner chooses (first: limits for hosted packages).

Idempotent. Do not edit after release; add a new migration.
"""

from __future__ import annotations

STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS vault_private.vault_device_settings (
      setting_key text PRIMARY KEY,
      value_json jsonb NOT NULL,
      changed_by_user_id text REFERENCES vault_private.local_users(user_id) ON DELETE SET NULL,
      updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
)


def apply(cursor) -> None:
    for statement in STATEMENTS:
        cursor.execute(statement)
