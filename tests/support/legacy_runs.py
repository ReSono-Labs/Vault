"""Old-engine run rows (work_id IS NULL) as the retired engine left them, for read/recovery tests (B4)."""
from __future__ import annotations

import psycopg
from psycopg.types.json import Jsonb


def insert_legacy_run(url, *, user_id, workspace_id, local_session_id, request, state="accepted"):
    with psycopg.connect(url) as connection:
        connection.execute(
            """INSERT INTO vault_private.vault_background_runs
               (run_id,user_id,workspace_id,local_session_id,request_json,state)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (request.run_id, user_id, workspace_id, local_session_id, Jsonb(request.payload()), state),
        )
