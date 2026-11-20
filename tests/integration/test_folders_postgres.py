from __future__ import annotations

import os

import psycopg
import pytest

from app.vault_runtime.folders.errors import FolderNameTakenError, FolderUnavailableError
from app.vault_runtime.folders.repository import FolderRepository
from app.vault_runtime.local_identity.repository import LocalIdentityRepository


@pytest.fixture
def repository() -> FolderRepository:
    database_url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("VAULT_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
    LocalIdentityRepository(database_url=database_url).ensure_schema()
    with psycopg.connect(database_url) as connection:
        # A table from the removed browser/helper feature must be dropped on startup.
        connection.execute("CREATE TABLE vault_private.host_filesystem_settings (user_id text)")
        for user_id in ("admin", "kid"):
            connection.execute(
                """INSERT INTO vault_private.local_users
                   (user_id, username_normalized, display_name, experience_style, password_hash)
                   VALUES (%s, %s, %s, 'balanced', 'x')""",
                (user_id, user_id, user_id),
            )
    repository = FolderRepository(database_url=database_url)
    repository.ensure_schema()
    repository.ensure_schema()  # Idempotent across restarts.
    repository.database_url = database_url  # type: ignore[attr-defined]
    return repository


def test_legacy_tables_are_dropped(repository: FolderRepository) -> None:
    with psycopg.connect(repository.database_url) as connection:  # type: ignore[attr-defined]
        row = connection.execute("SELECT to_regclass('vault_private.host_filesystem_settings')").fetchone()
    assert row == (None,)


def test_grants_folders_and_cascades(repository: FolderRepository) -> None:
    grant = repository.upsert_grant(
        user_id="kid", location_id="home", relative_path="Documents", max_permission="write", created_by="admin",
    )
    again = repository.upsert_grant(
        user_id="kid", location_id="home", relative_path="Documents", max_permission="write", created_by="admin",
    )
    assert again.grant_id == grant.grant_id

    folder = repository.insert_folder(
        user_id="kid", grant_id=grant.grant_id, relative_path="Projects", name="Projects",
        permission="write", created_vault=False,
    )
    with pytest.raises(FolderNameTakenError):
        repository.insert_folder(
            user_id="kid", grant_id=grant.grant_id, relative_path="Other", name="projects",
            permission="read", created_vault=False,
        )
    assert repository.get_folder_by_name(user_id="kid", name="PROJECTS") == folder
    assert repository.get_folder(user_id="admin", folder_id=folder.folder_id) is None
    assert repository.folder_counts(grant_ids=[grant.grant_id]) == {grant.grant_id: 1}

    repository.set_grant_permission(grant_id=grant.grant_id, max_permission="read")
    assert repository.get_folder(user_id="kid", folder_id=folder.folder_id).permission == "read"

    repository.delete_grant(grant_id=grant.grant_id)
    assert repository.list_folders(user_id="kid") == []
    with pytest.raises(FolderUnavailableError):
        repository.delete_grant(grant_id=grant.grant_id)


def test_access_needs_an_existing_person(repository: FolderRepository) -> None:
    with pytest.raises(FolderUnavailableError):
        repository.upsert_grant(
            user_id="nobody", location_id="home", relative_path="", max_permission="read", created_by="admin",
        )


def test_removing_a_person_removes_their_access(repository: FolderRepository) -> None:
    grant = repository.upsert_grant(
        user_id="kid", location_id="home", relative_path="", max_permission="read", created_by="admin",
    )
    repository.insert_folder(
        user_id="kid", grant_id=grant.grant_id, relative_path="", name="Home", permission="read", created_vault=False,
    )
    with psycopg.connect(repository.database_url) as connection:  # type: ignore[attr-defined]
        connection.execute("DELETE FROM vault_private.local_users WHERE user_id='kid'")
    assert repository.list_grants(user_id="kid") == []
    assert repository.list_folders(user_id="kid") == []
