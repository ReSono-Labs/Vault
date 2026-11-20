from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

from .types import TurnRecord, TurnStatus

DEFAULT_STATE_DIR = Path.home() / ".local" / "share" / "link-a2a-collab"


class TurnStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or (DEFAULT_STATE_DIR / "turns.sqlite3")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS turns (
                    turn_id TEXT PRIMARY KEY,
                    peer TEXT NOT NULL,
                    context_id TEXT,
                    task_id TEXT,
                    status TEXT NOT NULL,
                    request_text TEXT NOT NULL,
                    response_text TEXT,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    raw_task TEXT
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_turns_peer ON turns(peer)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_turns_context ON turns(context_id)")
            conn.commit()

    def create(self, peer: str, request_text: str, context_id: str | None = None) -> TurnRecord:
        now = time.time()
        record = TurnRecord(
            turn_id=str(uuid.uuid4()),
            peer=peer,
            context_id=context_id,
            task_id=None,
            status=TurnStatus.PENDING,
            request_text=request_text,
            response_text=None,
            error=None,
            created_at=now,
            updated_at=now,
            raw_task=None,
        )
        self._save(record)
        return record

    def update(
        self,
        turn_id: str,
        *,
        task_id: str | None = None,
        context_id: str | None = None,
        status: TurnStatus | None = None,
        response_text: str | None = None,
        error: str | None = None,
        raw_task: dict[str, Any] | None = None,
    ) -> TurnRecord:
        record = self.get(turn_id)
        if task_id is not None:
            record.task_id = task_id
        if context_id is not None:
            record.context_id = context_id
        if status is not None:
            record.status = status
        if response_text is not None:
            record.response_text = response_text
        if error is not None:
            record.error = error
        if raw_task is not None:
            record.raw_task = raw_task
        record.updated_at = time.time()
        self._save(record)
        return record

    def get(self, turn_id: str) -> TurnRecord:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM turns WHERE turn_id = ?", (turn_id,)).fetchone()
        if row is None:
            raise KeyError(turn_id)
        return self._from_row(row)

    def list_recent(self, limit: int = 20) -> list[TurnRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM turns ORDER BY created_at DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def _save(self, record: TurnRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO turns (
                    turn_id, peer, context_id, task_id, status, request_text,
                    response_text, error, created_at, updated_at, raw_task
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(turn_id) DO UPDATE SET
                    context_id = excluded.context_id,
                    task_id = excluded.task_id,
                    status = excluded.status,
                    response_text = excluded.response_text,
                    error = excluded.error,
                    updated_at = excluded.updated_at,
                    raw_task = excluded.raw_task
                """,
                (
                    record.turn_id,
                    record.peer,
                    record.context_id,
                    record.task_id,
                    record.status.value,
                    record.request_text,
                    record.response_text,
                    record.error,
                    record.created_at,
                    record.updated_at,
                    json.dumps(record.raw_task) if record.raw_task is not None else None,
                ),
            )
            conn.commit()

    @staticmethod
    def _from_row(row: sqlite3.Row) -> TurnRecord:
        raw = row["raw_task"]
        return TurnRecord(
            turn_id=row["turn_id"],
            peer=row["peer"],
            context_id=row["context_id"],
            task_id=row["task_id"],
            status=TurnStatus(row["status"]),
            request_text=row["request_text"],
            response_text=row["response_text"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            raw_task=json.loads(raw) if raw else None,
        )
