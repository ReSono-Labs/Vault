from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os

import psycopg
import pytest

from app.core.security.tokens import hash_token
from app.vault_runtime.local_identity.repository import (
    LocalAuthorizationError,
    LocalIdentityConflictError,
    LocalIdentityRepository,
    LocalSessionError,
    LocalUserLimitError,
)
from app.vault_runtime.local_identity.service import (
    LocalCredentialError,
    LocalIdentityService,
    LocalPasswordChangeRequiredError,
)


@pytest.fixture()
def identity_service():
    database_url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("VAULT_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
    setup_credential = "phase2-setup-credential"
    repository = LocalIdentityRepository(database_url=database_url)
    service = LocalIdentityService(
        repository=repository, setup_credential_hash=hash_token(setup_credential)
    )
    service.ensure_schema()
    yield service, repository, setup_credential
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")


def _bootstrap(service: LocalIdentityService, setup_credential: str):
    return service.bootstrap_owner(
        setup_credential=setup_credential, username="owner", password="owner-password",
        display_name="Owner", experience_style="concise",
    )


def test_bootstrap_is_one_time_and_stores_only_hashes(identity_service) -> None:
    service, repository, setup_credential = identity_service
    owner = _bootstrap(service, setup_credential)
    assert service.authenticate(session_token=owner.session_token).username == "owner"
    with pytest.raises(LocalIdentityConflictError):
        _bootstrap(service, setup_credential)
    with repository._connect() as connection:
        row = connection.execute(
            "SELECT password_hash FROM vault_private.local_users WHERE username_normalized = 'owner'"
        ).fetchone()
        session = connection.execute(
            "SELECT token_hash, csrf_token_hash FROM vault_private.local_sessions"
        ).fetchone()
    assert row and "owner-password" not in row[0]
    assert session == (hash_token(owner.session_token), hash_token(owner.csrf_token))


def test_bootstrap_consumes_installer_credential(identity_service) -> None:
    _service, repository, setup_credential = identity_service
    consumed = []
    service = LocalIdentityService(
        repository=repository, setup_credential_hash=hash_token(setup_credential),
        setup_credential_consumer=lambda: consumed.append(True),
    )
    _bootstrap(service, setup_credential)
    assert consumed == [True]
    with pytest.raises(LocalIdentityConflictError):
        service.bootstrap_owner(
            setup_credential=setup_credential, username="again", password="password-again",
            display_name="Again", experience_style="strict",
        )


def test_exactly_four_users_survive_concurrent_fifth_user_race(identity_service) -> None:
    service, repository, setup_credential = identity_service
    owner = _bootstrap(service, setup_credential).principal
    service.create_user(
        actor=owner, username="user2", password="password-02", display_name="User Two", experience_style="warm"
    )
    service.create_user(
        actor=owner, username="user3", password="password-03", display_name="User Three", experience_style="funny"
    )

    def create(number: int):
        return service.create_user(
            actor=owner, username=f"racer{number}", password=f"password-{number:02d}",
            display_name=f"Racer {number}", experience_style="strict",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(create, number) for number in (4, 5)]
    outcomes = []
    for future in futures:
        try:
            future.result()
            outcomes.append("created")
        except LocalUserLimitError:
            outcomes.append("limited")
    assert sorted(outcomes) == ["created", "limited"]
    assert repository.user_count() == 4


def test_five_bad_passwords_lock_account_with_generic_errors(identity_service) -> None:
    service, repository, setup_credential = identity_service
    _bootstrap(service, setup_credential)
    for _attempt in range(5):
        with pytest.raises(LocalCredentialError, match="Username or password"):
            service.login(username="owner", password="incorrect-password")
    record = repository.authentication_record(username="owner")
    assert record is not None and record[6] == "locked" and record[7] == 5
    with pytest.raises(LocalCredentialError, match="Username or password"):
        service.login(username="owner", password="owner-password")
    with pytest.raises(LocalCredentialError, match="Username or password"):
        service.login(username="does-not-exist", password="owner-password")


def test_refresh_rotation_csrf_replay_and_logout(identity_service) -> None:
    service, _repository, setup_credential = identity_service
    owner = _bootstrap(service, setup_credential)
    with pytest.raises(LocalSessionError):
        service.refresh(session_token=owner.session_token, csrf_token="wrong-csrf")
    refreshed = service.refresh(
        session_token=owner.session_token, csrf_token=owner.csrf_token
    )
    with pytest.raises(LocalSessionError):
        service.authenticate(session_token=owner.session_token)
    with pytest.raises(LocalSessionError):
        service.refresh(session_token=owner.session_token, csrf_token=owner.csrf_token)
    assert service.authenticate(session_token=refreshed.session_token).user_id == owner.principal.user_id
    service.logout(session_token=refreshed.session_token, csrf_token=refreshed.csrf_token)
    with pytest.raises(LocalSessionError):
        service.authenticate(session_token=refreshed.session_token)


def test_password_change_verifies_current_and_revokes_other_sessions(identity_service) -> None:
    service, repository, setup_credential = identity_service
    first = _bootstrap(service, setup_credential)
    second = service.login(username="owner", password="owner-password")
    with pytest.raises(LocalCredentialError, match="Current password"):
        service.change_password(
            principal=first.principal, current_password="wrong-password",
            new_password="replacement-password",
        )
    service.change_password(
        principal=first.principal, current_password="owner-password",
        new_password="replacement-password",
    )
    assert service.authenticate(session_token=first.session_token).user_id == first.principal.user_id
    with pytest.raises(LocalSessionError):
        service.authenticate(session_token=second.session_token)
    with pytest.raises(LocalCredentialError):
        service.login(username="owner", password="owner-password")
    assert service.login(username="owner", password="replacement-password").principal.user_id == first.principal.user_id
    assert len(repository.list_users()) == 1


def test_master_resets_unlocks_and_removes_secondary_account(identity_service) -> None:
    service, repository, setup_credential = identity_service
    master = _bootstrap(service, setup_credential)
    secondary_user_id, _workspace_id = service.create_user(
        actor=master.principal, username="secondary", password="secondary-password",
        display_name="Secondary", experience_style="warm",
    )
    secondary = service.login(username="secondary", password="secondary-password")
    for _attempt in range(5):
        with pytest.raises(LocalCredentialError):
            service.login(username="secondary", password="incorrect-password")
    service.reset_user_password(
        actor=master.principal, user_id=secondary_user_id, new_password="temporary-password",
    )
    with pytest.raises(LocalSessionError):
        service.authenticate(session_token=secondary.session_token)
    with pytest.raises(LocalCredentialError):
        service.login(username="secondary", password="secondary-password")
    reset_session = service.login(username="secondary", password="temporary-password")
    service.remove_user(actor=master.principal, user_id=secondary_user_id)
    with pytest.raises(LocalSessionError):
        service.authenticate(session_token=reset_session.session_token)
    with pytest.raises(LocalCredentialError):
        service.login(username="secondary", password="temporary-password")
    assert [item["username"] for item in repository.list_users()] == ["owner"]
    with repository._connect() as connection:
        workspace_status = connection.execute(
            "SELECT status FROM vault_private.local_workspaces WHERE owner_user_id=%s",
            (secondary_user_id,),
        ).fetchone()
        membership_status = connection.execute(
            "SELECT status FROM vault_private.local_workspace_memberships WHERE user_id=%s",
            (secondary_user_id,),
        ).fetchone()
        deleted_identity = connection.execute(
            "SELECT username_normalized,display_name,password_hash,status FROM vault_private.local_users WHERE user_id=%s",
            (secondary_user_id,),
        ).fetchone()
    assert workspace_status is None
    assert membership_status is None
    assert deleted_identity is not None
    assert str(deleted_identity[0]).startswith("deleted-")
    assert deleted_identity[1:] == ("Deleted user", "deleted", "deleted")


def test_master_selects_setup_temporary_or_managed_password_control(identity_service) -> None:
    service, _repository, setup_credential = identity_service
    master = _bootstrap(service, setup_credential)

    linked = service.provision_user(
        actor=master.principal, username="linked", display_name="Linked",
        experience_style="warm", password_mode="setup_link", age_group="under_18",
    )
    assert linked.setup_credential
    activated = service.activate_user(
        setup_credential=linked.setup_credential, new_password="linked-password",
    )
    assert activated.principal.password_mode == "user_managed"
    assert activated.principal.age_group == "under_18"
    with pytest.raises(LocalAuthorizationError, match="invalid or expired"):
        service.activate_user(
            setup_credential=linked.setup_credential, new_password="another-password",
        )

    temporary = service.provision_user(
        actor=master.principal, username="temporary", display_name="Temporary",
        experience_style="strict", password_mode="temporary_password",
        password="temporary-password", age_group="adult",
    )
    temporary_session = service.login(username="temporary", password="temporary-password")
    assert temporary.password_mode == "temporary_password"
    with pytest.raises(LocalPasswordChangeRequiredError):
        service.authenticate(session_token=temporary_session.session_token)
    restricted = service.authenticate(
        session_token=temporary_session.session_token, allow_restricted=True,
    )
    service.change_password(
        principal=restricted, current_password="temporary-password",
        new_password="chosen-password",
    )
    assert service.authenticate(session_token=temporary_session.session_token).password_mode == "user_managed"

    managed = service.provision_user(
        actor=master.principal, username="managed", display_name="Managed",
        experience_style="concise", password_mode="master_managed",
        password="managed-password", age_group="adult",
    )
    managed_session = service.login(username="managed", password="managed-password")
    assert managed.password_mode == "master_managed"
    with pytest.raises(LocalAuthorizationError, match="managed by the Vault master"):
        service.change_password(
            principal=managed_session.principal, current_password="managed-password",
            new_password="self-changed-password",
        )


def test_secondary_age_group_is_required_and_bounded(identity_service) -> None:
    service, repository, setup_credential = identity_service
    master = _bootstrap(service, setup_credential)
    with pytest.raises(ValueError, match="ageGroup"):
        service.provision_user(
            actor=master.principal, username="unknown", display_name="Unknown",
            experience_style="warm", password_mode="setup_link", age_group="unknown",
        )
    service.provision_user(
        actor=master.principal, username="minor", display_name="Minor",
        experience_style="warm", password_mode="setup_link", age_group="under_18",
    )
    listed = {item["username"]: item for item in repository.list_users()}
    assert listed["owner"]["ageGroup"] == "adult"
    assert listed["minor"]["ageGroup"] == "under_18"


def test_master_identity_is_protected_and_secondary_has_no_admin_authority(identity_service) -> None:
    service, _repository, setup_credential = identity_service
    master = _bootstrap(service, setup_credential)
    secondary_id, _workspace_id = service.create_user(
        actor=master.principal, username="secondary", password="secondary-password",
        display_name="Secondary", experience_style="strict",
    )
    secondary = service.login(username="secondary", password="secondary-password")
    with pytest.raises(LocalAuthorizationError, match="master account cannot"):
        service.remove_user(actor=master.principal, user_id=master.principal.user_id)
    with pytest.raises(LocalAuthorizationError, match="master account password-change"):
        service.reset_user_password(
            actor=master.principal, user_id=master.principal.user_id,
            new_password="replacement-password",
        )
    with pytest.raises(LocalAuthorizationError, match="master authority"):
        service.reset_user_password(
            actor=secondary.principal, user_id=secondary_id,
            new_password="replacement-password",
        )
    with pytest.raises(LocalAuthorizationError, match="master authority"):
        service.remove_user(actor=secondary.principal, user_id=secondary_id)


def test_workspace_isolation_sharing_and_immediate_revocation(identity_service) -> None:
    service, repository, setup_credential = identity_service
    owner_tokens = _bootstrap(service, setup_credential)
    service.create_user(
        actor=owner_tokens.principal, username="second", password="second-password",
        display_name="Second", experience_style="warm",
    )
    second_tokens = service.login(username="second", password="second-password")
    owner_workspace = owner_tokens.principal.workspace_id
    second_workspace = second_tokens.principal.workspace_id
    with pytest.raises(LocalAuthorizationError):
        service.switch_workspace(principal=owner_tokens.principal, workspace_id=second_workspace)
    with pytest.raises(LocalAuthorizationError):
        service.switch_workspace(principal=second_tokens.principal, workspace_id=owner_workspace)

    service.add_member(
        principal=owner_tokens.principal, workspace_id=owner_workspace, username="second"
    )
    service.switch_workspace(principal=second_tokens.principal, workspace_id=owner_workspace)
    switched = service.authenticate(session_token=second_tokens.session_token)
    assert switched.workspace_id == owner_workspace

    service.revoke_member(
        principal=owner_tokens.principal, workspace_id=owner_workspace, username="second"
    )
    with pytest.raises(LocalSessionError):
        service.authenticate(session_token=second_tokens.session_token)
    with pytest.raises(LocalAuthorizationError):
        repository.revoke_member(
            actor_user_id=owner_tokens.principal.user_id,
            workspace_id=owner_workspace,
            member_user_id=owner_tokens.principal.user_id,
        )


def test_all_four_users_are_denied_every_other_private_workspace(identity_service) -> None:
    service, _repository, setup_credential = identity_service
    tokens = [_bootstrap(service, setup_credential)]
    for number in range(2, 5):
        service.create_user(
            actor=tokens[0].principal, username=f"user{number}", password=f"password-{number:02d}",
            display_name=f"User {number}", experience_style="concise",
        )
        tokens.append(service.login(username=f"user{number}", password=f"password-{number:02d}"))
    for actor_index, actor_tokens in enumerate(tokens):
        for workspace_index, target_tokens in enumerate(tokens):
            if actor_index == workspace_index:
                continue
            with pytest.raises(LocalAuthorizationError):
                service.switch_workspace(
                    principal=actor_tokens.principal,
                    workspace_id=target_tokens.principal.workspace_id,
                )


def test_ordinary_workspace_owner_cannot_create_device_users(identity_service) -> None:
    service, _repository, setup_credential = identity_service
    device_owner = _bootstrap(service, setup_credential)
    service.create_user(
        actor=device_owner.principal, username="ordinary", password="ordinary-password",
        display_name="Ordinary", experience_style="warm",
    )
    ordinary = service.login(username="ordinary", password="ordinary-password")
    assert ordinary.principal.is_device_owner is False
    with pytest.raises(LocalAuthorizationError, match="Vault owner"):
        service.create_user(
            actor=ordinary.principal, username="unauthorized", password="unauthorized-password",
            display_name="Unauthorized", experience_style="strict",
        )


def test_expired_session_and_schema_fingerprint(identity_service) -> None:
    service, repository, setup_credential = identity_service
    owner = _bootstrap(service, setup_credential)
    service.ensure_schema()
    with repository._connect() as connection:
        connection.execute(
            "UPDATE vault_private.local_sessions SET expires_at = now() - interval '1 second' WHERE session_id = %s",
            (owner.principal.session_id,),
        )
        fingerprint = connection.execute(
            "SELECT schema_fingerprint FROM vault_private.local_schema_metadata WHERE schema_key = 'local_identity_v1'"
        ).fetchone()
    assert fingerprint is not None and len(fingerprint[0]) == 64
    with pytest.raises(LocalSessionError):
        service.authenticate(session_token=owner.session_token)
