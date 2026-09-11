from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest

from app.core.security.tokens import hash_token
from app.vault_runtime.extensions.secrets import LocalMasterKey
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.local_identity.service import LocalIdentityService
from app.vault_runtime.voice.credentials import VoiceProviderCredentialError, VoiceProviderCredentialStore
from app.vault_runtime.voice.repository import VoiceSessionRepository


@pytest.fixture()
def credential_context(tmp_path: Path):
    database_url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("VAULT_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
    identities = LocalIdentityService(
        repository=LocalIdentityRepository(database_url=database_url),
        setup_credential_hash=hash_token("setup"),
    )
    identities.ensure_schema()
    owner = identities.bootstrap_owner(
        setup_credential="setup", username="owner", password="owner-password",
        display_name="Owner", experience_style="strict",
    )
    identities.create_user(
        actor=owner.principal, username="member", password="member-password",
        display_name="Member", experience_style="warm",
    )
    member = identities.login(username="member", password="member-password")
    member_principal = identities.authenticate(session_token=member.session_token)
    VoiceSessionRepository(database_url=database_url).ensure_schema()
    store = VoiceProviderCredentialStore(
        database_url=database_url, master_key=LocalMasterKey(tmp_path / "voice-provider.key"),
    )
    yield database_url, store, owner.principal, member_principal
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")


def test_voice_provider_secret_is_scoped_encrypted_and_revocable(credential_context) -> None:
    database_url, store, owner, member = credential_context
    secret = "sk-local-owner-secret"
    store.set(
        owner, provider_key="openai", api_key=secret,
        model_key="gpt-realtime", voice="alloy",
    )
    assert store.status(member)["configured"] is True
    assert store.resolve(member, "openai").value == secret
    assert member.workspace_id != owner.workspace_id
    with psycopg.connect(database_url) as connection:
        row = connection.execute(
            "SELECT nonce,ciphertext FROM vault_private.vault_voice_provider_credentials"
        ).fetchone()
    assert row is not None and secret.encode() not in bytes(row[1])
    individual = "sk-individual-member-secret"
    store.set_account_access(
        owner, target_user_id=member.user_id, access_mode="individual",
        api_key=individual,
    )
    access = store.account_access_status(owner, member.user_id)
    assert access["accessMode"] == "individual"
    assert access["individualConfigured"] is True
    assert store.resolve(member, "openai").value == individual
    store.set_account_access(owner, target_user_id=member.user_id, access_mode="shared")
    assert store.resolve(member, "openai").value == secret
    with pytest.raises(VoiceProviderCredentialError):
        store.set(
            member, provider_key="openai", api_key="sk-member",
            model_key="gpt-realtime", voice="alloy",
        )
    store.remove(owner)
    assert store.status(owner)["configured"] is False
    with pytest.raises(VoiceProviderCredentialError):
        store.resolve(owner, "openai")


def test_voice_provider_preferences_update_without_api_key(credential_context) -> None:
    _, store, owner, _member = credential_context
    store.set(
        owner, provider_key="openai", api_key="sk-local-owner-secret",
        model_key="gpt-live-1", voice="Sol",
    )
    store.update_preferences(
        owner, provider_key="openai", model_key="gpt-live-1",
        voice="marin", background_model_key="gpt-5.6-sol",
    )
    status = store.status(owner)
    assert status["voice"] == "marin"
    assert status["backgroundModelKey"] == "gpt-5.6-sol"
    assert store.resolve(owner, "openai").value == "sk-local-owner-secret"
