"""Run activity events in vault_background_run_events, shared by every Background engine.

The Background work detail reads ``reasoning_summary`` (``{"summary"}``) and ``agent_evidence``
(``{"phase", "summary"}``) events from this table by run id (owner decision 5-D, BG-05)."""
from __future__ import annotations

import json
from typing import Any

import psycopg

REASONING_SUMMARY_LIMIT = 16_384


def append_run_event(
    cursor: Any, run_id: str, user_id: str, workspace_id: str,
    event_type: str, state: str, detail: dict[str, object],
) -> None:
    cursor.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"background-event:{run_id}",)
    )
    cursor.execute(
        "SELECT COALESCE(max(event_index),-1)+1 FROM vault_private.vault_background_run_events WHERE run_id=%s",
        (run_id,),
    )
    row = cursor.fetchone()
    index = int(row[0] if not isinstance(row, dict) else next(iter(row.values())))
    cursor.execute(
        """
        INSERT INTO vault_private.vault_background_run_events
          (run_id,event_index,user_id,workspace_id,event_type,state,detail_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            run_id, index, user_id, workspace_id, event_type, state,
            json.dumps(detail, separators=(",", ":")),
        ),
    )


def reasoning_summaries(response: object) -> tuple[str, ...]:
    """Reasoning summary texts in one model response (Agents SDK ModelResponse)."""
    summaries: list[str] = []
    for item in getattr(response, "output", None) or ():
        if getattr(item, "type", None) != "reasoning":
            continue
        for summary in getattr(item, "summary", None) or ():
            text = str(getattr(summary, "text", "")).strip()
            if text:
                summaries.append(text[:REASONING_SUMMARY_LIMIT])
    return tuple(summaries)


class RunEventWriter:
    """Writes reasoning and evidence events for one durable run."""

    def __init__(self, *, database_url: str) -> None:
        self._database_url = database_url

    def record(self, *, user_id: str, workspace_id: str, run_id: str,
               events: list[tuple[str, dict[str, object]]], state: str = "running") -> None:
        if not events:
            return
        with psycopg.connect(self._database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT 1 FROM vault_private.vault_background_runs
                       WHERE run_id=%s AND user_id=%s AND workspace_id=%s""",
                    (run_id, user_id, workspace_id),
                )
                if cursor.fetchone() is None:
                    return  # The run row belongs to another scope or is gone: record nothing.
                for event_type, detail in events:
                    append_run_event(cursor, run_id, user_id, workspace_id, event_type, state, detail)

    def reasoning(self, *, user_id: str, workspace_id: str, run_id: str, summaries: tuple[str, ...]) -> None:
        self.record(user_id=user_id, workspace_id=workspace_id, run_id=run_id,
                    events=[("reasoning_summary", {"summary": summary}) for summary in summaries])

    def evidence(self, *, user_id: str, workspace_id: str, run_id: str, output: dict[str, object] | None) -> None:
        items = (output or {}).get("phase_evidence") if isinstance(output, dict) else None
        self.record(user_id=user_id, workspace_id=workspace_id, run_id=run_id, events=[
            ("agent_evidence", {"phase": str(item["phase"]), "summary": str(item["summary"])})
            for item in (items if isinstance(items, list) else ())
            if isinstance(item, dict) and item.get("phase") and item.get("summary")
        ])
