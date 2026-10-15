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


def _connect_oauth(store, owner) -> None:
    store.set_oauth_tokens(
        owner, provider_key="openai", auth_method="chatgpt_oauth",
        token_payload={"access_token": "oauth-access", "_resono_expires_at": 4_102_444_800},
        model_key="gpt-realtime-2.1-mini", background_model_key="gpt-5.6-luna", voice="marin",
    )


def test_oauth_stays_selected_while_api_key_serves_transcription_and_web_search(credential_context) -> None:
    _, store, owner, member = credential_context
    _connect_oauth(store, owner)
    # OAuth only: the API-key capabilities fail with a clear, actionable message.
    assert store.has_api_key(owner, "openai") is False
    with pytest.raises(VoiceProviderCredentialError, match="Live transcription needs an OpenAI API key"):
        store.resolve(owner, "openai", "live_transcription")
    # Saving a key keeps OAuth as the selected conversation method.
    store.set(owner, provider_key="openai", api_key="sk-retained",
              model_key="gpt-realtime-2.1-mini", voice="marin", background_model_key="gpt-5.6-luna")
    assert store.status(owner)["authMethod"] == "chatgpt_oauth"
    assert store.has_api_key(owner, "openai") is True and store.has_api_key(member, "openai") is True
    conversation = store.resolve(owner, "openai")
    assert (conversation.auth_method, conversation.value) == ("chatgpt_oauth", "oauth-access")
    for capability in ("live_transcription", "web_search"):
        credential = store.resolve(owner, "openai", capability)
        assert (credential.auth_method, credential.value) == ("api_key", "sk-retained")
    # Other capabilities and background work keep following the selected method.
    assert store.resolve(owner, "openai", "memory_review").auth_method == "chatgpt_oauth"
    background, model = store.background_access(user_id=owner.user_id, workspace_id=owner.workspace_id)
    assert background.auth_method == "chatgpt_oauth" and model == "gpt-5.6-luna"
    search, _ = store.background_access(user_id=owner.user_id, workspace_id=owner.workspace_id,
                                        capability="web_search")
    assert (search.auth_method, search.value) == ("api_key", "sk-retained")
    # The method can still be switched explicitly, and the capabilities do not move.
    store.select_auth_method(owner, provider_key="openai", auth_method="api_key")
    assert store.resolve(owner, "openai").value == "sk-retained"
    store.select_auth_method(owner, provider_key="openai", auth_method="chatgpt_oauth")
    assert store.resolve(owner, "openai").value == "oauth-access"


def test_api_key_capabilities_do_not_affect_other_providers(credential_context) -> None:
    _, store, owner, _member = credential_context
    store.set(owner, provider_key="xai", api_key="xai-key", model_key="grok-voice-latest",
              voice="eve", background_model_key="grok-4.6")
    assert store.resolve(owner, "xai", "web_search").value == "xai-key"
