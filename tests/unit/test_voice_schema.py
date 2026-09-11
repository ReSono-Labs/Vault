from app.vault_runtime.voice.schema import SCHEMA_FINGERPRINT, SCHEMA_STATEMENTS


def test_voice_schema_has_only_local_session_ledgers() -> None:
    sql = "\n".join(SCHEMA_STATEMENTS).lower()
    assert len(SCHEMA_FINGERPRINT) == 64
    assert "vault_voice_sessions" in sql
    assert "vault_voice_provider_events" in sql
    assert "vault_voice_tool_invocations" in sql
    assert "route_grant" not in sql and "teardown_delivery" not in sql
    assert "resono_api" not in sql and "service_api_key" not in sql


def test_voice_provider_table_is_created_before_migrations_and_dependents() -> None:
    statements = [statement.lower() for statement in SCHEMA_STATEMENTS]
    create_provider = next(
        index for index, statement in enumerate(statements)
        if "create table if not exists vault_private.vault_voice_provider_credentials" in statement
    )
    alter_provider = next(
        index for index, statement in enumerate(statements)
        if "alter table vault_private.vault_voice_provider_credentials" in statement
    )
    create_oauth = next(
        index for index, statement in enumerate(statements)
        if "create table if not exists vault_private.vault_ai_oauth_credentials" in statement
    )
    assert create_provider < alter_provider < create_oauth
