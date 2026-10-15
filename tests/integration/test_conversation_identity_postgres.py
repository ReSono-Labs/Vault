from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from hashlib import sha256
import os
from threading import Barrier, Event
import time
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
import pytest

from app.core.security.tokens import hash_token
from app.vault_runtime.conversation.contracts import (
    AuthorizationError, ConflictError, InputError, NotFoundError,
)
from app.vault_runtime.conversation.repository import ConversationRepository
from app.vault_runtime.conversation.schema import SCHEMA_FINGERPRINT
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


@pytest.mark.parametrize("url", [
    "postgresql://127.0.0.1:55436/production",
    "postgresql://remote:55436/resono_vault_test",
    "postgresql://127.0.0.1:5432/resono_vault_test",
    "postgresql://127.0.0.1:55436/resono_vault_test?host=remote",
    "postgresql://127.0.0.1:55436/resono_vault_test#fragment", "invalid", None,
])
def test_fixture_rejects_unsafe_target(url):
    with pytest.raises(RuntimeError, match="unsafe"):
        require_test_database(url)


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


def counts(url):
    with psycopg.connect(url) as connection:
        return tuple(connection.execute(f"SELECT count(*) FROM vault_private.{table}").fetchone()[0]
                     for table in ("vault_conversations", "vault_conversation_segments", "vault_conversation_turns"))


def test_repeated_create_and_submit_exactly_once_and_old_key_retry(context):
    url, service, owner, second, repository = context
    conversation = repository.create(owner.principal, " create-key ")
    for _ in range(10):
        assert repository.create(owner.principal, "create-key") == conversation
    assert counts(url) == (1, 1, 0)
    assert conversation.segments[0].ordinal == 0
    assert conversation.segments[0].state == "open"
    text = "  Exact final text\nwith spaces\t "
    first = repository.submit_text(owner.principal, conversation.conversation_id, "key", text, 0)
    assert first.input_text == text
    assert first.input_fingerprint == sha256(text.encode()).hexdigest()
    assert (first.history_version, first.submitted_history_version, first.ordinal) == (1, 0, 0)
    assert first.input_contract_version == 1 and not first.duplicate
    for _ in range(10):
        duplicate = repository.submit_text(owner.principal, conversation.conversation_id, "key", text, 0)
        assert duplicate == replace(first, duplicate=True)
    with pytest.raises(ConflictError, match="different text"):
        repository.submit_text(owner.principal, conversation.conversation_id, "key", text.strip(), 0)
    newer = repository.submit_text(owner.principal, conversation.conversation_id, "next", "next", 1)
    assert (newer.history_version, newer.ordinal) == (2, 1)
    assert repository.submit_text(owner.principal, conversation.conversation_id, "key", text, 0) == replace(first, duplicate=True)
    assert repository.turn(owner.principal, conversation.conversation_id, first.turn_id) == first
    assert repository.load(owner.principal, conversation.conversation_id).history_version == 2
    assert counts(url) == (1, 1, 2)
    with psycopg.connect(url) as connection:
        assert connection.execute("SELECT to_regclass('vault_private.vault_voice_sessions'),"
                                  "to_regclass('vault_private.vault_memory_records')").fetchone() == (None, None)


def test_concurrent_create_returns_same_header_and_segment(context):
    url, service, owner, second, repository = context
    barrier = Barrier(4)

    def create(_):
        barrier.wait(timeout=5)
        return repository.create(owner.principal, "same-key")

    with ThreadPoolExecutor(max_workers=4) as executor:
        created = list(executor.map(create, range(4)))
    assert all(item == created[0] for item in created)
    assert counts(url) == (1, 1, 0)


def test_concurrent_different_submissions_one_wins_one_conflicts(context):
    url, service, owner, second, repository = context
    conversation = repository.create(owner.principal, "c")
    barrier = Barrier(2)

    def submit(key):
        barrier.wait(timeout=5)
        try:
            return repository.submit_text(owner.principal, conversation.conversation_id, key, key, 0)
        except ConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(submit, ("a", "b")))
    assert results.count("conflict") == 1
    header = repository.load(owner.principal, conversation.conversation_id)
    assert (header.history_version, header.next_turn_ordinal) == (1, 1)
    assert counts(url) == (1, 1, 1)


def fault_connector(*, marker, after):
    @contextmanager
    def connect(url):
        with psycopg.connect(url) as connection:
            class Connection:
                @contextmanager
                def cursor(self):
                    with connection.cursor() as cursor:
                        class Cursor:
                            def execute(self, query, params=None):
                                matches = marker in query
                                if matches and not after:
                                    raise RuntimeError("injected transaction fault")
                                result = cursor.execute(query, params)
                                if matches and after:
                                    raise RuntimeError("injected transaction fault")
                                return result

                            def fetchone(self):
                                return cursor.fetchone()

                            def fetchall(self):
                                return cursor.fetchall()
                        yield Cursor()
            yield Connection()
    return connect


@pytest.mark.parametrize("marker,after", [
    ("INSERT INTO vault_private.vault_conversation_turns", False),
    ("INSERT INTO vault_private.vault_conversation_turns", True),
    ("UPDATE vault_private.vault_conversations", True),
])
def test_submit_transaction_rolls_back_without_advancing_identity(context, marker, after):
    url, service, owner, second, repository = context
    conversation = repository.create(owner.principal, "c")
    broken = ConversationRepository(database_url=url, connector=fault_connector(marker=marker, after=after))
    with pytest.raises(RuntimeError, match="injected"):
        broken.submit_text(owner.principal, conversation.conversation_id, "key", "text", 0)
    assert repository.load(owner.principal, conversation.conversation_id) == conversation
    assert counts(url) == (1, 1, 0)
    assert repository.submit_text(owner.principal, conversation.conversation_id, "key", "text", 0).ordinal == 0


def test_create_header_and_segment_rollback_atomically(context):
    url, service, owner, second, repository = context
    broken = ConversationRepository(database_url=url, connector=fault_connector(
        marker="INSERT INTO vault_private.vault_conversation_segments", after=True))
    with pytest.raises(RuntimeError):
        broken.create(owner.principal, "key")
    assert counts(url) == (0, 0, 0)
    assert len(repository.create(owner.principal, "key").segments) == 1


@pytest.mark.parametrize("text", ["a" * 65536, "é" * 32768])
def test_utf8_size_bound_accepts_exact_and_rejects_extra_byte(context, text):
    url, service, owner, second, repository = context
    conversation = repository.create(owner.principal, "c")
    with pytest.raises(InputError):
        repository.submit_text(owner.principal, conversation.conversation_id, "key", text + "a", 0)
    assert counts(url) == (1, 1, 0)
    assert repository.submit_text(owner.principal, conversation.conversation_id, "key", text, 0).input_text == text


def test_private_scope_shared_workspace_and_device_owner_do_not_override(context):
    url, service, owner, second, repository = context
    private = repository.create(second.principal, "same-key")
    own = repository.create(owner.principal, "same-key")
    with pytest.raises(NotFoundError):
        repository.load(owner.principal, private.conversation_id)
    shared = share(service, owner, second)
    member = repository.create(shared, "same-key")
    assert len({private.conversation_id, own.conversation_id, member.conversation_id}) == 3
    turn = repository.submit_text(shared, member.conversation_id, "key", "private member text", 0)
    for actor, target in ((shared, own), (owner.principal, member)):
        with pytest.raises(NotFoundError):
            repository.load(actor, target.conversation_id)
        with pytest.raises(NotFoundError):
            repository.submit_text(actor, target.conversation_id, "key", "text", 0)
    with pytest.raises(NotFoundError):
        repository.turn(owner.principal, member.conversation_id, turn.turn_id)
    # Cannot claim a workspace just by replacing the principal's fields.
    forged = replace(shared, workspace_id=second.principal.workspace_id)
    with pytest.raises(AuthorizationError):
        repository.load(forged, private.conversation_id)


@pytest.mark.parametrize("revocation", ["membership", "session", "user", "workspace", "expired"])
def test_live_authority_denies_reads_writes_and_duplicate_retries(context, revocation):
    url, service, owner, second, repository = context
    shared = share(service, owner, second)
    conversation = repository.create(shared, "c")
    turn = repository.submit_text(shared, conversation.conversation_id, "key", "text", 0)
    with psycopg.connect(url) as connection:
        if revocation == "membership":
            connection.execute("UPDATE vault_private.local_workspace_memberships SET status='revoked' WHERE user_id=%s AND workspace_id=%s", (shared.user_id, shared.workspace_id))
        elif revocation == "session":
            connection.execute("UPDATE vault_private.local_sessions SET status='revoked' WHERE session_id=%s", (shared.session_id,))
        elif revocation == "user":
            connection.execute("UPDATE vault_private.local_users SET status='locked' WHERE user_id=%s", (shared.user_id,))
        elif revocation == "workspace":
            connection.execute("UPDATE vault_private.local_workspaces SET status='archived' WHERE workspace_id=%s", (shared.workspace_id,))
        else:
            connection.execute("UPDATE vault_private.local_sessions SET expires_at=now()-interval '1 second' WHERE session_id=%s", (shared.session_id,))
    operations = (
        lambda: repository.load(shared, conversation.conversation_id),
        lambda: repository.turn(shared, conversation.conversation_id, turn.turn_id),
        lambda: repository.create(shared, "c"),
        lambda: repository.submit_text(shared, conversation.conversation_id, "key", "text", 0),
    )
    for operation in operations:
        with pytest.raises(AuthorizationError):
            operation()
    assert counts(url) == (1, 1, 1)


def test_history_survives_login_expiry_and_loads_with_new_session(context):
    url, service, owner, second, repository = context
    conversation = repository.create(owner.principal, "c")
    turn = repository.submit_text(owner.principal, conversation.conversation_id, "key", "text", 0)
    with psycopg.connect(url) as connection:
        connection.execute("UPDATE vault_private.local_sessions SET expires_at=now()-interval '1 second' WHERE session_id=%s", (owner.principal.session_id,))
    with pytest.raises(AuthorizationError):
        repository.load(owner.principal, conversation.conversation_id)
    refreshed = service.login(username="owner", password="owner-password")
    assert repository.turn(refreshed.principal, conversation.conversation_id, turn.turn_id) == turn


def test_schema_repeat_preserves_records_and_fingerprint(context):
    url, service, owner, second, repository = context
    conversation = repository.create(owner.principal, "c")
    turn = repository.submit_text(owner.principal, conversation.conversation_id, "key", "text", 0)
    for _ in range(2):
        repository.ensure_schema()
    assert repository.turn(owner.principal, conversation.conversation_id, turn.turn_id) == turn
    with psycopg.connect(url) as connection:
        assert connection.execute("SELECT schema_fingerprint FROM vault_private.local_schema_metadata WHERE schema_key='conversation_v1'").fetchone() == (SCHEMA_FINGERPRINT,)


def test_actual_account_tombstone_erases_shared_rows_only_for_removed_user(context):
    url, service, owner, second, repository = context
    shared = share(service, owner, second)
    member = repository.create(shared, "member")
    repository.submit_text(shared, member.conversation_id, "key", "member text", 0)
    own = repository.create(owner.principal, "owner")
    own_turn = repository.submit_text(owner.principal, own.conversation_id, "key", "owner text", 0)
    service.remove_user(actor=owner.principal, user_id=shared.user_id)
    assert counts(url) == (1, 1, 1)
    assert repository.turn(owner.principal, own.conversation_id, own_turn.turn_id) == own_turn
    with psycopg.connect(url) as connection:
        assert connection.execute("SELECT status FROM vault_private.local_users WHERE user_id=%s", (shared.user_id,)).fetchone() == ("deleted",)
        assert connection.execute("SELECT count(*) FROM vault_private.vault_conversations WHERE user_id=%s", (shared.user_id,)).fetchone() == (0,)


def test_workspace_cascade_deletes_all_owned_children(context):
    url, service, owner, second, repository = context
    shared = share(service, owner, second)
    for actor in (owner.principal, shared):
        conversation = repository.create(actor, "c")
        repository.submit_text(actor, conversation.conversation_id, "key", "text", 0)
    with psycopg.connect(url) as connection:
        connection.execute("DELETE FROM vault_private.local_workspaces WHERE workspace_id=%s", (shared.workspace_id,))
    assert counts(url) == (0, 0, 0)


@pytest.mark.parametrize("invalid", ["cross_user", "cross_workspace", "cross_conversation",
                                    "bad_state", "negative_ordinal", "negative_version",
                                    "bad_fingerprint", "oversize", "empty",
                                    "duplicate_key", "duplicate_ordinal"])
def test_database_turn_constraints_independently_reject_invalid_rows(context, invalid):
    url, service, owner, second, repository = context
    conversation = repository.create(owner.principal, "c")
    repository.submit_text(owner.principal, conversation.conversation_id, "first", "first", 0)
    values = dict(turn_id=str(uuid4()), conversation_id=conversation.conversation_id,
                  segment_id=conversation.segments[0].segment_id,
                  user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
                  ordinal=1, submission_key="second", input_text="text",
                  input_fingerprint=sha256(b"text").hexdigest(), submitted_history_version=1,
                  state="submitted")
    if invalid == "cross_user":
        values["user_id"] = second.principal.user_id
    elif invalid == "cross_workspace":
        values["workspace_id"] = second.principal.workspace_id
    elif invalid == "cross_conversation":
        values["conversation_id"] = repository.create(owner.principal, "other").conversation_id
    elif invalid == "bad_state":
        values["state"] = "unknown"
    elif invalid == "negative_ordinal":
        values["ordinal"] = -1
    elif invalid == "negative_version":
        values["submitted_history_version"] = -1
    elif invalid == "bad_fingerprint":
        values["input_fingerprint"] = "short"
    elif invalid == "oversize":
        values["input_text"] = "é" * 32769
    elif invalid == "empty":
        values["input_text"] = ""
    elif invalid == "duplicate_key":
        values["submission_key"] = "first"
    else:
        values["ordinal"] = 0
    with pytest.raises(psycopg.IntegrityError):
        with psycopg.connect(url) as connection:
            connection.execute(
                f"INSERT INTO vault_private.vault_conversation_turns ({','.join(values)}) "
                f"VALUES ({','.join(['%s'] * len(values))})", tuple(values.values()),
            )
    assert repository.load(owner.principal, conversation.conversation_id).history_version == 1


@pytest.mark.parametrize("invalid", ["title", "header_version", "header_ordinal", "header_state",
                                    "cross_user_segment", "cross_workspace_segment", "second_open_segment",
                                    "duplicate_segment_ordinal", "segment_state", "segment_ordinal"])
def test_database_header_and_segment_constraints(context, invalid):
    url, service, owner, second, repository = context
    conversation = repository.create(owner.principal, "c")
    with pytest.raises(psycopg.IntegrityError):
        with psycopg.connect(url) as connection:
            if invalid in {"title", "header_version", "header_ordinal", "header_state"}:
                column, value = {"title": ("title", "x" * 257),
                                 "header_version": ("history_version", -1),
                                 "header_ordinal": ("next_turn_ordinal", -1),
                                 "header_state": ("state", "unknown")}[invalid]
                connection.execute(f"UPDATE vault_private.vault_conversations SET {column}=%s WHERE conversation_id=%s",
                                   (value, conversation.conversation_id))
            else:
                user_id = second.principal.user_id if invalid == "cross_user_segment" else owner.principal.user_id
                workspace_id = second.principal.workspace_id if invalid == "cross_workspace_segment" else owner.principal.workspace_id
                ordinal = -1 if invalid == "segment_ordinal" else (0 if invalid == "duplicate_segment_ordinal" else 1)
                state = "unknown" if invalid == "segment_state" else ("open" if invalid == "second_open_segment" else "sealed")
                connection.execute("""INSERT INTO vault_private.vault_conversation_segments
                                      (segment_id,conversation_id,user_id,workspace_id,ordinal,state)
                                      VALUES (%s,%s,%s,%s,%s,%s)""",
                                   (str(uuid4()), conversation.conversation_id, user_id, workspace_id, ordinal, state))
    assert repository.load(owner.principal, conversation.conversation_id) == conversation


@pytest.mark.parametrize("seal", ["header", "segment"])
def test_closed_header_or_missing_open_segment_rejects_new_turn_but_keeps_retry(context, seal):
    url, service, owner, second, repository = context
    conversation = repository.create(owner.principal, "c")
    first = repository.submit_text(owner.principal, conversation.conversation_id, "first", "text", 0)
    table = "vault_conversations" if seal == "header" else "vault_conversation_segments"
    with psycopg.connect(url) as connection:
        connection.execute(f"UPDATE vault_private.{table} SET state='sealed' WHERE conversation_id=%s", (conversation.conversation_id,))
    with pytest.raises(ConflictError):
        repository.submit_text(owner.principal, conversation.conversation_id, "second", "text", 1)
    assert repository.submit_text(owner.principal, conversation.conversation_id, "first", "text", 0) == replace(first, duplicate=True)
    assert counts(url) == (1, 1, 1)


def test_physical_user_cascade_preserves_other_member(context):
    url, service, owner, second, repository = context
    shared = share(service, owner, second)
    member = repository.create(shared, "member")
    repository.submit_text(shared, member.conversation_id, "key", "member text", 0)
    own = repository.create(owner.principal, "owner")
    with psycopg.connect(url) as connection:
        # Clear pre-existing identity RESTRICT dependencies, without deleting shared workspace.
        connection.execute("DELETE FROM vault_private.local_workspaces WHERE owner_user_id=%s", (shared.user_id,))
        connection.execute("DELETE FROM vault_private.local_workspace_memberships WHERE user_id=%s", (shared.user_id,))
        connection.execute("DELETE FROM vault_private.local_users WHERE user_id=%s", (shared.user_id,))
    assert counts(url) == (1, 1, 0)
    assert repository.load(owner.principal, own.conversation_id) == own


def test_authority_shared_locks_hold_until_append_commit(context):
    url, service, owner, second, repository = context
    conversation = repository.create(owner.principal, "c")
    authorized, release, revoke_started = Event(), Event(), Event()

    @contextmanager
    def paused_connector(database_url):
        with psycopg.connect(database_url) as connection:
            class Connection:
                @contextmanager
                def cursor(self):
                    with connection.cursor() as cursor:
                        class Cursor:
                            def execute(self, query, params=None):
                                result = cursor.execute(query, params)
                                if "FOR SHARE OF s,u,m,w" in query:
                                    authorized.set()
                                    assert release.wait(timeout=10)
                                return result

                            def fetchone(self):
                                return cursor.fetchone()

                            def fetchall(self):
                                return cursor.fetchall()
                        yield Cursor()
            yield Connection()

    paused = ConversationRepository(database_url=url, connector=paused_connector)

    def revoke():
        with psycopg.connect(url, application_name="c03a-revoke-test") as connection:
            connection.execute("SET statement_timeout='10s'")
            revoke_started.set()
            connection.execute("UPDATE vault_private.local_workspace_memberships SET status='revoked' WHERE user_id=%s AND workspace_id=%s", (owner.principal.user_id, owner.principal.workspace_id))

    with ThreadPoolExecutor(max_workers=2) as executor:
        submit = executor.submit(paused.submit_text, owner.principal, conversation.conversation_id, "key", "text", 0)
        try:
            assert authorized.wait(timeout=5)
            revocation = executor.submit(revoke)
            assert revoke_started.wait(timeout=5)
            deadline = time.monotonic() + 5
            observed_lock = False
            while time.monotonic() < deadline:
                with psycopg.connect(url) as connection:
                    observed_lock = connection.execute("SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE application_name='c03a-revoke-test' AND wait_event_type='Lock')").fetchone()[0]
                if observed_lock:
                    break
                time.sleep(0.01)
            assert observed_lock and not revocation.done()
        finally:
            release.set()
        assert submit.result(timeout=5).history_version == 1
        revocation.result(timeout=5)
    with pytest.raises(AuthorizationError):
        repository.load(owner.principal, conversation.conversation_id)
    assert counts(url) == (1, 1, 1)
