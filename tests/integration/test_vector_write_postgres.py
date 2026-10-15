from concurrent.futures import ThreadPoolExecutor
import os
import threading
import time
from urllib.parse import urlsplit

import psycopg
import pytest

from app.vault_runtime.memory.contracts import MemoryContractError
from app.vault_runtime.memory.repository import MemoryAuthorizationError, MemoryNotFoundError, MemoryRepository
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from tests.integration.test_memory_postgres import memory_context, _candidate, _entry


@pytest.fixture(autouse=True)
def exact_test_database():
    value = os.getenv("VAULT_TEST_DATABASE_URL")
    if value:
        parsed = urlsplit(value)
        if (parsed.hostname, parsed.port, parsed.path, parsed.username) != (
                "127.0.0.1", 55436, "/resono_vault_test", "vault_test"):
            pytest.fail("Vector-write tests require the exact isolated test database")


def create(memories, principal, *, content="Prefers tea", intent="create", visibility="private"):
    entry = _entry(memories, principal, session="write-race", index=0, text="Remember tea")
    return memories.reconcile_memory(
        user_id=principal.user_id, workspace_id=principal.workspace_id, voice_session_id="write-race",
        candidate=_candidate(content=content, intent=intent, visibility=visibility),
        evidence=((entry.entry_id, "user_statement", "user_asserted", "Remember tea"),),
    )


def store(memories, principal, record, **extra):
    return memories.store_embedding(
        user_id=principal.user_id, workspace_id=principal.workspace_id, memory_id=record.memory_id,
        provider="synthetic-test", model="synthetic-test-model", embedding=[1.0, 0.0],
        content_text=record.content_text, **extra,
    )


class PausedStore(MemoryRepository):
    def __init__(self, url, entered, release):
        super().__init__(database_url=url)
        self.url, self.entered, self.release = url, entered, release

    def _connect(self):
        return psycopg.connect(self.url, application_name="vector-store-race")

    def _memory_by_id_cursor(self, cursor, **kwargs):
        memory = super()._memory_by_id_cursor(cursor, **kwargs)
        self.entered.set()
        if not self.release.wait(5):
            raise RuntimeError("Test coordination timeout")
        return memory


class CorrectionRepository(MemoryRepository):
    def _connect(self):
        return psycopg.connect(self._database_url, application_name="vector-correction-race")


def correction_is_blocked(url, application_name="vector-correction-race"):
    deadline = time.monotonic() + 2
    with psycopg.connect(url, autocommit=True) as connection:
        while time.monotonic() < deadline:
            row = connection.execute(
                """SELECT EXISTS (
                    SELECT 1 FROM pg_stat_activity correction, pg_stat_activity writer
                    WHERE correction.application_name=%s
                      AND writer.application_name='vector-store-race'
                      AND writer.pid=ANY(pg_blocking_pids(correction.pid)))"""
                , (application_name,),
            ).fetchone()
            if row[0]:
                return True
            time.sleep(0.01)
    return False


def test_correction_waits_for_checked_vector_write_then_removes_vector(memory_context):
    url, _identity, owner, _second, memories = memory_context
    principal = owner.principal
    record = create(memories, principal)
    entered, release = threading.Event(), threading.Event()
    paused = PausedStore(url, entered, release)
    correction = CorrectionRepository(database_url=url)
    with ThreadPoolExecutor(max_workers=2) as workers:
        writing = workers.submit(store, paused, principal, record)
        try:
            assert entered.wait(2)
            corrected = workers.submit(create, correction, principal, content="Prefers coffee", intent="correct")
            assert correction_is_blocked(url), "Correction committed between content check and vector upsert"
        finally:
            release.set()
        writing.result(timeout=3)
        corrected.result(timeout=3)
    with psycopg.connect(url) as connection:
        assert connection.execute(
            "SELECT count(*) FROM vault_private.vault_memory_embeddings WHERE memory_id=%s",
            (record.memory_id,),
        ).fetchone()[0] == 0


def test_current_version_required_for_internal_job_aba_snapshot(memory_context):
    _url, _identity, owner, _second, memories = memory_context
    principal = owner.principal
    record = create(memories, principal)
    create(memories, principal, content="Prefers coffee", intent="correct")
    latest = create(memories, principal, content="Prefers tea", intent="correct")
    assert latest.current_version > record.current_version and latest.content_text == record.content_text
    with pytest.raises(MemoryContractError, match="version"):
        store(memories, principal, record, expected_version=record.current_version)
    store(memories, principal, latest, expected_version=latest.current_version)


def test_changed_content_or_deleted_record_cannot_be_embedded(memory_context):
    _url, _identity, owner, _second, memories = memory_context
    principal = owner.principal
    old = create(memories, principal)
    new = create(memories, principal, content="Prefers coffee", intent="correct")
    with pytest.raises(MemoryContractError):
        store(memories, principal, old)
    memories.delete_memory(user_id=principal.user_id, workspace_id=principal.workspace_id, memory_id=new.memory_id)
    with pytest.raises(MemoryNotFoundError):
        store(memories, principal, new)


@pytest.mark.parametrize("version", [0, -1, True, 1.5, "1"])
def test_invalid_expected_version_rejected(memory_context, version):
    _url, _identity, owner, _second, memories = memory_context
    record = create(memories, owner.principal)
    with pytest.raises(MemoryContractError):
        store(memories, owner.principal, record, expected_version=version)


def test_legacy_no_version_write_still_valid_and_wrong_scope_denied(memory_context):
    _url, _identity, owner, second, memories = memory_context
    record = create(memories, owner.principal)
    store(memories, owner.principal, record)
    with pytest.raises((MemoryNotFoundError, MemoryAuthorizationError)):
        store(memories, second.principal, record)


def test_shared_member_revocation_waits_for_write_commit_then_denies_future_writes(memory_context):
    url, identity, owner, second, memories = memory_context
    principal = owner.principal
    record = create(memories, principal, visibility="workspace")
    identity.add_member(principal=principal, workspace_id=principal.workspace_id, username="second")
    identity.switch_workspace(principal=second.principal, workspace_id=principal.workspace_id)
    member = identity.authenticate(session_token=second.session_token)
    entered, release = threading.Event(), threading.Event()
    paused = PausedStore(url, entered, release)
    revoker = LocalIdentityRepository(database_url=url, connector=lambda target: psycopg.connect(
        target, application_name="vector-revoke-race"))
    with ThreadPoolExecutor(max_workers=2) as workers:
        writing = workers.submit(store, paused, member, record, expected_version=record.current_version)
        try:
            assert entered.wait(2)
            revoking = workers.submit(revoker.revoke_member, actor_user_id=principal.user_id,
                                      workspace_id=principal.workspace_id, member_user_id=member.user_id)
            assert correction_is_blocked(url, "vector-revoke-race")
        finally:
            release.set()
        writing.result(timeout=3)
        revoking.result(timeout=3)
    with pytest.raises(MemoryAuthorizationError):
        store(memories, member, record, expected_version=record.current_version)
