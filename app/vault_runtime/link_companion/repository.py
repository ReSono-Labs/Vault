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
                    """SELECT l.display_name, l.pairing_id, l.paired_at,
                              EXISTS (SELECT 1 FROM vault_private.local_sessions s
                                      WHERE s.session_id=l.session_id AND s.status='active' AND s.expires_at>now())
                       FROM vault_private.link_companion_link l WHERE l.id=1"""
                )
                row = cursor.fetchone()
                if row is None:
                    return None
                paired_at = row[2]
                return {
                    # A link without a live companion credential (pre-2026-10-18 pairing, password
                    # change, session revocation) must be paired again before the companion can act.
                    "status": "paired" if row[3] else "needs_pairing",
                    "displayName": row[0],
                    "pairingId": row[1],
                    "pairedAt": paired_at.isoformat() if hasattr(paired_at, "isoformat") else str(paired_at),
                }

    def link_session_id(self) -> str | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT session_id FROM vault_private.link_companion_link WHERE id=1")
                row = cursor.fetchone()
                return str(row[0]) if row and row[0] else None

    def touch_session(self, session_id: str) -> None:
        """Slide the companion credential forward on use; unpair or a password change still revokes it."""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE vault_private.local_sessions SET expires_at=now()+interval '365 days'
                       WHERE session_id=%s AND status='active' AND expires_at<now()+interval '300 days'""",
                    (session_id,),
                )

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
                # An approved credential nobody collected in time is never handed out later.
                cursor.execute(
                    """UPDATE vault_private.link_companion_pairings SET delivery_token=NULL
                       WHERE delivery_token IS NOT NULL AND expires_at<=now()"""
                )
                cursor.execute(
                    """INSERT INTO vault_private.link_companion_pairings
                       (pairing_id, pairing_code, display_name, poll_token_hash, status, expires_at)
                       VALUES (%s,%s,%s,%s,'pending',%s)""",
                    (pairing_id, pairing_code, name, hash_token(poll_token), expires),
                )
        return {"pairingId": pairing_id, "pairingCode": pairing_code, "status": "pending"}

    def pairing_status(self, *, pairing_id: str, poll_token: str) -> dict[str, str]:
        """Status for the poll-token holder. The companion credential is returned once, then erased."""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT poll_token_hash, status, expires_at>now(), delivery_token
                       FROM vault_private.link_companion_pairings WHERE pairing_id=%s FOR UPDATE""",
                    (pairing_id,),
                )
                row = cursor.fetchone()
                if row is None or not token_equals(row[0], hash_token(poll_token)):
                    raise LinkCompanionAuthorizationError("Pairing request is unavailable.")
                if row[1] == "pending" and not row[2]:
                    return {"status": "expired"}
                result = {"status": str(row[1])}
                if row[1] == "approved" and row[3] and row[2]:
                    result["companionToken"] = str(row[3])
                    cursor.execute(
                        """UPDATE vault_private.link_companion_pairings SET delivery_token=NULL
                           WHERE pairing_id=%s""",
                        (pairing_id,),
                    )
                return result

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

    def approve_pairing(self, *, pairing_id: str, session_id: str, companion_token: str) -> dict[str, object]:
        """Owner approval: bind the dedicated owner session and stage its token for one pickup.

        Re-pairing replaces the previous companion: its session is revoked in the same transaction.
        """
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
                self._revoke_current(cursor, reason="replaced_by_new_pairing")
                cursor.execute(
                    """UPDATE vault_private.link_companion_pairings
                       SET status='approved', session_id=%s, delivery_token=%s,
                           expires_at=greatest(expires_at, now()+interval '10 minutes')
                       WHERE pairing_id=%s""",
                    (session_id, companion_token, pairing_id),
                )
                cursor.execute(
                    """INSERT INTO vault_private.link_companion_link (id, display_name, pairing_id, session_id)
                       VALUES (1,%s,%s,%s)
                       ON CONFLICT (id) DO UPDATE
                       SET display_name=EXCLUDED.display_name,
                           pairing_id=EXCLUDED.pairing_id,
                           session_id=EXCLUDED.session_id,
                           paired_at=now()""",
                    (row[0], pairing_id, session_id),
                )
        current = self.current_link()
        if current is None:
            raise LinkCompanionError("Pairing could not be stored.")
        return current

    @staticmethod
    def _revoke_current(cursor: Any, *, reason: str) -> None:
        cursor.execute(
            """UPDATE vault_private.local_sessions SET status='revoked', revoked_at=now(),
                      revocation_reason='link_companion_'||%s
               WHERE status='active' AND session_id IN (
                 SELECT session_id FROM vault_private.link_companion_link WHERE id=1 AND session_id IS NOT NULL)""",
            (reason,),
        )
        cursor.execute(
            """UPDATE vault_private.link_companion_pairings
               SET status='revoked', delivery_token=NULL, revoked_at=now(), revocation_reason=%s
               WHERE status='approved'""",
            (reason,),
        )

    def unpair(self, *, reason: str = "owner_unpaired") -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._revoke_current(cursor, reason=reason)
                cursor.execute("DELETE FROM vault_private.link_companion_link WHERE id=1")
                cursor.execute(
                    """UPDATE vault_private.link_companion_pairings
                       SET status='revoked', revoked_at=now(), revocation_reason=%s WHERE status='pending'""",
                    (reason,),
                )
