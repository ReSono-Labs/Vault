import ast
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

import pytest

from app.vault_runtime.conversation.contracts import (
    ConversationSegment, InputError, history_version, identifier, text_fingerprint,
)
from app.vault_runtime.conversation.repository import ConversationRepository


def test_text_fingerprint_preserves_exact_bytes_and_multibyte_boundary():
    for text in (" \nhello\t ", "a" * 65536, "é" * 32768):
        assert text_fingerprint(text) == sha256(text.encode("utf-8")).hexdigest()
    assert text_fingerprint(" hello ") != text_fingerprint("hello")


@pytest.mark.parametrize("text", ["", " \n\t", "a" * 65537, "é" * 32768 + "a",
                                   "x\x00y", "\ud800", None, 123])
def test_invalid_text_is_rejected(text):
    with pytest.raises(InputError):
        text_fingerprint(text)


@pytest.mark.parametrize("value", [True, False, -1, 1.0, "1", None])
def test_history_version_is_exact_nonnegative_int(value):
    with pytest.raises(InputError):
        history_version(value)


def test_valid_identifiers_and_versions():
    assert identifier(" key \n") == "key"
    assert identifier("é" * 128) == "é" * 128
    assert history_version(0) == 0
    assert history_version(12) == 12


@pytest.mark.parametrize("value", ["", "  ", "é" * 129, "a" * 257, "x\x00", "\ud800", None])
def test_invalid_identifiers(value):
    with pytest.raises(InputError):
        identifier(value)


def test_validation_occurs_before_connection_or_writes():
    def forbidden_connect(url):
        pytest.fail("invalid input must not connect")

    repository = ConversationRepository(database_url="unused", connector=forbidden_connect)
    with pytest.raises(InputError):
        repository.create(object(), " ")
    with pytest.raises(InputError):
        repository.load(object(), "\x00")
    with pytest.raises(InputError):
        repository.turn(object(), "c", " ")
    for text, version in ((" ", 0), ("valid", True), ("a" * 65537, 0)):
        with pytest.raises(InputError):
            repository.submit_text(object(), "c", "key", text, version)


def test_records_are_immutable():
    now = datetime.now(timezone.utc)
    segment = ConversationSegment("s", "c", "u", "w", 0, "open", now, now)
    with pytest.raises(FrozenInstanceError):
        segment.state = "sealed"


def test_module_dependency_direction_excludes_execution_learning_and_provider():
    root = Path(__file__).resolve().parents[2] / "app/vault_runtime/conversation"
    allowed = {"__future__", "collections.abc", "contextlib", "typing", "uuid",
               "dataclasses", "datetime", "hashlib", "psycopg",
               "app.vault_runtime.conversation.contracts", "app.vault_runtime.conversation.schema",
               "app.vault_runtime.local_identity.models", "app.vault_runtime.local_identity.schema",
               "app.vault_runtime.local_identity.authority"}
    allowed.add("app.vault_runtime.decision_routing.contracts")
    foundation = {"__init__.py", "contracts.py", "schema.py", "repository.py"}
    assert foundation <= {path.name for path in root.glob("*.py")}
    # C08 composes this passive foundation; it does not change its dependency direction.
    for path in (root/name for name in foundation):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert node.module in allowed
            elif isinstance(node, ast.Import):
                assert all(alias.name in allowed for alias in node.names)
