from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
from urllib.parse import urlsplit

import psycopg
import pytest

from app.vault_runtime.memory.repository import MemoryAuthorizationError
from tests.integration.test_memory_postgres import memory_context, _candidate, _entry


@pytest.fixture(autouse=True)
def exact_test_database():
    value = os.getenv("VAULT_TEST_DATABASE_URL")
    if value:
        parsed = urlsplit(value)
        if (parsed.hostname, parsed.port, parsed.path, parsed.username) != (
            "127.0.0.1", 55436, "/resono_vault_test", "vault_test"
        ):
            pytest.fail("Retrieval-state tests require the exact isolated database")


def create(memories, principal, *, key="drink", visibility="private", confidence="high"):
    entry = _entry(memories, principal, session=key, index=0, text="Remember tea")
    return memories.reconcile_memory(
        user_id=principal.user_id, workspace_id=principal.workspace_id,
        voice_session_id=key,
        candidate=replace(_candidate(content="Prefers tea", visibility=visibility),
                          memory_key=key, confidence=confidence),
        evidence=((entry.entry_id, "user_statement", "user_asserted", entry.text_content),),
    )


def snapshot(memories, principal, *ids):
    return memories.retrieval_snapshot(user_id=principal.user_id,
        workspace_id=principal.workspace_id, memory_ids=ids)


def test_empty_add_metadata_noop_delete_and_repeat_schema(memory_context):
    url, _identity, owner, _second, memories = memory_context
    principal = owner.principal
    empty = snapshot(memories, principal)
    record = create(memories, principal, confidence="medium")
    added = snapshot(memories, principal, record.memory_id)
    assert empty.fingerprint != added.fingerprint
    assert added.records[0].memory == record
    assert added.records[0].retrieval_epoch == 1
    confirmed = create(memories, principal, confidence="high")
    changed = snapshot(memories, principal, record.memory_id)
    assert confirmed.current_version == record.current_version
    assert changed.records[0].retrieval_epoch == 2
    assert changed.fingerprint != added.fingerprint
    with psycopg.connect(url) as connection:
        connection.execute("UPDATE vault_private.vault_memory_records SET retrieval_epoch=1 WHERE memory_id=%s",
                           (record.memory_id,))
    assert snapshot(memories, principal, record.memory_id) == changed
    memories.ensure_schema()
    assert snapshot(memories, principal, record.memory_id) == changed
    memories.delete_memory(user_id=principal.user_id, workspace_id=principal.workspace_id,
                           memory_id=record.memory_id)
    deleted = snapshot(memories, principal, record.memory_id)
    assert not deleted.records and deleted.fingerprint != changed.fingerprint


def test_private_scope_isolation_shared_visibility_move_and_revocation(memory_context):
    url, identity, owner, second, memories = memory_context
    principal = owner.principal
    identity.add_member(principal=principal, workspace_id=principal.workspace_id, username="second")
    identity.switch_workspace(principal=second.principal, workspace_id=principal.workspace_id)
    member = identity.authenticate(session_token=second.session_token)
    before = snapshot(memories, member)
    private = create(memories, principal)
    assert snapshot(memories, member, private.memory_id) == before
    owner_before = snapshot(memories, principal, private.memory_id)
    with psycopg.connect(url) as connection:
        connection.execute("UPDATE vault_private.vault_memory_records SET visibility='workspace' WHERE memory_id=%s",
                           (private.memory_id,))
    shared = snapshot(memories, member, private.memory_id)
    owner_shared = snapshot(memories, principal, private.memory_id)
    assert shared.fingerprint != before.fingerprint and len(shared.records) == 1
    assert owner_shared.workspace_epoch > owner_before.workspace_epoch
    assert owner_shared.private_epoch > owner_before.private_epoch
    with psycopg.connect(url) as connection:
        connection.execute("UPDATE vault_private.local_workspace_memberships SET status='revoked' WHERE user_id=%s AND workspace_id=%s",
                           (member.user_id, member.workspace_id))
    with pytest.raises(MemoryAuthorizationError):
        snapshot(memories, member)


def test_rollback_and_concurrent_scope_increments(memory_context):
    url, _identity, owner, _second, memories = memory_context
    principal = owner.principal
    record = create(memories, principal)
    before = snapshot(memories, principal, record.memory_id)
    with psycopg.connect(url) as connection:
        connection.execute("UPDATE vault_private.vault_memory_records SET content_text='rolled back' WHERE memory_id=%s",
                           (record.memory_id,))
        connection.rollback()
    assert snapshot(memories, principal, record.memory_id) == before
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(create, memories, principal, key=key) for key in ("one", "two")]
        for future in futures:
            future.result(timeout=10)
    assert snapshot(memories, principal).private_epoch == before.private_epoch + 2


def test_additive_legacy_migration_preserves_evidence_and_vector(memory_context):
    url, _identity, owner, _second, memories = memory_context
    principal = owner.principal
    record = create(memories, principal)
    memories.store_embedding(user_id=principal.user_id, workspace_id=principal.workspace_id,
        memory_id=record.memory_id, provider="synthetic", model="synthetic",
        embedding=[1.0, 0.0], content_text=record.content_text)
    with psycopg.connect(url) as connection:
        vector = connection.execute("SELECT content_fingerprint, embedding::text FROM vault_private.vault_memory_embeddings").fetchall()
        evidence = connection.execute("SELECT * FROM vault_private.vault_memory_evidence").fetchall()
        # Only exact newly owned metadata objects, in the gated throwaway schema.
        connection.execute("DROP TRIGGER vault_memory_scope_epoch ON vault_private.vault_memory_records")
        connection.execute("DROP TRIGGER vault_memory_record_epoch ON vault_private.vault_memory_records")
        connection.execute("DROP TABLE vault_private.vault_memory_scope_epochs")
        connection.execute("ALTER TABLE vault_private.vault_memory_records DROP COLUMN retrieval_epoch")
    memories.ensure_schema()
    migrated = snapshot(memories, principal, record.memory_id)
    assert migrated.records[0].memory == record
    assert migrated.records[0].retrieval_epoch == 1
    with psycopg.connect(url) as connection:
        assert connection.execute("SELECT content_fingerprint, embedding::text FROM vault_private.vault_memory_embeddings").fetchall() == vector
        assert connection.execute("SELECT * FROM vault_private.vault_memory_evidence").fetchall() == evidence


def test_workspace_cascade_does_not_resurrect_counter(memory_context):
    url, _identity, owner, _second, memories = memory_context
    principal = owner.principal
    create(memories, principal, visibility="workspace")
    with psycopg.connect(url) as connection:
        connection.execute("DELETE FROM vault_private.local_workspaces WHERE workspace_id=%s", (principal.workspace_id,))
        assert connection.execute("SELECT count(*) FROM vault_private.vault_memory_scope_epochs WHERE workspace_id=%s",
                                  (principal.workspace_id,)).fetchone()[0] == 0


def test_logical_user_erasure_removes_private_epochs_and_invalidates_shared(memory_context):
    url, identity, owner, second, memories = memory_context
    principal = owner.principal
    identity.add_member(principal=principal, workspace_id=principal.workspace_id, username="second")
    identity.switch_workspace(principal=second.principal, workspace_id=principal.workspace_id)
    member = identity.authenticate(session_token=second.session_token)
    create(memories, member)
    create(memories, member, key="shared", visibility="workspace")
    before = snapshot(memories, principal)
    identity.remove_user(actor=principal, user_id=member.user_id)
    assert snapshot(memories, principal).workspace_epoch > before.workspace_epoch
    with psycopg.connect(url) as connection:
        assert connection.execute("SELECT status FROM vault_private.local_users WHERE user_id=%s",
                                  (member.user_id,)).fetchone()[0] == "deleted"
        assert connection.execute("SELECT count(*) FROM vault_private.vault_memory_scope_epochs WHERE user_id=%s",
                                  (member.user_id,)).fetchone()[0] == 0


def test_recency_content_aba_and_workspace_move_invalidate_both_corpora(memory_context):
    url, _identity, owner, second, memories = memory_context
    principal = owner.principal
    record = create(memories, principal, visibility="workspace")
    initial = snapshot(memories, principal, record.memory_id)
    other = snapshot(memories, second.principal)
    with psycopg.connect(url) as connection:
        connection.execute("UPDATE vault_private.vault_memory_records SET updated_at=updated_at + interval '1 second' WHERE memory_id=%s",
                           (record.memory_id,))
    recent = snapshot(memories, principal, record.memory_id)
    assert recent.records[0].memory.current_version == record.current_version
    assert recent.records[0].retrieval_epoch == 2
    assert recent.fingerprint != initial.fingerprint
    with psycopg.connect(url) as connection:
        connection.execute("UPDATE vault_private.vault_memory_records SET content_text='coffee' WHERE memory_id=%s", (record.memory_id,))
        connection.execute("UPDATE vault_private.vault_memory_records SET content_text=%s WHERE memory_id=%s", (record.content_text, record.memory_id))
    aba = snapshot(memories, principal, record.memory_id)
    assert aba.records[0].retrieval_epoch == 4
    assert aba.records[0].memory.content_text == record.content_text
    assert aba.fingerprint != recent.fingerprint
    with psycopg.connect(url) as connection:
        connection.execute("UPDATE vault_private.vault_memory_records SET workspace_id=%s WHERE memory_id=%s",
                           (second.principal.workspace_id, record.memory_id))
    moved_from = snapshot(memories, principal, record.memory_id)
    moved_to = snapshot(memories, second.principal, record.memory_id)
    assert not moved_from.records and moved_from.fingerprint != aba.fingerprint
    assert len(moved_to.records) == 1 and moved_to.fingerprint != other.fingerprint
