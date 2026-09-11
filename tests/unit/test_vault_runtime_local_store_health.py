from contextlib import contextmanager

from app.vault_runtime.local_api.stores import PostgresVaultHealthStore


class FakeCursor:
    def __init__(self) -> None:
        self.query = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def execute(self, query: str) -> None:
        self.query = query

    def fetchone(self):
        return "vault", "vault_user", True, "0.8.2"


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> FakeCursor:
        return self._cursor


def test_postgres_health_preserves_voice_vault_contract() -> None:
    cursor = FakeCursor()
    calls = []

    @contextmanager
    def connect(database_url: str, **kwargs):
        calls.append((database_url, kwargs))
        yield FakeConnection(cursor)

    store = PostgresVaultHealthStore(database_url="postgresql://local/vault", connector=connect)
    assert store.health() == {
        "database": "ok",
        "databaseName": "vault",
        "databaseUser": "vault_user",
        "schemaReady": True,
        "pgvectorVersion": "0.8.2",
    }
    assert calls == [("postgresql://local/vault", {"connect_timeout": 5})]
    assert "vault_private" in cursor.query
    assert "pg_extension" in cursor.query
