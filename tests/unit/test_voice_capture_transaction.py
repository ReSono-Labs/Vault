from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from app.vault_runtime.memory.repository import MemoryRepository, MemoryTranscriptConflictError
from app.vault_runtime.voice.events import VoiceProviderEventCapture
from app.vault_runtime.voice.models import ProviderEvent
from app.vault_runtime.voice.repository import VoiceSessionConflictError, VoiceSessionRepository


def _arguments():
    return dict(user_id="user", workspace_id="workspace", local_session_id="login",
                voice_session_id="voice", provider_event_id="event", event_type="final",
                event_role="user", payload={}, transcript_text="final text",
                transcript_entry_index=0)


class Sessions:
    def __init__(self, *, accepted=True):
        self.connection = object()
        self.accepted = accepted
        self.calls = []

    @contextmanager
    def transaction(self):
        self.calls.append("begin")
        try:
            yield self.connection
        except Exception:
            self.calls.append("rollback")
            raise
        else:
            self.calls.append("commit")

    def record_provider_event_in_transaction(self, connection, **arguments):
        assert connection is self.connection
        self.calls.append("provider")
        return ProviderEvent("event", "voice", "final", "user", 0, self.accepted)


class Memories:
    def __init__(self, sessions, *, error=None):
        self.sessions = sessions
        self.error = error
        self.arguments = None

    def append_transcript_in_transaction(self, connection, **arguments):
        assert connection is self.sessions.connection
        self.arguments = arguments
        self.sessions.calls.append("transcript")
        if self.error is not None:
            raise self.error


@pytest.mark.parametrize("accepted", [True, False])
def test_shared_transaction_appends_even_for_duplicate(accepted):
    sessions = Sessions(accepted=accepted)
    memories = Memories(sessions)
    result = VoiceProviderEventCapture(sessions=sessions, memories=memories).capture(**_arguments())
    assert result.accepted is accepted
    assert sessions.calls == ["begin", "provider", "transcript", "commit"]
    assert memories.arguments["reject_conflicting_duplicate"] is True
    assert memories.arguments["metadata"] == {"providerEventId": "event"}


@pytest.mark.parametrize("error", [RuntimeError("write failed"), MemoryTranscriptConflictError("conflict")])
def test_capture_failure_rolls_back_and_conflict_maps_to_voice(error):
    sessions = Sessions()
    memories = Memories(sessions, error=error)
    expected = VoiceSessionConflictError if isinstance(error, MemoryTranscriptConflictError) else RuntimeError
    with pytest.raises(expected):
        VoiceProviderEventCapture(sessions=sessions, memories=memories).capture(**_arguments())
    assert sessions.calls == ["begin", "provider", "transcript", "rollback"]


def test_provider_only_event_does_not_append_transcript():
    sessions = Sessions()
    memories = Memories(sessions)
    VoiceProviderEventCapture(sessions=sessions, memories=memories).capture(
        **{**_arguments(), "transcript_text": None, "transcript_entry_index": None}
    )
    assert sessions.calls == ["begin", "provider", "commit"]
    assert memories.arguments is None


@pytest.mark.parametrize("change", [dict(transcript_text=None), dict(transcript_entry_index=None), dict(event_role=None)])
def test_bad_capture_envelope_fails_before_transaction(change):
    sessions = Sessions()
    with pytest.raises(ValueError):
        VoiceProviderEventCapture(sessions=sessions, memories=Memories(sessions)).capture(
            **{**_arguments(), **change}
        )
    assert sessions.calls == []


class Cursor:
    def __init__(self, row):
        self.rows = [(1,), row]
        self.statements = []

    def __enter__(self): return self
    def __exit__(self, *arguments): return False
    def execute(self, sql, parameters): self.statements.append((sql, parameters))
    def fetchone(self): return self.rows.pop(0)


class Connection:
    def __init__(self, cursor): self.cursor_value = cursor
    def __enter__(self): return self
    def __exit__(self, *arguments): return False
    def cursor(self): return self.cursor_value


def _row(*, role="user", event_type="final", text="final text", metadata=None):
    return ("entry", "workspace", "user", "voice", 0, role, event_type,
            text, datetime.now(UTC), metadata if metadata is not None else {"providerEventId": "event"})


@pytest.mark.parametrize("change", [dict(role="assistant"), dict(event_type="other"),
                                    dict(text="changed"), dict(metadata={"providerEventId": "other"})])
def test_strict_transcript_rejects_changed_existing_content(change):
    cursor = Cursor(_row(**change))
    repository = MemoryRepository(database_url="unused", connector=lambda _: pytest.fail("nested connect"))
    with pytest.raises(MemoryTranscriptConflictError):
        repository.append_transcript_in_transaction(
            Connection(cursor), user_id="user", workspace_id="workspace", voice_session_id="voice",
            entry_index=0, role="user", event_type="final", text_content="final text",
            metadata={"providerEventId": "event"}, reject_conflicting_duplicate=True,
        )


def test_exact_transcript_retry_preserves_entry_identity_and_normalization():
    cursor = Cursor(_row())
    repository = MemoryRepository(database_url="unused", connector=lambda _: pytest.fail("nested connect"))
    result = repository.append_transcript_in_transaction(
        Connection(cursor), user_id="user", workspace_id="workspace", voice_session_id="voice",
        entry_index=0, role="user", event_type=" final ", text_content=" final text ",
        metadata={"providerEventId": "event"}, entry_id="new-id-on-retry",
        reject_conflicting_duplicate=True,
    )
    assert result.entry_id == "entry" and result.text_content == "final text"
    assert len(cursor.statements) == 2


def test_public_transcript_wrapper_preserves_legacy_duplicate_behavior():
    connection = Connection(Cursor(_row(text="original")))
    calls = []
    def connector(url):
        calls.append(url)
        return connection
    repository = MemoryRepository(database_url="unused", connector=connector)
    result = repository.append_transcript(
        user_id="user", workspace_id="workspace", voice_session_id="voice",
        entry_index=0, role="user", event_type="final", text_content="changed",
    )
    assert result.text_content == "original" and calls == ["unused"]


def test_public_provider_wrapper_delegates_one_existing_connection(monkeypatch):
    connection = Connection(None)
    calls = []
    repository = VoiceSessionRepository(database_url="unused", connector=lambda _: connection)
    sentinel = object()
    def capture(connection_arg, **arguments):
        calls.append((connection_arg, arguments))
        return sentinel
    monkeypatch.setattr(repository, "record_provider_event_in_transaction", capture)
    arguments = _arguments()
    arguments.pop("transcript_text")
    assert repository.record_provider_event(**arguments) is sentinel
    assert calls == [(connection, arguments)]


def test_invalid_public_transcript_does_not_open_database():
    repository = MemoryRepository(database_url="unused", connector=lambda _: pytest.fail("connect"))
    from app.vault_runtime.memory.repository import MemoryContractError
    with pytest.raises(MemoryContractError):
        repository.append_transcript(user_id="user", workspace_id="workspace",
            voice_session_id="voice", entry_index=0, role="invalid",
            event_type="final", text_content="text")


@pytest.mark.parametrize("changes, error", [({"provider_event_id": ""}, ValueError),
    ({"event_role": "invalid"}, ValueError), ({"payload": object()}, TypeError)])
def test_invalid_public_provider_event_does_not_open_database(changes, error):
    repository = VoiceSessionRepository(database_url="unused", connector=lambda _: pytest.fail("connect"))
    arguments = _arguments()
    arguments.pop("transcript_text")
    arguments.update(changes)
    with pytest.raises(error):
        repository.record_provider_event(**arguments)
