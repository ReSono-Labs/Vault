from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hmac import compare_digest
import secrets
from collections.abc import Callable
from typing import TYPE_CHECKING

from app.core.security.passwords import hash_password, verify_password
from app.core.security.tokens import hash_token
from app.vault_runtime.local_identity.models import LocalPrincipal, LocalSessionTokens, LocalUserProvisioning, LocalWorkspace
from app.vault_runtime.local_identity.repository import (
    LocalAuthorizationError,
    LocalIdentityConflictError,
    LocalIdentityRepository,
)

if TYPE_CHECKING:
    from app.vault_runtime.workspace_storage import WorkspaceStorage

SESSION_TTL_DAYS = 30
ACTIVATION_TTL_DAYS = 7
MINIMUM_PASSWORD_LENGTH = 10
SECONDARY_PASSWORD_MODES = frozenset({"setup_link", "temporary_password", "master_managed"})
SECONDARY_AGE_GROUPS = frozenset({"under_18", "adult"})
_DUMMY_PASSWORD_HASH = hash_password("not-a-real-password", salt=bytes(16))


class LocalCredentialError(LocalAuthorizationError):
    code = "invalid_credentials"


class LocalPasswordChangeRequiredError(LocalAuthorizationError):
    code = "password_change_required"


def normalize_local_username(value: str) -> str:
    normalized = value.strip().casefold()
    if not normalized or len(normalized) > 64:
        raise ValueError("A local username between 1 and 64 characters is required.")
    if any(character.isspace() for character in normalized):
        raise ValueError("Local usernames cannot contain whitespace.")
    return normalized


def normalize_display_name(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > 120:
        raise ValueError("A display name between 1 and 120 characters is required.")
    return normalized


def normalize_experience_style(value: str) -> str:
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > 120:
        raise ValueError("An experience style between 1 and 120 characters is required.")
    return normalized


class LocalIdentityService:
    def __init__(
        self, *, repository: LocalIdentityRepository, setup_credential_hash: str | None = None,
        setup_credential_consumer: Callable[[], None] | None = None,
        workspace_storage: "WorkspaceStorage | None" = None,
    ) -> None:
        self._repository = repository
        self._setup_credential_hash = setup_credential_hash
        self._setup_credential_consumer = setup_credential_consumer
        self._workspace_storage = workspace_storage

    def ensure_schema(self) -> None:
        self._repository.ensure_schema()

    def setup_complete(self) -> bool:
        return self._repository.user_count() > 0

    def validate_setup_credential(self, setup_credential: str) -> None:
        if self.setup_complete():
            raise LocalIdentityConflictError("Vault setup has already been completed.")
        supplied_hash = hash_token(setup_credential)
        if not self._setup_credential_hash or not compare_digest(supplied_hash, self._setup_credential_hash):
            raise LocalCredentialError("Setup credential is invalid.")

    def bootstrap_owner_minimal(
        self, *, setup_credential: str, display_name: str, experience_style: str,
    ) -> tuple[LocalSessionTokens, str, str]:
        """Grounded two-question onboarding with generated local recovery auth."""
        generated_username = "owner"
        generated_password = secrets.token_urlsafe(24)
        tokens = self.bootstrap_owner(
            setup_credential=setup_credential, username=generated_username,
            password=generated_password, display_name=display_name,
            experience_style=experience_style,
        )
        return tokens, generated_username, generated_password

    def bootstrap_owner(
        self,
        *,
        setup_credential: str,
        username: str,
        password: str,
        display_name: str,
        experience_style: str,
    ) -> LocalSessionTokens:
        if self._repository.user_count() != 0:
            raise LocalIdentityConflictError("Vault setup has already been completed.")
        self.validate_setup_credential(setup_credential)
        tokens = self._create_user_and_login(
            username=username, password=password, display_name=display_name, experience_style=experience_style
        )
        if self._setup_credential_consumer is not None:
            self._setup_credential_consumer()
        self._setup_credential_hash = None
        return tokens

    def create_user(
        self,
        *,
        actor: LocalPrincipal,
        username: str,
        password: str,
        display_name: str,
        experience_style: str,
    ) -> tuple[str, str]:
        if not actor.is_device_owner:
            raise LocalAuthorizationError("Vault owner authority is required.")
        return self._create_user_record(
            username=username, password=password, display_name=display_name, experience_style=experience_style
        )

    def provision_user(
        self, *, actor: LocalPrincipal, username: str, display_name: str,
        experience_style: str, password_mode: str, age_group: str,
        password: str | None = None,
    ) -> LocalUserProvisioning:
        if not actor.is_device_owner:
            raise LocalAuthorizationError("Vault master authority is required.")
        mode = password_mode.strip()
        if mode not in SECONDARY_PASSWORD_MODES:
            raise ValueError("passwordMode must be setup_link, temporary_password, or master_managed.")
        normalized_age_group = age_group.strip()
        if normalized_age_group not in SECONDARY_AGE_GROUPS:
            raise ValueError("ageGroup must be under_18 or adult.")
        setup_credential = secrets.token_urlsafe(32) if mode == "setup_link" else None
        supplied_password = password or ""
        if mode != "setup_link" and len(supplied_password) < MINIMUM_PASSWORD_LENGTH:
            raise ValueError("Password must contain at least 10 characters.")
        placeholder = supplied_password if mode != "setup_link" else secrets.token_urlsafe(32)
        user_id, workspace_id = self._create_user_record(
            username=username, password=placeholder, display_name=display_name,
            experience_style=experience_style, password_mode=mode,
            must_change_password=mode == "temporary_password",
            activation_token_hash=hash_token(setup_credential) if setup_credential else None,
            activation_expires_at=(datetime.now(UTC) + timedelta(days=ACTIVATION_TTL_DAYS)) if setup_credential else None,
            age_group=normalized_age_group,
        )
        return LocalUserProvisioning(user_id, workspace_id, mode, setup_credential)

    def list_users(self, *, actor: LocalPrincipal) -> list[dict[str, object]]:
        if not actor.is_device_owner:
            raise LocalAuthorizationError("Vault owner authority is required.")
        return self._repository.list_users()

    def change_password(self, *, principal: LocalPrincipal, current_password: str, new_password: str) -> None:
        if principal.password_mode == "master_managed":
            raise LocalAuthorizationError("This password is managed by the Vault master account.")
        if len(new_password) < MINIMUM_PASSWORD_LENGTH:
            raise ValueError("Password must contain at least 10 characters.")
        record = self._repository.authentication_record(username=principal.username)
        stored_hash = str(record[4]) if record is not None else _DUMMY_PASSWORD_HASH
        if record is None or str(record[0]) != principal.user_id or not verify_password(current_password, stored_hash):
            raise LocalCredentialError("Current password is invalid.")
        self._repository.change_password(
            user_id=principal.user_id, session_id=principal.session_id,
            password_hash=hash_password(new_password),
        )

    def verify_current_password(self, *, principal: LocalPrincipal, current_password: str) -> None:
        if principal.password_mode == "master_managed":
            raise LocalAuthorizationError("This password is managed by the Vault master account.")
        record = self._repository.authentication_record(username=principal.username)
        stored_hash = str(record[4]) if record is not None else _DUMMY_PASSWORD_HASH
        if record is None or str(record[0]) != principal.user_id or not verify_password(current_password, stored_hash):
            raise LocalCredentialError("Current password is invalid.")

    def reset_user_password(
        self, *, actor: LocalPrincipal, user_id: str, new_password: str | None,
        password_mode: str = "temporary_password",
    ) -> str | None:
        if not actor.is_device_owner:
            raise LocalAuthorizationError("Vault master authority is required.")
        if user_id == actor.user_id:
            raise LocalAuthorizationError("Use the master account password-change control.")
        mode = password_mode.strip()
        if mode not in SECONDARY_PASSWORD_MODES:
            raise ValueError("passwordMode must be setup_link, temporary_password, or master_managed.")
        setup_credential = secrets.token_urlsafe(32) if mode == "setup_link" else None
        supplied_password = new_password or ""
        if mode != "setup_link" and len(supplied_password) < MINIMUM_PASSWORD_LENGTH:
            raise ValueError("Password must contain at least 10 characters.")
        self._repository.owner_reset_user_password(
            user_id=user_id,
            password_hash=hash_password(supplied_password if mode != "setup_link" else secrets.token_urlsafe(32)),
            password_mode=mode, must_change_password=mode == "temporary_password",
            activation_token_hash=hash_token(setup_credential) if setup_credential else None,
            activation_expires_at=(datetime.now(UTC) + timedelta(days=ACTIVATION_TTL_DAYS)) if setup_credential else None,
        )
        return setup_credential

    def activate_user(self, *, setup_credential: str, new_password: str) -> LocalSessionTokens:
        if len(new_password) < MINIMUM_PASSWORD_LENGTH:
            raise ValueError("Password must contain at least 10 characters.")
        user_id, username, display_name, experience_style, workspace_id, age_group = self._repository.activate_user(
            token_hash=hash_token(setup_credential), password_hash=hash_password(new_password),
        )
        return self._issue_session(
            user_id=user_id, username=username, display_name=display_name,
            experience_style=experience_style, workspace_id=workspace_id,
            is_device_owner=False, password_mode="user_managed", must_change_password=False,
            age_group=age_group,
        )

    def remove_user(self, *, actor: LocalPrincipal, user_id: str) -> None:
        if not actor.is_device_owner:
            raise LocalAuthorizationError("Vault master authority is required.")
        if user_id == actor.user_id:
            raise LocalAuthorizationError("The master account cannot be removed.")
        owned_workspaces = self._repository.owned_workspace_ids(user_id=user_id)
        self._repository.owner_remove_user(user_id=user_id)
        if self._workspace_storage is not None:
            self._workspace_storage.remove_user(
                user_id=user_id, owned_workspace_ids=owned_workspaces,
            )

    def _create_user_and_login(self, **values: str) -> LocalSessionTokens:
        username = normalize_local_username(values["username"])
        user_id, workspace_id = self._create_user_record(**values, require_empty=True)
        return self._issue_session(
            user_id=user_id,
            username=username,
            display_name=normalize_display_name(values["display_name"]),
            experience_style=normalize_experience_style(values["experience_style"]),
            workspace_id=workspace_id,
        )

    def _create_user_record(
        self, *, username: str, password: str, display_name: str, experience_style: str,
        require_empty: bool = False, password_mode: str = "user_managed",
        must_change_password: bool = False, activation_token_hash: str | None = None,
        activation_expires_at: datetime | None = None, age_group: str = "adult",
    ) -> tuple[str, str]:
        if len(password) < MINIMUM_PASSWORD_LENGTH:
            raise ValueError("Password must contain at least 10 characters.")
        created = self._repository.create_user_with_private_workspace(
            username=normalize_local_username(username),
            display_name=normalize_display_name(display_name),
            experience_style=normalize_experience_style(experience_style),
            password_hash=hash_password(password),
            password_mode=password_mode, must_change_password=must_change_password,
            activation_token_hash=activation_token_hash, activation_expires_at=activation_expires_at,
            age_group=age_group,
            require_empty=require_empty,
        )
        if self._workspace_storage is not None:
            try:
                self._workspace_storage.provision(user_id=created[0], workspace_id=created[1])
            except Exception:
                self._repository.remove_unprovisioned_user(user_id=created[0])
                raise
        return created

    def login(self, *, username: str, password: str) -> LocalSessionTokens:
        normalized = normalize_local_username(username)
        record = self._repository.authentication_record(username=normalized)
        stored_hash = str(record[4]) if record is not None else _DUMMY_PASSWORD_HASH
        password_valid = verify_password(password, stored_hash)
        if record is None or str(record[6]) != "active" or not password_valid:
            if record is not None and str(record[6]) == "active":
                self._repository.record_login_failure(user_id=str(record[0]))
            raise LocalCredentialError("Username or password is invalid.")
        user_id = str(record[0])
        self._repository.record_login_success(user_id=user_id)
        return self._issue_session(
            user_id=user_id, username=str(record[1]), display_name=str(record[2]),
            experience_style=str(record[3]), is_device_owner=bool(record[5]),
            workspace_id=self._repository.primary_workspace_id(user_id=user_id),
            password_mode=str(record[8]), must_change_password=bool(record[9]),
            age_group=str(record[10]),
        )

    def _issue_session(
        self, *, user_id: str, username: str, display_name: str, experience_style: str,
        workspace_id: str, is_device_owner: bool = True,
        password_mode: str = "user_managed", must_change_password: bool = False,
        age_group: str = "adult",
    ) -> LocalSessionTokens:
        issued_at = datetime.now(UTC)
        expires_at = issued_at + timedelta(days=SESSION_TTL_DAYS)
        session_token, csrf_token = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        session_id = self._repository.create_session(
            user_id=user_id, token_hash=hash_token(session_token), csrf_token_hash=hash_token(csrf_token),
            workspace_id=workspace_id, issued_at=issued_at, expires_at=expires_at,
        )
        principal = LocalPrincipal(
            user_id=user_id, username=username, display_name=display_name,
            experience_style=experience_style, is_device_owner=is_device_owner, session_id=session_id,
            password_mode=password_mode, must_change_password=must_change_password,
            age_group=age_group,
            workspace_id=workspace_id, expires_at=expires_at,
        )
        return LocalSessionTokens(session_token=session_token, csrf_token=csrf_token, principal=principal)

    def authenticate(self, *, session_token: str, allow_restricted: bool = False) -> LocalPrincipal:
        principal = self._repository.resolve_session(token_hash=hash_token(session_token))
        if principal.must_change_password and not allow_restricted:
            raise LocalPasswordChangeRequiredError("Password change is required before using Vault.")
        return principal

    def require_csrf(self, *, principal: LocalPrincipal, csrf_token: str) -> None:
        self._repository.verify_csrf(session_id=principal.session_id, csrf_token_hash=hash_token(csrf_token))

    def refresh(self, *, session_token: str, csrf_token: str) -> LocalSessionTokens:
        principal = self.authenticate(session_token=session_token)
        self.require_csrf(principal=principal, csrf_token=csrf_token)
        issued_at = datetime.now(UTC)
        expires_at = issued_at + timedelta(days=SESSION_TTL_DAYS)
        new_session_token, new_csrf_token = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        new_session_id, workspace_id = self._repository.rotate_session(
            old_token_hash=hash_token(session_token), new_token_hash=hash_token(new_session_token),
            new_csrf_token_hash=hash_token(new_csrf_token), issued_at=issued_at, expires_at=expires_at,
        )
        return LocalSessionTokens(
            session_token=new_session_token, csrf_token=new_csrf_token,
            principal=LocalPrincipal(
                user_id=principal.user_id, username=principal.username, display_name=principal.display_name,
                experience_style=principal.experience_style, is_device_owner=principal.is_device_owner,
                password_mode=principal.password_mode, must_change_password=principal.must_change_password,
                age_group=principal.age_group,
                session_id=new_session_id,
                workspace_id=workspace_id, expires_at=expires_at,
            ),
        )

    def logout(self, *, session_token: str, csrf_token: str) -> None:
        principal = self.authenticate(session_token=session_token, allow_restricted=True)
        self.require_csrf(principal=principal, csrf_token=csrf_token)
        self._repository.revoke_session(token_hash=hash_token(session_token))

    def list_workspaces(self, *, principal: LocalPrincipal) -> list[LocalWorkspace]:
        return self._repository.list_workspaces(user_id=principal.user_id)

    def create_workspace(self, *, principal: LocalPrincipal, display_name: str) -> str:
        workspace_id = self._repository.create_workspace(
            owner_user_id=principal.user_id, display_name=normalize_display_name(display_name)
        )
        if self._workspace_storage is not None:
            try:
                self._workspace_storage.provision_workspace(
                    owner_user_id=principal.user_id, workspace_id=workspace_id,
                )
            except Exception:
                self._repository.remove_unprovisioned_workspace(workspace_id=workspace_id)
                raise
        return workspace_id

    def add_member(self, *, principal: LocalPrincipal, workspace_id: str, username: str) -> None:
        member_id = self._repository.active_user_id(username=normalize_local_username(username))
        self._repository.add_member(
            actor_user_id=principal.user_id, workspace_id=workspace_id, member_user_id=member_id
        )

    def revoke_member(self, *, principal: LocalPrincipal, workspace_id: str, username: str) -> None:
        member_id = self._repository.active_user_id(username=normalize_local_username(username))
        self._repository.revoke_member(
            actor_user_id=principal.user_id, workspace_id=workspace_id, member_user_id=member_id
        )

    def switch_workspace(self, *, principal: LocalPrincipal, workspace_id: str) -> None:
        self._repository.switch_workspace(
            session_id=principal.session_id, user_id=principal.user_id, workspace_id=workspace_id
        )
