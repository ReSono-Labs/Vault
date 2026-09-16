from __future__ import annotations

from typing import Any


def ensure_link_companion_schema(cursor: Any) -> None:
    cursor.execute("CREATE SCHEMA IF NOT EXISTS vault_private")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS vault_private.link_companion_pairings (
            pairing_id text PRIMARY KEY,
            pairing_code text NOT NULL UNIQUE,
            display_name text NOT NULL,
            poll_token_hash text NOT NULL,
            status text NOT NULL,
            expires_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS vault_private.link_companion_link (
            id integer PRIMARY KEY CHECK (id = 1),
            display_name text NOT NULL,
            pairing_id text NOT NULL,
            paired_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
