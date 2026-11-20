"""Shared test helpers moved out of test modules (TST-01)."""

import os
from urllib.parse import urlsplit

import psycopg
import pytest

from app.core.security.tokens import hash_token
from app.vault_runtime.conversation.repository import ConversationRepository
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.local_identity.service import LocalIdentityService


def require_test_database(database_url):
    """Independent guard BEFORE any connection or destructive fixture operation."""
    try:
        parsed = urlsplit(database_url)
        valid = (parsed.scheme in {"postgres", "postgresql"}
                 and parsed.hostname == "127.0.0.1" and parsed.port == 55436
                 and parsed.path == "/resono_vault_test" and not parsed.query
                 and not parsed.fragment)
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise RuntimeError("Refusing unsafe conversation test database target.")
    return database_url


@pytest.fixture()
def context():
    database_url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Isolated PostgreSQL harness is required; a skip is not verification.")
    database_url = require_test_database(database_url)
    with psycopg.connect(database_url) as connection:
        assert connection.execute("SELECT current_database()").fetchone()[0] == "resono_vault_test"
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
    try:
        identities = LocalIdentityRepository(database_url=database_url)
        service = LocalIdentityService(repository=identities, setup_credential_hash=hash_token("setup"))
        service.ensure_schema()
        owner = service.bootstrap_owner(setup_credential="setup", username="owner",
                                        password="owner-password", display_name="Owner", experience_style="strict")
        service.create_user(actor=owner.principal, username="second", password="second-password",
                            display_name="Second", experience_style="warm")
        second = service.login(username="second", password="second-password")
        repository = ConversationRepository(database_url=database_url)
        repository.ensure_schema()
        yield database_url, service, owner, second, repository
    finally:
        # Revalidate the same explicit test target before cleanup; never reset volumes.
        with psycopg.connect(require_test_database(database_url)) as connection:
            connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")


def share(service, owner, second):
    service.add_member(principal=owner.principal, workspace_id=owner.principal.workspace_id, username="second")
    service.switch_workspace(principal=second.principal, workspace_id=owner.principal.workspace_id)
    return service.authenticate(session_token=second.session_token)
