from __future__ import annotations

import os

import psycopg
import pytest

from app.vault_runtime.commands.repository import CommandRepository
from app.vault_runtime.folders.errors import FolderInvalidRequestError, FolderUnavailableError
from app.vault_runtime.local_identity.repository import LocalIdentityRepository


@pytest.fixture
def repository() -> CommandRepository:
    database_url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("VAULT_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
    LocalIdentityRepository(database_url=database_url).ensure_schema()
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """INSERT INTO vault_private.local_users
               (user_id, username_normalized, display_name, experience_style, password_hash)
               VALUES ('u', 'u', 'u', 'balanced', 'x')"""
        )
    repository = CommandRepository(database_url=database_url)
    repository.ensure_schema()
    repository.ensure_schema()
    return repository


def test_switch_and_approval_lifecycle(repository: CommandRepository) -> None:
    assert repository.get_setting("commands.enabled") is None
    repository.set_setting("commands.enabled", True, updated_by="u")
    assert repository.get_setting("commands.enabled") is True

    request = repository.create(user_id="u", workspace_id="w", agent="chat", conversation_id="c",
                                directory="local/P", command="ls", state="pending")
    with pytest.raises(FolderInvalidRequestError):
        repository.claim_approved(user_id="u", request_id=request.request_id, conversation_id="c")
    assert [item.request_id for item in repository.pending_for_conversation(user_id="u", conversation_id="c")] == [request.request_id]
    repository.decide(user_id="u", request_id=request.request_id, approve=True)
    with pytest.raises(FolderUnavailableError):
        repository.decide(user_id="u", request_id=request.request_id, approve=True)
    claimed = repository.claim_approved(user_id="u", request_id=request.request_id, conversation_id="c")
    assert claimed.state == "running"
    with pytest.raises(FolderUnavailableError):
        repository.claim_approved(user_id="u", request_id=request.request_id, conversation_id="c")
    repository.finish(request_id=request.request_id, state="completed", outcome={"exit_code": 0})
    assert repository.get(user_id="u", request_id=request.request_id).outcome == {"exit_code": 0}

    with psycopg.connect(repository._database_url) as connection:  # noqa: SLF001
        connection.execute("UPDATE vault_private.command_requests SET expires_at=now() - interval '1 minute'")
    expired = repository.create(user_id="u", workspace_id="w", agent="chat", conversation_id="c",
                                directory="local/P", command="ls", state="pending")
    with psycopg.connect(repository._database_url) as connection:  # noqa: SLF001
        connection.execute("UPDATE vault_private.command_requests SET expires_at=now() - interval '1 minute' "
                           "WHERE request_id=%s", (expired.request_id,))
    with pytest.raises(FolderUnavailableError):
        repository.decide(user_id="u", request_id=expired.request_id, approve=True)
    assert repository.pending_for_conversation(user_id="u", conversation_id="c") == []
