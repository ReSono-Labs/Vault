from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os

import psycopg
import pytest

from app.core.security.tokens import hash_token
from app.vault_runtime.local_identity.repository import LocalIdentityRepository
from app.vault_runtime.local_identity.service import LocalIdentityService
from app.vault_runtime.memory.contracts import MemoryCandidate, MemoryReview, ReviewedMemoryCandidate
from app.vault_runtime.memory.pipeline import MemoryPipeline
from app.vault_runtime.memory.repository import (
    MemoryAuthorizationError,
    MemoryConfirmationError,
    MemoryNotFoundError,
    MemoryRepository,
    transcript_fingerprint,
)
from app.vault_runtime.memory.service import MemoryService


@pytest.fixture()
def memory_context():
    database_url = os.getenv("VAULT_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("VAULT_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")
    identities = LocalIdentityRepository(database_url=database_url)
    service = LocalIdentityService(
        repository=identities, setup_credential_hash=hash_token("setup")
    )
    service.ensure_schema()
    owner = service.bootstrap_owner(
        setup_credential="setup", username="owner", password="owner-password",
        display_name="Owner", experience_style="strict",
    )
    service.create_user(
        actor=owner.principal, username="second", password="second-password",
        display_name="Second", experience_style="funny",
    )
    second = service.login(username="second", password="second-password")
    memories = MemoryRepository(database_url=database_url)
    memories.ensure_schema()
    yield database_url, service, owner, second, memories
    with psycopg.connect(database_url) as connection:
        connection.execute("DROP SCHEMA IF EXISTS vault_private CASCADE")


def _candidate(*, content: str, visibility: str = "private", intent: str = "create", sensitivity: str = "normal"):
    return MemoryCandidate(
        subject_id="user", domain="personal", memory_type="preference",
        memory_key="drink", content_text=content, source_authority="user_asserted",
        confidence="high", sensitivity=sensitivity, intent=intent, visibility=visibility,
    )


def _entry(memories: MemoryRepository, principal, *, session: str, index: int, text: str):
    return memories.append_transcript(
        user_id=principal.user_id, workspace_id=principal.workspace_id,
        voice_session_id=session, entry_index=index, role="user",
        event_type="voice.user.final", text_content=text,
    )


def test_transcript_fingerprint_and_ingestion_are_idempotent(memory_context) -> None:
    _url, _service, owner, _second, memories = memory_context
    first = _entry(memories, owner.principal, session="s1", index=1, text="Remember tea")
    duplicate = _entry(memories, owner.principal, session="s1", index=1, text="different ignored")
    assert duplicate.entry_id == first.entry_id
    entries = memories.transcript_entries(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s1",
    )
    fingerprint = transcript_fingerprint(entries)
    assert memories.claim_ingestion(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s1", fingerprint=fingerprint,
    )
    assert not memories.claim_ingestion(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s1", fingerprint=fingerprint,
    )


def test_private_isolation_workspace_sharing_and_revocation(memory_context) -> None:
    _url, service, owner, second, memories = memory_context
    evidence = _entry(memories, owner.principal, session="s1", index=1, text="I prefer tea")
    private = memories.reconcile_memory(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s1", candidate=_candidate(content="Prefers tea"),
        evidence=((evidence.entry_id, "explicit_memory_intent", "user_asserted", evidence.text_content),),
    )
    service.add_member(
        principal=owner.principal, workspace_id=owner.principal.workspace_id, username="second"
    )
    service.switch_workspace(
        principal=second.principal, workspace_id=owner.principal.workspace_id
    )
    second_shared = service.authenticate(session_token=second.session_token)
    with pytest.raises(MemoryNotFoundError):
        memories.memory(
            user_id=second_shared.user_id, workspace_id=second_shared.workspace_id,
            memory_id=private.memory_id,
        )
    shared_evidence = _entry(memories, owner.principal, session="s2", index=1, text="Our drink is water")
    shared = memories.reconcile_memory(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s2", candidate=_candidate(content="Workspace prefers water", visibility="workspace"),
        evidence=((shared_evidence.entry_id, "explicit_memory_intent", "user_asserted", shared_evidence.text_content),),
    )
    assert memories.memory(
        user_id=second_shared.user_id, workspace_id=second_shared.workspace_id,
        memory_id=shared.memory_id,
    ).content_text == "Workspace prefers water"
    member_evidence = _entry(
        memories, second_shared, session="member-s1", index=1, text="Correct our drink to coffee"
    )
    shared_updated = memories.reconcile_memory(
        user_id=second_shared.user_id, workspace_id=second_shared.workspace_id,
        voice_session_id="member-s1",
        candidate=_candidate(
            content="Workspace prefers coffee", visibility="workspace", intent="correct"
        ),
        evidence=((member_evidence.entry_id, "user_statement", "user_asserted", member_evidence.text_content),),
    )
    assert shared_updated.memory_id == shared.memory_id
    assert shared_updated.user_id == owner.principal.user_id
    assert shared_updated.content_text == "Workspace prefers coffee"
    service.revoke_member(
        principal=owner.principal, workspace_id=owner.principal.workspace_id, username="second"
    )
    with pytest.raises(MemoryAuthorizationError):
        memories.memory(
            user_id=second_shared.user_id, workspace_id=second_shared.workspace_id,
            memory_id=shared.memory_id,
        )


def test_all_four_users_cannot_probe_each_others_private_memories(memory_context) -> None:
    _url, service, owner, second, memories = memory_context
    principals = [owner.principal, second.principal]
    for number in (3, 4):
        service.create_user(
            actor=owner.principal, username=f"user{number}", password=f"password-{number:02d}",
            display_name=f"User {number}", experience_style="strict",
        )
        principals.append(
            service.login(username=f"user{number}", password=f"password-{number:02d}").principal
        )
    records = []
    for number, principal in enumerate(principals):
        entry = _entry(
            memories, principal, session=f"private-{number}", index=1, text=f"Private {number}"
        )
        records.append(
            memories.reconcile_memory(
                user_id=principal.user_id, workspace_id=principal.workspace_id,
                voice_session_id=f"private-{number}",
                candidate=MemoryCandidate(
                    subject_id="user", domain="identity", memory_type="fact",
                    memory_key=f"private-{number}", content_text=f"Private {number}",
                    source_authority="user_asserted", confidence="high",
                    sensitivity="normal", intent="create", visibility="private",
                ),
                evidence=((entry.entry_id, "user_statement", "user_asserted", entry.text_content),),
            )
        )
    for actor_index, actor in enumerate(principals):
        for record_index, record in enumerate(records):
            if actor_index == record_index:
                assert memories.memory(
                    user_id=actor.user_id, workspace_id=actor.workspace_id,
                    memory_id=record.memory_id,
                ).memory_id == record.memory_id
            else:
                with pytest.raises((MemoryAuthorizationError, MemoryNotFoundError)):
                    memories.memory(
                        user_id=actor.user_id, workspace_id=actor.workspace_id,
                        memory_id=record.memory_id,
                    )


def test_four_users_hold_sessions_and_write_private_memory_concurrently(memory_context) -> None:
    _url, service, owner, second, memories = memory_context
    credentials = [("owner", "owner-password"), ("second", "second-password")]
    for number in (3, 4):
        service.create_user(
            actor=owner.principal, username=f"user{number}", password=f"password-{number:02d}",
            display_name=f"User {number}", experience_style="strict",
        )
        credentials.append((f"user{number}", f"password-{number:02d}"))

    def active_user(index: int, username: str, password: str):
        session = service.login(username=username, password=password)
        principal = service.authenticate(session_token=session.session_token)
        voice_session_id = f"concurrent-{index}"
        entry = memories.append_transcript(
            user_id=principal.user_id, workspace_id=principal.workspace_id,
            voice_session_id=voice_session_id, entry_index=0, role="user",
            event_type="voice.user.final", text_content=f"Private concurrent value {index}",
        )
        record = memories.reconcile_memory(
            user_id=principal.user_id, workspace_id=principal.workspace_id,
            voice_session_id=voice_session_id,
            candidate=MemoryCandidate(
                subject_id="user", domain="personal", memory_type="preference",
                memory_key=f"concurrent-{index}", content_text=f"Private concurrent value {index}",
                source_authority="user_asserted", confidence="high", sensitivity="normal",
                intent="create", visibility="private",
            ),
            evidence=((entry.entry_id, "user_statement", "user_asserted", entry.text_content),),
        )
        return session, principal, record

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            pool.submit(active_user, index, username, password)
            for index, (username, password) in enumerate(credentials)
        ]
    results = [future.result() for future in futures]
    assert len({principal.session_id for _session, principal, _record in results}) == 4
    assert len({principal.workspace_id for _session, principal, _record in results}) == 4
    for actor_index, (session, actor, _owned) in enumerate(results):
        assert service.authenticate(session_token=session.session_token).workspace_id == actor.workspace_id
        for record_index, (_target_session, _target, record) in enumerate(results):
            if actor_index == record_index:
                assert memories.memory(
                    user_id=actor.user_id, workspace_id=actor.workspace_id,
                    memory_id=record.memory_id,
                ).content_text == f"Private concurrent value {actor_index}"
            else:
                with pytest.raises((MemoryAuthorizationError, MemoryNotFoundError)):
                    memories.memory(
                        user_id=actor.user_id, workspace_id=actor.workspace_id,
                        memory_id=record.memory_id,
                    )


def test_versions_evidence_profile_filter_and_lexical(memory_context) -> None:
    url, _service, owner, _second, memories = memory_context
    entry = _entry(memories, owner.principal, session="s1", index=1, text="I prefer tea")
    created = memories.reconcile_memory(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s1", candidate=_candidate(content="Prefers tea"),
        evidence=((entry.entry_id, "explicit_memory_intent", "user_asserted", entry.text_content),),
    )
    correction = _entry(memories, owner.principal, session="s1", index=2, text="Actually coffee")
    updated = memories.reconcile_memory(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s1", candidate=_candidate(content="Prefers coffee", intent="correct"),
        evidence=((correction.entry_id, "explicit_memory_intent", "user_asserted", correction.text_content),),
    )
    assert created.memory_id == updated.memory_id and updated.current_version == 2
    assert memories.lexical_memories(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id, query="coffee"
    )[0].memory_id == created.memory_id
    with psycopg.connect(url) as connection:
        versions = connection.execute(
            "SELECT count(*) FROM vault_private.vault_memory_record_versions WHERE memory_id=%s",
            (created.memory_id,),
        ).fetchone()[0]
        evidence_count = connection.execute(
            "SELECT count(*) FROM vault_private.vault_memory_evidence e JOIN vault_private.vault_memory_record_versions v ON v.version_id=e.version_id WHERE v.memory_id=%s",
            (created.memory_id,),
        ).fetchone()[0]
    assert (versions, evidence_count) == (2, 2)
    sensitive_entry = _entry(memories, owner.principal, session="s2", index=1, text="Sensitive")
    memories.reconcile_memory(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s2",
        candidate=MemoryCandidate(
            subject_id="user", domain="identity", memory_type="fact", memory_key="secret",
            content_text="Sensitive identity", source_authority="user_asserted", confidence="high",
            sensitivity="sensitive", intent="create", visibility="private",
        ),
        evidence=((sensitive_entry.entry_id, "explicit_memory_intent", "user_asserted", "Sensitive"),),
    )
    assert all(item.sensitivity == "normal" for item in memories.profile_memories(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id
    ))


def test_pending_action_requires_real_later_same_session_user_entry(memory_context) -> None:
    _url, _service, owner, second, memories = memory_context
    prepared = _entry(memories, owner.principal, session="s1", index=3, text="Change tea to coffee")
    memory = memories.reconcile_memory(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s1", candidate=_candidate(content="Prefers tea"),
        evidence=((prepared.entry_id, "explicit_memory_intent", "user_asserted", "Prefers tea"),),
    )
    action_id = memories.prepare_action(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s1", prepared_entry_index=3, action_kind="correct",
        memory_id=memory.memory_id, proposed_content="Prefers coffee",
    )
    with pytest.raises(MemoryConfirmationError):
        memories.consume_action(
            user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
            voice_session_id="s1", action_id=action_id, confirmation_entry_index=3,
        )
    _entry(memories, owner.principal, session="s1", index=4, text="Yes, make that correction")
    action = memories.consume_action(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s1", action_id=action_id, confirmation_entry_index=4,
    )
    assert action.proposed_content == "Prefers coffee"
    with pytest.raises(MemoryConfirmationError):
        memories.consume_action(
            user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
            voice_session_id="s1", action_id=action_id, confirmation_entry_index=4,
        )
    with pytest.raises((MemoryAuthorizationError, MemoryConfirmationError)):
        memories.consume_action(
            user_id=second.principal.user_id, workspace_id=second.principal.workspace_id,
            voice_session_id="s1", action_id=action_id, confirmation_entry_index=4,
        )


class _Embedder:
    model_key = "test-real-provider-model"

    def embed(self, text: str) -> list[float]:
        return [1.0, 0.0] if "coffee" in text.lower() else [0.0, 1.0]


class _UnavailableEmbedder:
    model_key = "test-real-provider-model"

    def embed(self, text: str) -> list[float]:
        raise RuntimeError("provider unavailable")


def test_hybrid_retrieval_and_provider_failure_fallback(memory_context) -> None:
    _url, _service, owner, _second, memories = memory_context
    entry = _entry(memories, owner.principal, session="s1", index=1, text="I prefer coffee")
    memory = memories.reconcile_memory(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s1", candidate=_candidate(content="Prefers coffee"),
        evidence=((entry.entry_id, "explicit_memory_intent", "user_asserted", entry.text_content),),
    )
    memories.store_embedding(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        memory_id=memory.memory_id, provider="test-provider", model=_Embedder.model_key,
        embedding=[1.0, 0.0], content_text=memory.content_text,
    )
    service = MemoryService(repository=memories)
    exact = service.search(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        query="Prefers coffee", embedder=None,
    )
    assert exact[0].score == 1.0 and set(exact[0].match_methods) == {"exact", "lexical"}
    semantic = service.search(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        query="coffee choice", embedder=_Embedder(),
    )
    assert "semantic" in semantic[0].match_methods
    fallback = service.search(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        query="coffee", embedder=_UnavailableEmbedder(),
    )
    assert fallback and "lexical" in fallback[0].match_methods


def test_content_change_removes_stale_embedding(memory_context) -> None:
    url, _service, owner, _second, memories = memory_context
    entry = _entry(memories, owner.principal, session="s1", index=1, text="Tea")
    memory = memories.reconcile_memory(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s1", candidate=_candidate(content="Prefers tea"),
        evidence=((entry.entry_id, "user_statement", "user_asserted", "Tea"),),
    )
    memories.store_embedding(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        memory_id=memory.memory_id, provider="test-provider", model=_Embedder.model_key,
        embedding=[0.0, 1.0], content_text=memory.content_text,
    )
    correction = _entry(memories, owner.principal, session="s1", index=2, text="Coffee")
    memories.reconcile_memory(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s1", candidate=_candidate(content="Prefers coffee", intent="correct"),
        evidence=((correction.entry_id, "user_statement", "user_asserted", "Coffee"),),
    )
    with psycopg.connect(url) as connection:
        count = connection.execute(
            "SELECT count(*) FROM vault_private.vault_memory_embeddings WHERE memory_id=%s",
            (memory.memory_id,),
        ).fetchone()[0]
    assert count == 0


def test_service_applies_confirmed_correction_and_forget(memory_context) -> None:
    _url, _identity, owner, _second, memories = memory_context
    initial = _entry(memories, owner.principal, session="s1", index=1, text="I prefer tea")
    memory = memories.reconcile_memory(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s1", candidate=_candidate(content="Prefers tea"),
        evidence=((initial.entry_id, "explicit_memory_intent", "user_asserted", initial.text_content),),
    )
    _entry(memories, owner.principal, session="s1", index=2, text="Change it to coffee")
    correction = memories.prepare_action(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s1", prepared_entry_index=2, action_kind="correct",
        memory_id=memory.memory_id, proposed_content="Prefers coffee",
    )
    _entry(memories, owner.principal, session="s1", index=3, text="Yes")
    service = MemoryService(repository=memories)
    result = service.confirm_action(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s1", action_id=correction, confirmation_entry_index=3,
    )
    assert result.memory is not None and result.memory.content_text == "Prefers coffee"
    _entry(memories, owner.principal, session="s1", index=4, text="Forget that")
    forgetting = memories.prepare_action(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s1", prepared_entry_index=4, action_kind="forget",
        memory_id=memory.memory_id,
    )
    _entry(memories, owner.principal, session="s1", index=5, text="Yes, forget it")
    forgotten = service.confirm_action(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s1", action_id=forgetting, confirmation_entry_index=5,
    )
    assert forgotten.action == "forgotten" and forgotten.memory is None
    with pytest.raises(MemoryNotFoundError):
        memories.memory(
            user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
            memory_id=memory.memory_id,
        )


class _ReviewerCapability:
    def review(self, transcript: str) -> MemoryReview:
        assert "[entryIndex=1]" in transcript
        return MemoryReview(
            summary="The user prefers tea.", model="test-reviewer",
            memories=(
                ReviewedMemoryCandidate(
                    memory=_candidate(content="Prefers tea"), source_entry_indexes=(1,)
                ),
            ),
        )


def test_pipeline_persists_summary_cited_memory_and_idempotent_completion(memory_context) -> None:
    url, _service, owner, _second, memories = memory_context
    _entry(memories, owner.principal, session="s1", index=1, text="Remember that I prefer tea")
    pipeline = MemoryPipeline(repository=memories, reviewer=_ReviewerCapability())
    first = pipeline.finalize(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s1",
    )
    assert first.summary == "The user prefers tea." and first.memory_count == 1
    assert first.embedded_count == 0 and first.embeddings_available is False
    second = pipeline.finalize(
        user_id=owner.principal.user_id, workspace_id=owner.principal.workspace_id,
        voice_session_id="s1",
    )
    assert second.already_completed is True
    with psycopg.connect(url) as connection:
        counts = connection.execute(
            """
            SELECT
              (SELECT count(*) FROM vault_private.vault_session_summaries),
              (SELECT count(*) FROM vault_private.vault_memory_ingestions WHERE state='completed'),
              (SELECT count(*) FROM vault_private.vault_memory_records),
              (SELECT count(*) FROM vault_private.vault_memory_evidence)
            """
        ).fetchone()
    assert counts == (1, 1, 1, 1)


def test_pipeline_persists_real_pgvector_for_scoped_memory(memory_context) -> None:
    url, _service, owner, _second, memories = memory_context
    _entry(memories, owner.principal, session="s1", index=1, text="I prefer coffee")
    result = MemoryPipeline(
        repository=memories, reviewer=_ReviewerCapability(),
    ).finalize(
        user_id=owner.principal.user_id,
        workspace_id=owner.principal.workspace_id,
        voice_session_id="s1",
        embedder=_Embedder(),
        embedding_provider="openai",
    )

    assert result.embedded_count == 1
    assert result.embeddings_available is True
    with psycopg.connect(url) as connection:
        stored = connection.execute(
            """
            SELECT e.provider,e.model,e.dimensions,vector_dims(e.embedding)
            FROM vault_private.vault_memory_embeddings e
            JOIN vault_private.vault_memory_records m ON m.memory_id=e.memory_id
            WHERE m.user_id=%s AND m.workspace_id=%s
            """,
            (owner.principal.user_id, owner.principal.workspace_id),
        ).fetchone()
    assert stored == ("openai", _Embedder.model_key, 2, 2)
