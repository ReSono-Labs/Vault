from __future__ import annotations

import secrets
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.core.security.tokens import hash_token, token_equals
from app.vault_runtime.link_companion.schema import ensure_link_companion_schema


class LinkCompanionError(RuntimeError):
    code = "link_companion_error"


class LinkCompanionAuthorizationError(LinkCompanionError):
    code = "link_companion_authorization_denied"


class LinkCompanionNotFoundError(LinkCompanionError):
    code = "link_companion_not_found"


class LinkCompanionRepository:
    def __init__(
        self,
        *,
        database_url: str,
        connector: Callable[..., AbstractContextManager[Any]] | None = None,
    ) -> None:
        self._database_url = database_url
        self._connector = connector

    def _connect(self):
        if self._connector is not None:
            return self._connector(self._database_url)
        import psycopg
        return psycopg.connect(self._database_url, connect_timeout=5)

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                ensure_link_companion_schema(cursor)

    def current_link(self) -> dict[str, object] | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT display_name, pairing_id, paired_at
                       FROM vault_private.link_companion_link WHERE id=1"""
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                paired_at = row[2]
                return {
                    "status": "paired",
                    "displayName": row[0],
                    "pairingId": row[1],
                    "pairedAt": paired_at.isoformat() if hasattr(paired_at, "isoformat") else str(paired_at),
                }

    def start_pairing(self, *, display_name: str, poll_token: str) -> dict[str, str]:
        name = display_name.strip()[:128]
        if not name:
            raise ValueError("displayName is required")
        if not poll_token.strip():
            raise ValueError("pollToken is required")
        pairing_id = str(uuid4())
        pairing_code = "-".join((secrets.token_hex(2), secrets.token_hex(2))).upper()
        expires = datetime.now(timezone.utc) + timedelta(minutes=10)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """DELETE FROM vault_private.link_companion_pairings
                       WHERE status='pending' AND expires_at<=now()"""
                )
                cursor.execute(
                    """INSERT INTO vault_private.link_companion_pairings
                       (pairing_id, pairing_code, display_name, poll_token_hash, status, expires_at)
                       VALUES (%s,%s,%s,%s,'pending',%s)""",
                    (pairing_id, pairing_code, name, hash_token(poll_token), expires),
                )
        return {"pairingId": pairing_id, "pairingCode": pairing_code, "status": "pending"}

    def pairing_status(self, *, pairing_id: str, poll_token: str) -> str:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT poll_token_hash, status, expires_at>now()
                       FROM vault_private.link_companion_pairings WHERE pairing_id=%s""",
                    (pairing_id,),
                )
                row = cursor.fetchone()
                if row is None or not token_equals(row[0], hash_token(poll_token)):
                    raise LinkCompanionAuthorizationError("Pairing request is unavailable.")
                if row[1] == "pending" and not row[2]:
                    return "expired"
                return str(row[1])

    def pairing_by_code(self, *, pairing_code: str) -> dict[str, object]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT pairing_id, display_name, status, expires_at>now()
                       FROM vault_private.link_companion_pairings WHERE pairing_code=%s""",
                    (pairing_code.upper(),),
                )
                row = cursor.fetchone()
                if row is None or row[2] != "pending" or not row[3]:
                    raise LinkCompanionAuthorizationError("Pairing request is unavailable or expired.")
                return {
                    "pairingId": row[0],
                    "displayName": row[1],
                    "status": row[2],
                }

    def approve_pairing(self, *, pairing_id: str) -> dict[str, object]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT display_name FROM vault_private.link_companion_pairings
                       WHERE pairing_id=%s AND status='pending' AND expires_at>now() FOR UPDATE""",
                    (pairing_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise LinkCompanionAuthorizationError("Pairing request is unavailable or expired.")
                cursor.execute(
                    """UPDATE vault_private.link_companion_pairings
                       SET status='approved' WHERE pairing_id=%s""",
                    (pairing_id,),
                )
                cursor.execute(
                    """INSERT INTO vault_private.link_companion_link (id, display_name, pairing_id)
                       VALUES (1,%s,%s)
                       ON CONFLICT (id) DO UPDATE
                       SET display_name=EXCLUDED.display_name,
                           pairing_id=EXCLUDED.pairing_id,
                           paired_at=now()""",
                    (row[0], pairing_id),
                )
        current = self.current_link()
        if current is None:
            raise LinkCompanionError("Pairing could not be stored.")
        return current

    def unpair(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM vault_private.link_companion_link WHERE id=1")
                cursor.execute(
                    """UPDATE vault_private.link_companion_pairings
                       SET status='revoked' WHERE status IN ('pending','approved')"""
                )
