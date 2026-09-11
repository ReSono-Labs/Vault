"""Hash-bound preflight confirmation adapted from R1 import lifecycle behavior."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from threading import RLock
from collections.abc import Callable
from typing import Generic, TypeVar

from app.vault_runtime.extensions.models import ExtensionAudience, ExtensionKind


T = TypeVar("T")


class PreflightError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Preflight(Generic[T]):
    token: str
    kind: ExtensionKind
    identity: str
    principal_user_id: str
    workspace_id: str
    candidate_hash: str
    current_hash: str | None
    audience: ExtensionAudience
    payload: T
    expires_at: datetime


class PreflightRegistry(Generic[T]):
    def __init__(
        self, *, lifetime: timedelta = timedelta(minutes=10),
        dispose: Callable[[T], None] | None = None,
    ) -> None:
        if lifetime <= timedelta(0) or lifetime > timedelta(hours=1):
            raise ValueError("preflight lifetime must be within one hour")
        self._lifetime = lifetime
        self._dispose = dispose
        self._records: dict[str, Preflight[T]] = {}
        self._lock = RLock()

    def issue(
        self, *, kind: ExtensionKind, identity: str, principal_user_id: str,
        workspace_id: str, candidate_hash: str, current_hash: str | None,
        audience: ExtensionAudience, payload: T, now: datetime | None = None,
    ) -> Preflight[T]:
        for value in (identity, principal_user_id, workspace_id, candidate_hash):
            if not value or value.strip() != value:
                raise PreflightError("preflight identifiers must be non-empty and trimmed")
        issued = datetime.now(UTC) if now is None else _aware(now)
        record = Preflight(
            token=token_urlsafe(32), kind=kind, identity=identity,
            principal_user_id=principal_user_id, workspace_id=workspace_id,
            candidate_hash=candidate_hash, current_hash=current_hash,
            audience=audience, payload=payload, expires_at=issued + self._lifetime,
        )
        with self._lock:
            self._purge(issued)
            self._records[record.token] = record
        return record

    def consume(
        self, token: str, *, principal_user_id: str, workspace_id: str,
        current_hash: str | None, replace: bool, now: datetime | None = None,
    ) -> Preflight[T]:
        checked = datetime.now(UTC) if now is None else _aware(now)
        with self._lock:
            record = self._records.get(token)
            if record is None:
                raise PreflightError("preflight token is invalid or already used")
            if checked >= record.expires_at:
                self._records.pop(token, None)
                self._dispose_payload(record.payload)
                raise PreflightError("preflight token has expired")
            if record.principal_user_id != principal_user_id or record.workspace_id != workspace_id:
                raise PreflightError("preflight token belongs to another local scope")
            if record.current_hash != current_hash:
                raise PreflightError("installed extension changed after preflight")
            if current_hash is not None and not replace:
                raise PreflightError("replacement requires explicit confirmation")
            self._records.pop(token, None)
        return record

    def peek(self, token: str) -> Preflight[T]:
        with self._lock:
            record = self._records.get(token)
        if record is None:
            raise PreflightError("preflight token is invalid or already used")
        return record

    def discard(self, token: str) -> None:
        with self._lock:
            record = self._records.pop(token, None)
            if record is not None:
                self._dispose_payload(record.payload)

    def _purge(self, now: datetime) -> None:
        expired = [token for token, item in self._records.items() if now >= item.expires_at]
        for token in expired:
            record = self._records.pop(token, None)
            if record is not None:
                self._dispose_payload(record.payload)

    def _dispose_payload(self, payload: T) -> None:
        if self._dispose is not None:
            self._dispose(payload)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("time must be timezone-aware")
    return value.astimezone(UTC)
