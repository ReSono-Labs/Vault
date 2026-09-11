from __future__ import annotations

import os

import psycopg
import pytest

from app.vault_runtime.extensions.secrets import LocalMasterKey
from app.vault_runtime.host_filesystem.repository import HostFilesystemRepository
from app.vault_runtime.host_filesystem.service import HostFilesystemService
from app.vault_runtime.local_identity.models import LocalPrincipal
from datetime import UTC, datetime


@pytest.fixture()
def host_filesystem():
    database_url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("VAULT_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    with psycopg.connect(database_url) as connection:
        connection.execute("DELETE FROM vault_private.host_filesystem_mounts")
        connection.execute("DELETE FROM vault_private.host_filesystem_integrations")
    repository = HostFilesystemRepository(database_url=database_url)
    service = HostFilesystemService(
        repository=repository,
        credential_key=LocalMasterKey("/tmp/host-filesystem-test.key"),
    )
    principal = LocalPrincipal(
        user_id="owner-user",
        username="owner",
        display_name="Owner",
        experience_style="balanced",
        is_device_owner=True,
        session_id="session",
        workspace_id="workspace-a",
        expires_at=datetime.now(UTC),
    )
    service.save_settings(principal=principal, enabled=True)
    yield service, repository, principal
    with psycopg.connect(database_url) as connection:
        connection.execute("DELETE FROM vault_private.host_filesystem_mounts")
        connection.execute("DELETE FROM vault_private.host_filesystem_integrations")


def test_upsert_reactivates_revoked_mount_with_same_name(host_filesystem) -> None:
    service, repository, principal = host_filesystem
    first_id = "11111111-1111-1111-1111-111111111111"
    second_id = "22222222-2222-2222-2222-222222222222"
    service.register_mount(
        principal=principal,
        mount_id=first_id,
        mount_name="resono-business",
        permission="read",
        source="browser",
    )
    service.revoke_mount(principal=principal, mount_id=first_id)
    payload, prior = service.register_mount_for_import(
        principal=principal,
        mount_id=second_id,
        mount_name="resono-business",
        permission="write",
        source="browser",
    )
    assert payload["mountId"] == second_id
    assert payload["permission"] == "write"
    assert prior is not None
    assert prior.mount_id == first_id
    active = repository.get_mount_by_name(
        user_id=principal.user_id,
        workspace_id=principal.workspace_id,
        mount_name="resono-business",
    )
    assert active is not None
    assert active.mount_id == second_id
    assert active.permission == "write"


def test_register_mount_for_import_is_idempotent_for_existing_mount(host_filesystem) -> None:
    service, _repository, principal = host_filesystem
    mount_id = "33333333-3333-3333-3333-333333333333"
    service.register_mount(
        principal=principal,
        mount_id=mount_id,
        mount_name="resono-business",
        permission="read",
        source="browser",
    )
    payload, prior = service.register_mount_for_import(
        principal=principal,
        mount_id=mount_id,
        mount_name="resono-business",
        permission="read",
        source="browser",
    )
    assert payload["mountId"] == mount_id
    assert prior is None
