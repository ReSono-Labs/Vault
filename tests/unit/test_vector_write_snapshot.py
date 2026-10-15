from datetime import datetime, timezone

import pytest

from app.vault_runtime.memory.contracts import MemoryCandidate, MemoryReview, ReviewedMemoryCandidate
from app.vault_runtime.memory.models import TranscriptEntry
from app.vault_runtime.memory.pipeline import MemoryPipeline
from app.vault_runtime.memory.service import MemoryService
from tests.unit.test_memory_search_boundary import record


class Embedder:
    model_key = "synthetic-test"

    def embed(self, text):
        return [1.0, 0.0]


class Repository:
    def __init__(self, fail=False):
        self.writes = []
        self.fail = fail

    def memories_missing_embeddings(self, **kwargs):
        return (record(2),)

    def store_embedding(self, **kwargs):
        self.writes.append(kwargs)
        assert kwargs["expected_version"] == 3
        if self.fail:
            raise RuntimeError("stale snapshot")

    def transcript_entries(self, **kwargs):
        return (TranscriptEntry("entry", "w", "u", "voice", 1, "user", "voice.user.final",
                                "Remember invoice", datetime.now(timezone.utc)),)

    def session_summary(self, **kwargs):
        return None

    def ingestion_completed(self, **kwargs):
        return False

    def claim_ingestion(self, **kwargs):
        return True

    def store_summary(self, **kwargs):
        pass

    def reconcile_memory(self, **kwargs):
        return record(2)

    def complete_ingestion(self, **kwargs):
        pass


class Reviewer:
    def review(self, transcript):
        return MemoryReview(summary="Invoice context", memories=(ReviewedMemoryCandidate(
            memory=MemoryCandidate(subject_id="u", domain="project", memory_type="fact", memory_key="invoice",
                                   content_text="Invoice context", source_authority="user_asserted",
                                   confidence="high", sensitivity="normal", intent="create", visibility="private"),
            source_entry_indexes=(1,),
        ),), model="synthetic-reviewer")


@pytest.mark.parametrize("fail", [False, True])
def test_existing_service_producer_forwards_snapshot_version_and_truthful_counts(fail):
    repository = Repository(fail)
    service = MemoryService(repository=repository, embedder_factory=lambda user, workspace: Embedder())
    assert service.ensure_vectors(user_id="u", workspace_id="w") == ((0, 1) if fail else (1, 0))
    assert len(repository.writes) == 1 and repository.writes[0]["expected_version"] == 3


@pytest.mark.parametrize("fail", [False, True])
def test_existing_pipeline_producer_forwards_snapshot_version_and_truthful_counts(fail):
    repository = Repository(fail)
    pipeline = MemoryPipeline(repository=repository, reviewer=Reviewer())
    result = pipeline.embed_records(user_id="u", workspace_id="w", records=[record(2)],
                                    embedder=Embedder(), embedding_provider="synthetic-test")
    assert result == (0 if fail else 1)
    assert len(repository.writes) == 1 and repository.writes[0]["expected_version"] == 3
