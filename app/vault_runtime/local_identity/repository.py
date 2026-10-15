from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.vault_runtime.local_identity.models import LocalPrincipal, LocalWorkspace
from app.vault_runtime.local_identity.schema import ensure_local_identity_schema

MAX_LOCAL_USERS = 4
LOGIN_FAILURE_LOCK_THRESHOLD = 5
_USER_LIMIT_ADVISORY_LOCK = 8_603_156_482_023_441_201


class LocalIdentityError(RuntimeError):
    code = "local_identity_error"


class LocalUserLimitError(LocalIdentityError):
    code = "local_user_limit_reached"


class LocalIdentityConflictError(LocalIdentityError):
    code = "local_identity_conflict"


class LocalAuthorizationError(LocalIdentityError):
    code = "local_authorization_denied"


class LocalSessionError(LocalIdentityError):
    code = "local_session_invalid"


class LocalIdentityRepository:
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
                ensure_local_identity_schema(cursor)

    def create_user_with_private_workspace(
        self,
        *,
        username: str,
        display_name: str,
        experience_style: str,
        password_hash: str,
        password_mode: str = "user_managed",
        must_change_password: bool = False,
        activation_token_hash: str | None = None,
        activation_expires_at: datetime | None = None,
        age_group: str = "adult",
        require_empty: bool = False,
    ) -> tuple[str, str]:
        user_id, workspace_id = str(uuid4()), str(uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (_USER_LIMIT_ADVISORY_LOCK,))
                cursor.execute(
                    "SELECT count(*) FROM vault_private.local_users WHERE status <> 'deleted'"
                )
                user_count = int(cursor.fetchone()[0])
                if require_empty and user_count != 0:
                    raise LocalIdentityConflictError("Vault setup has already been completed.")
                if user_count >= MAX_LOCAL_USERS:
                    raise LocalUserLimitError("Vault supports at most four local users.")
                cursor.execute(
                    "SELECT 1 FROM vault_private.local_users WHERE username_normalized = %s",
                    (username,),
                )
                if cursor.fetchone() is not None:
                    raise LocalIdentityConflictError("That local username is unavailable.")
                cursor.execute(
                    """
                    INSERT INTO vault_private.local_users
                      (user_id, username_normalized, display_name, experience_style, password_hash, is_device_owner,
                       password_mode,must_change_password,activation_token_hash,activation_expires_at,age_group)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (user_id, username, display_name, experience_style, password_hash, require_empty,
                     password_mode,must_change_password,activation_token_hash,activation_expires_at,age_group),
                )
                cursor.execute(
                    """
                    INSERT INTO vault_private.local_workspaces
                      (workspace_id, owner_user_id, display_name)
                    VALUES (%s, %s, %s)
                    """,
                    (workspace_id, user_id, f"{display_name}'s Vault"),
                )
                cursor.execute(
                    """
                    INSERT INTO vault_private.local_workspace_memberships
                      (membership_id, workspace_id, user_id, membership_type)
                    VALUES (%s, %s, %s, 'owner')
                    """,
                    (str(uuid4()), workspace_id, user_id),
                )
        return user_id, workspace_id

    def authentication_record(self, *, username: str) -> tuple[Any, ...] | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT user_id, username_normalized, display_name, experience_style,
                           password_hash, is_device_owner, status, failed_login_count,
                           password_mode,must_change_password,age_group
                    FROM vault_private.local_users
                    WHERE username_normalized = %s
                    """,
                    (username,),
                )
                return cursor.fetchone()

    def user_count(self) -> int:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM vault_private.local_users WHERE status <> 'deleted'")
                return int(cursor.fetchone()[0])

    def active_storage_identities(self) -> tuple[tuple[str, str], ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT w.owner_user_id,w.workspace_id
                       FROM vault_private.local_workspaces w
                       JOIN vault_private.local_users u ON u.user_id=w.owner_user_id
                       WHERE u.status='active' AND w.status='active'
                       ORDER BY u.created_at,w.created_at,w.workspace_id"""
                )
                return tuple((str(row[0]), str(row[1])) for row in cursor.fetchall())

    def list_users(self) -> list[dict[str, object]]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT user_id,username_normalized,display_name,experience_style,
                              is_device_owner,status,created_at,password_mode,must_change_password,
                              (activation_token_hash IS NOT NULL AND activation_consumed_at IS NULL),age_group
                       FROM vault_private.local_users WHERE status <> 'deleted'
                       ORDER BY is_device_owner DESC,created_at,user_id"""
                )
                return [{
                    "userId": str(row[0]), "username": str(row[1]),
                    "displayName": str(row[2]), "experienceStyle": str(row[3]),
                    "isDeviceOwner": bool(row[4]), "status": str(row[5]),
                    "createdAt": row[6].isoformat(), "passwordMode": str(row[7]),
                    "mustChangePassword": bool(row[8]), "activationPending": bool(row[9]),
                    "ageGroup": str(row[10]),
                } for row in cursor.fetchall()]

    def change_password(self, *, user_id: str, session_id: str, password_hash: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE vault_private.local_users SET password_hash=%s,
                              password_mode='user_managed',must_change_password=false,
                              activation_token_hash=NULL,activation_expires_at=NULL,
                              failed_login_count=0,updated_at=now()
                       WHERE user_id=%s AND status='active'""",
                    (password_hash,user_id),
                )
                if cursor.rowcount != 1:
                    raise LocalAuthorizationError("Local identity is unavailable.")
                cursor.execute(
                    """UPDATE vault_private.local_sessions SET status='revoked',revoked_at=now(),
                              revocation_reason='password_changed'
                       WHERE user_id=%s AND session_id<>%s AND status='active'""",
                    (user_id,session_id),
                )

    def owner_reset_user_password(
        self, *, user_id: str, password_hash: str, password_mode: str,
        must_change_password: bool, activation_token_hash: str | None = None,
        activation_expires_at: datetime | None = None,
    ) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE vault_private.local_users
                       SET password_hash=%s,password_mode=%s,must_change_password=%s,
                           activation_token_hash=%s,activation_expires_at=%s,activation_consumed_at=NULL,
                           failed_login_count=0,status='active',locked_at=NULL,updated_at=now()
                       WHERE user_id=%s AND is_device_owner=false AND status<>'deleted'""",
                    (password_hash,password_mode,must_change_password,activation_token_hash,
                     activation_expires_at,user_id),
                )
                if cursor.rowcount != 1:
                    raise LocalAuthorizationError("Secondary local account is unavailable.")
                cursor.execute(
                    """UPDATE vault_private.local_sessions
                       SET status='revoked',revoked_at=now(),revocation_reason='owner_password_reset'
                       WHERE user_id=%s AND status='active'""",
                    (user_id,),
                )

    def activate_user(self, *, token_hash: str, password_hash: str) -> tuple[str, str, str, str, str, str]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT user_id,username_normalized,display_name,experience_style,age_group
                       FROM vault_private.local_users
                       WHERE activation_token_hash=%s AND activation_consumed_at IS NULL
                         AND activation_expires_at>now() AND status='active' AND is_device_owner=false
                       FOR UPDATE""",
                    (token_hash,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise LocalAuthorizationError("Account setup credential is invalid or expired.")
                cursor.execute(
                    """UPDATE vault_private.local_users
                       SET password_hash=%s,password_mode='user_managed',must_change_password=false,
                           activation_token_hash=NULL,activation_consumed_at=now(),updated_at=now()
                       WHERE user_id=%s""",
                    (password_hash,row[0]),
                )
                cursor.execute(
                    """SELECT workspace_id FROM vault_private.local_workspace_memberships
                       WHERE user_id=%s AND membership_type='owner' AND status='active'
                       ORDER BY created_at LIMIT 1""",
                    (row[0],),
                )
                workspace = cursor.fetchone()
                if workspace is None:
                    raise LocalAuthorizationError("Local account workspace is unavailable.")
                return str(row[0]),str(row[1]),str(row[2]),str(row[3]),str(workspace[0]),str(row[4])

    def owner_remove_user(self, *, user_id: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT workspace_id FROM vault_private.local_workspaces WHERE owner_user_id=%s FOR UPDATE",
                    (user_id,),
                )
                owned_workspace_ids = tuple(str(row[0]) for row in cursor.fetchall())
                cursor.execute(
                    """UPDATE vault_private.local_users
                       SET status='deleted',username_normalized=%s,display_name='Deleted user',
                           experience_style='deleted',password_hash='deleted',password_mode='master_managed',
                           must_change_password=false,activation_token_hash=NULL,activation_expires_at=NULL,
                           activation_consumed_at=now(),failed_login_count=0,locked_at=NULL,updated_at=now()
                       WHERE user_id=%s AND is_device_owner=false AND status<>'deleted'""",
                    (f"deleted-{uuid4()}", user_id),
                )
                if cursor.rowcount != 1:
                    raise LocalAuthorizationError("Secondary local account is unavailable.")
                cursor.execute(
                    """UPDATE vault_private.local_sessions
                       SET status='revoked',revoked_at=now(),revocation_reason='owner_account_removed'
                       WHERE user_id=%s AND status='active'""",
                    (user_id,),
                )
                self._erase_user_data_cursor(
                    cursor, user_id=user_id, owned_workspace_ids=owned_workspace_ids,
                )

    @staticmethod
    def _erase_user_data_cursor(
        cursor: Any, *, user_id: str, owned_workspace_ids: tuple[str, ...],
    ) -> None:
        # Mail intentionally uses RESTRICT foreign keys. Delete leaf records
        # before accounts for both owned and shared workspaces.
        for table in (
            "vault_email_attachments", "vault_email_sync_cursors", "vault_email_messages",
            "vault_email_send_requests", "vault_email_sync_runs", "vault_email_folders",
            "vault_email_provider_credentials", "vault_email_mailbox_accounts",
        ):
            LocalIdentityRepository._delete_if_exists(
                cursor, table=table, column="account_id", value=user_id,
            )
        for table, column in (
            ("vault_conversations", "user_id"),
            ("vault_calendar_accounts", "account_id"),
            ("vault_personal_records", "account_id"),
            ("vault_memory_pending_actions", "user_id"),
            ("vault_memory_ingestions", "user_id"),
            ("vault_memory_records", "user_id"),
            ("vault_memory_scope_epochs", "user_id"),
            ("vault_session_summaries", "user_id"),
            ("vault_transcript_entries", "user_id"),
            ("vault_background_runs", "user_id"),
            ("vault_voice_tool_results", "user_id"),
            ("vault_voice_tool_invocations", "user_id"),
            ("vault_voice_tool_grants", "user_id"),
            ("vault_voice_provider_events", "user_id"),
            ("vault_voice_sessions", "user_id"),
            ("vault_voice_provider_access", "user_id"),
            ("vault_extension_grants", "user_id"),
        ):
            LocalIdentityRepository._delete_if_exists(
                cursor, table=table, column=column, value=user_id,
            )
        cursor.execute("DELETE FROM vault_private.local_sessions WHERE user_id=%s", (user_id,))
        cursor.execute(
            "DELETE FROM vault_private.local_workspace_memberships WHERE user_id=%s",
            (user_id,),
        )
        for workspace_id in owned_workspace_ids:
            LocalIdentityRepository._delete_if_exists(
                cursor, table="vault_extensions", column="installed_in_workspace_id",
                value=workspace_id,
            )
            cursor.execute(
                "DELETE FROM vault_private.local_workspaces WHERE workspace_id=%s",
                (workspace_id,),
            )

    @staticmethod
    def _delete_if_exists(cursor: Any, *, table: str, column: str, value: str) -> None:
        cursor.execute("SELECT to_regclass(%s)", (f"vault_private.{table}",))
        if cursor.fetchone()[0] is not None:
            cursor.execute(
                f"DELETE FROM vault_private.{table} WHERE {column}=%s", (value,),
            )

    def owned_workspace_ids(self, *, user_id: str) -> tuple[str, ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT workspace_id FROM vault_private.local_workspaces WHERE owner_user_id=%s ORDER BY workspace_id",
                    (user_id,),
                )
                return tuple(str(row[0]) for row in cursor.fetchall())

    def remove_unprovisioned_user(self, *, user_id: str) -> None:
        """Rollback a just-created identity whose private storage failed."""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM vault_private.local_workspaces WHERE owner_user_id=%s",
                    (user_id,),
                )
                cursor.execute("DELETE FROM vault_private.local_users WHERE user_id=%s", (user_id,))

    def remove_unprovisioned_workspace(self, *, workspace_id: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM vault_private.local_workspaces WHERE workspace_id=%s",
                    (workspace_id,),
                )

    def active_user_id(self, *, username: str) -> str:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT user_id FROM vault_private.local_users WHERE username_normalized = %s AND status = 'active'",
                    (username,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise LocalAuthorizationError("Local member is unavailable.")
                return str(row[0])

    def record_login_failure(self, *, user_id: str) -> tuple[int, str]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE vault_private.local_users
                    SET failed_login_count = failed_login_count + 1,
                        status = CASE WHEN failed_login_count + 1 >= %s THEN 'locked' ELSE status END,
                        locked_at = CASE WHEN failed_login_count + 1 >= %s THEN now() ELSE locked_at END,
                        updated_at = now()
                    WHERE user_id = %s AND status <> 'deleted'
                    RETURNING failed_login_count, status
                    """,
                    (LOGIN_FAILURE_LOCK_THRESHOLD, LOGIN_FAILURE_LOCK_THRESHOLD, user_id),
                )
                row = cursor.fetchone()
                if row is None:
                    raise LocalAuthorizationError("Local identity is unavailable.")
                return int(row[0]), str(row[1])

    def record_login_success(self, *, user_id: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE vault_private.local_users
                    SET failed_login_count = 0, last_login_at = now(), updated_at = now()
                    WHERE user_id = %s AND status = 'active'
                    """,
                    (user_id,),
                )

    def primary_workspace_id(self, *, user_id: str) -> str:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT workspace_id
                    FROM vault_private.local_workspace_memberships
                    WHERE user_id = %s AND membership_type = 'owner' AND status = 'active'
                    ORDER BY created_at, workspace_id LIMIT 1
                    """,
                    (user_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise LocalAuthorizationError("No active local workspace is available.")
                return str(row[0])

    def create_session(
        self,
        *,
        user_id: str,
        token_hash: str,
        csrf_token_hash: str,
        workspace_id: str,
        issued_at: datetime,
        expires_at: datetime,
    ) -> str:
        session_id = str(uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership_cursor(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    INSERT INTO vault_private.local_sessions
                      (session_id, user_id, token_hash, csrf_token_hash, active_workspace_id, issued_at, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (session_id, user_id, token_hash, csrf_token_hash, workspace_id, issued_at, expires_at),
                )
        return session_id

    def resolve_review_principal(self,user_id,workspace_id,session_id):
        """Internal recovery only; reuse canonical session validation, never elevate authority."""
        with self._connect() as connection,connection.cursor() as cursor:
            cursor.execute("""SELECT token_hash FROM vault_private.local_sessions
              WHERE user_id=%s AND active_workspace_id=%s AND session_id=%s""",
              (user_id,workspace_id,session_id))
            row=cursor.fetchone()
        if row is None:
            raise LocalSessionError("Review authority is unavailable.")
        principal=self.resolve_session(token_hash=row[0])
        if (principal.user_id,principal.workspace_id,principal.session_id)!=(user_id,workspace_id,session_id):
            raise LocalSessionError("Review authority changed.")
        return principal

    def resolve_session(self, *, token_hash: str, now: datetime | None = None) -> LocalPrincipal:
        effective_now = now or datetime.now(UTC)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT u.user_id, u.username_normalized, u.display_name, u.experience_style,
                           u.is_device_owner, s.session_id, s.active_workspace_id, s.expires_at,
                           u.password_mode,u.must_change_password,u.age_group
                    FROM vault_private.local_sessions s
                    JOIN vault_private.local_users u ON u.user_id = s.user_id
                    JOIN vault_private.local_workspace_memberships m
                      ON m.workspace_id = s.active_workspace_id AND m.user_id = s.user_id
                    JOIN vault_private.local_workspaces w ON w.workspace_id = s.active_workspace_id
                    WHERE s.token_hash = %s AND s.status = 'active' AND s.expires_at > %s
                      AND u.status = 'active' AND m.status = 'active' AND w.status = 'active'
                    """,
                    (token_hash, effective_now),
                )
                row = cursor.fetchone()
                if row is None:
                    raise LocalSessionError("Local session is invalid or expired.")
                cursor.execute(
                    "UPDATE vault_private.local_sessions SET last_seen_at = %s WHERE session_id = %s",
                    (effective_now, row[5]),
                )
        return LocalPrincipal(
            user_id=str(row[0]), username=str(row[1]), display_name=str(row[2]),
            experience_style=str(row[3]), is_device_owner=bool(row[4]),
            password_mode=str(row[8]), must_change_password=bool(row[9]),
            age_group=str(row[10]),
            session_id=str(row[5]), workspace_id=str(row[6]), expires_at=row[7],
        )

    def rotate_session(
        self,
        *,
        old_token_hash: str,
        new_token_hash: str,
        new_csrf_token_hash: str,
        issued_at: datetime,
        expires_at: datetime,
    ) -> tuple[str, str]:
        new_session_id = str(uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT session_id, user_id, active_workspace_id
                    FROM vault_private.local_sessions
                    WHERE token_hash = %s AND status = 'active' AND expires_at > %s
                    FOR UPDATE
                    """,
                    (old_token_hash, issued_at),
                )
                old = cursor.fetchone()
                if old is None:
                    raise LocalSessionError("Local session is invalid or expired.")
                self._require_membership_cursor(cursor, user_id=str(old[1]), workspace_id=str(old[2]))
                cursor.execute(
                    """
                    INSERT INTO vault_private.local_sessions
                      (session_id, user_id, token_hash, csrf_token_hash, active_workspace_id, issued_at, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (new_session_id, old[1], new_token_hash, new_csrf_token_hash, old[2], issued_at, expires_at),
                )
                cursor.execute(
                    """
                    UPDATE vault_private.local_sessions
                    SET status = 'rotated', revoked_at = %s, revocation_reason = 'refresh_rotated',
                        rotated_to_session_id = %s
                    WHERE session_id = %s
                    """,
                    (issued_at, new_session_id, old[0]),
                )
        return new_session_id, str(old[2])

    def revoke_session(self, *, token_hash: str, reason: str = "logout") -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE vault_private.local_sessions
                    SET status = 'revoked', revoked_at = now(), revocation_reason = %s
                    WHERE token_hash = %s AND status = 'active'
                    """,
                    (reason, token_hash),
                )

    def verify_csrf(self, *, session_id: str, csrf_token_hash: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 1 FROM vault_private.local_sessions
                    WHERE session_id = %s AND csrf_token_hash = %s AND status = 'active' AND expires_at > now()
                    """,
                    (session_id, csrf_token_hash),
                )
                if cursor.fetchone() is None:
                    raise LocalSessionError("CSRF proof is invalid.")

    def list_workspaces(self, *, user_id: str) -> list[LocalWorkspace]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT w.workspace_id, w.display_name, w.owner_user_id, m.membership_type
                    FROM vault_private.local_workspace_memberships m
                    JOIN vault_private.local_workspaces w ON w.workspace_id = m.workspace_id
                    WHERE m.user_id = %s AND m.status = 'active' AND w.status = 'active'
                    ORDER BY w.created_at, w.workspace_id
                    """,
                    (user_id,),
                )
                return [LocalWorkspace(str(row[0]), str(row[1]), str(row[2]), str(row[3])) for row in cursor.fetchall()]

    def create_workspace(self, *, owner_user_id: str, display_name: str) -> str:
        workspace_id = str(uuid4())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM vault_private.local_users WHERE user_id = %s AND status = 'active'",
                    (owner_user_id,),
                )
                if cursor.fetchone() is None:
                    raise LocalAuthorizationError("Local owner is unavailable.")
                cursor.execute(
                    "INSERT INTO vault_private.local_workspaces (workspace_id, owner_user_id, display_name) VALUES (%s, %s, %s)",
                    (workspace_id, owner_user_id, display_name),
                )
                cursor.execute(
                    """
                    INSERT INTO vault_private.local_workspace_memberships
                      (membership_id, workspace_id, user_id, membership_type)
                    VALUES (%s, %s, %s, 'owner')
                    """,
                    (str(uuid4()), workspace_id, owner_user_id),
                )
        return workspace_id

    def add_member(self, *, actor_user_id: str, workspace_id: str, member_user_id: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_owner_cursor(cursor, user_id=actor_user_id, workspace_id=workspace_id)
                cursor.execute(
                    "SELECT 1 FROM vault_private.local_users WHERE user_id = %s AND status = 'active'",
                    (member_user_id,),
                )
                if cursor.fetchone() is None:
                    raise LocalAuthorizationError("Local member is unavailable.")
                cursor.execute(
                    """
                    INSERT INTO vault_private.local_workspace_memberships
                      (membership_id, workspace_id, user_id, membership_type, status, revoked_at)
                    VALUES (%s, %s, %s, 'member', 'active', NULL)
                    ON CONFLICT (workspace_id, user_id) DO UPDATE SET
                      membership_type = 'member', status = 'active', revoked_at = NULL
                    """,
                    (str(uuid4()), workspace_id, member_user_id),
                )

    def revoke_member(self, *, actor_user_id: str, workspace_id: str, member_user_id: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_owner_cursor(cursor, user_id=actor_user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    SELECT membership_type FROM vault_private.local_workspace_memberships
                    WHERE workspace_id = %s AND user_id = %s AND status = 'active'
                    """,
                    (workspace_id, member_user_id),
                )
                target = cursor.fetchone()
                if target is not None and str(target[0]) == "owner":
                    raise LocalAuthorizationError("Workspace owner membership cannot be revoked.")
                cursor.execute(
                    """
                    UPDATE vault_private.local_workspace_memberships
                    SET status = 'revoked', revoked_at = now()
                    WHERE workspace_id = %s AND user_id = %s AND membership_type = 'member' AND status = 'active'
                    """,
                    (workspace_id, member_user_id),
                )
                cursor.execute(
                    """
                    UPDATE vault_private.local_sessions
                    SET status = 'revoked', revoked_at = now(), revocation_reason = 'workspace_membership_revoked'
                    WHERE user_id = %s AND active_workspace_id = %s AND status = 'active'
                    """,
                    (member_user_id, workspace_id),
                )

    def switch_workspace(self, *, session_id: str, user_id: str, workspace_id: str) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership_cursor(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    UPDATE vault_private.local_sessions SET active_workspace_id = %s
                    WHERE session_id = %s AND user_id = %s AND status = 'active'
                    """,
                    (workspace_id, session_id, user_id),
                )
                if cursor.rowcount != 1:
                    raise LocalSessionError("Local session is invalid.")

    @staticmethod
    def _require_membership_cursor(cursor, *, user_id: str, workspace_id: str) -> None:
        cursor.execute(
            """
            SELECT 1 FROM vault_private.local_workspace_memberships m
            JOIN vault_private.local_workspaces w ON w.workspace_id = m.workspace_id
            WHERE m.user_id = %s AND m.workspace_id = %s AND m.status = 'active' AND w.status = 'active'
            """,
            (user_id, workspace_id),
        )
        if cursor.fetchone() is None:
            raise LocalAuthorizationError("Workspace access is denied.")

    @staticmethod
    def _require_owner_cursor(cursor, *, user_id: str, workspace_id: str) -> None:
        cursor.execute(
            """
            SELECT 1 FROM vault_private.local_workspace_memberships
            WHERE user_id = %s AND workspace_id = %s
              AND membership_type = 'owner' AND status = 'active'
            """,
            (user_id, workspace_id),
        )
        if cursor.fetchone() is None:
            raise LocalAuthorizationError("Workspace owner authority is required.")
