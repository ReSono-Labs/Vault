"""Existing Voice/Conversation current-session predicate, shared without policy changes."""
from typing import Any


def has_current_session_scope(
    cursor: Any, *, user_id: str, workspace_id: str,
    local_session_id: str, lock: bool = False,
) -> bool:
    cursor.execute(
        """SELECT 1 FROM vault_private.local_sessions s
           JOIN vault_private.local_users u ON u.user_id=s.user_id
           JOIN vault_private.local_workspace_memberships m
             ON m.workspace_id=%s AND m.user_id=s.user_id
           JOIN vault_private.local_workspaces w ON w.workspace_id=m.workspace_id
           WHERE s.session_id=%s AND s.user_id=%s AND s.active_workspace_id=%s
             AND s.status='active' AND s.expires_at>now()
             AND u.status='active' AND m.status='active' AND w.status='active'"""
        + (" FOR SHARE OF s,u,m,w" if lock else ""),
        (workspace_id, local_session_id, user_id, workspace_id),
    )
    return cursor.fetchone() is not None
