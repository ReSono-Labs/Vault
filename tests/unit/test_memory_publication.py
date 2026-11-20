from types import SimpleNamespace as NS

import pytest

from app.vault_runtime.memory.pipeline import MemoryPipeline
from app.vault_runtime.memory.contracts import MemoryCandidate,MemoryReview,ReviewedMemoryCandidate
from app.vault_runtime.memory.suppression import MemorySuppressedError


def review(index=0):
    candidate=MemoryCandidate(subject_id="u",domain="personal",memory_type="preference",memory_key="tea",
        content_text="Prefers tea",source_authority="user_asserted",confidence="high",sensitivity="normal",intent="create")
    return MemoryReview("Tea preference",(ReviewedMemoryCandidate(candidate,(index,)),),"configured-model")


def test_canonical_publication_passes_original_evidence_and_transaction():
    calls=[]
    repository=NS(reconcile_memory=lambda **kwargs:calls.append(kwargs) or NS(lifecycle_status="active"))
    pipeline=MemoryPipeline(repository=repository,reviewer=None)
    transaction=object()
    result=pipeline.reconcile_review(user_id="u",workspace_id="w",source_session_id="s",review=review(),
        evidence_by_index={0:("source-id","user_statement","I prefer tea")},connection=transaction)
    assert result[0].lifecycle_status=="active"
    assert calls[0]["_connection"] is transaction
    assert calls[0]["evidence"]==(("source-id","user_statement","user_asserted","I prefer tea"),)


def test_all_citations_checked_before_any_publication():
    calls=[]
    pipeline=MemoryPipeline(repository=NS(reconcile_memory=lambda **kwargs:calls.append(kwargs)),reviewer=None)
    combined=MemoryReview("Preferences",review().memories+review(99).memories,"configured-model")
    with pytest.raises(ValueError,match="unavailable source"):
        pipeline.reconcile_review(user_id="u",workspace_id="w",source_session_id="s",review=combined,
            evidence_by_index={0:(None,"chat_user_statement","I prefer tea")})
    assert not calls


def test_suppression_preserves_candidate_disposition_without_publication():
    def suppressed(**kwargs):
        raise MemorySuppressedError("Forgotten")
    pipeline=MemoryPipeline(repository=NS(reconcile_memory=suppressed),reviewer=None)
    assert pipeline.reconcile_review(user_id="u",workspace_id="w",source_session_id="s",review=review(),
        evidence_by_index={0:(None,"user_statement","I prefer tea")})==(None,)


def test_shared_embedding_retries_elsewhere_without_fabricated_vectors():
    calls=[]
    def embed(text):
        raise RuntimeError("Unavailable provider")
    pipeline=MemoryPipeline(repository=NS(store_embedding=lambda **kwargs:calls.append(kwargs)),reviewer=None)
    assert pipeline.embed_records(user_id="u",workspace_id="w",records=[NS(lifecycle_status="active",content_text="tea")],
        embedder=NS(embed=embed),embedding_provider="openai")==0
    assert not calls


def test_nontransactional_repository_cannot_claim_finalization_from_partial_summary():
    entry=NS(entry_index=0,entry_id="entry",role="user",event_type="user.final",text_content="I prefer tea")
    repository=NS(transcript_entries=lambda **kwargs:(entry,),session_summary=lambda **kwargs:"Prior partial summary",
        ingestion_completed=lambda **kwargs:False,claim_ingestion=lambda **kwargs:False)
    pipeline=MemoryPipeline(repository=repository,reviewer=NS(review=lambda text:review()))
    with pytest.raises(ValueError,match="Canonical transactional repository required"):
        pipeline.finalize(user_id="u",workspace_id="w",voice_session_id="s")


def test_source_refs_validated_before_writes_and_use_original_publication_port():
    from app.vault_runtime.memory.analysis_spans import source_reference
    calls=[]
    pipeline=MemoryPipeline(repository=NS(reconcile_memory=lambda **kwargs:calls.append(kwargs)),reviewer=None)
    reference=source_reference("chat-final:turn","user","I prefer tea")
    pipeline.reconcile_review(user_id="u",workspace_id="w",source_session_id="s",review=review(),
        evidence_by_index={0:(None,"chat_user_statement","I prefer tea")},source_refs_by_index={0:reference})
    assert calls[0]["evidence_source_refs"]==(reference,)
    calls.clear()
    with pytest.raises(ValueError):
        pipeline.reconcile_review(user_id="u",workspace_id="w",source_session_id="s",review=review(),
            evidence_by_index={0:(None,"chat_user_statement","I prefer tea")},
            source_refs_by_index={0:{**reference,"sourceFingerprint":"0"*64}})
    assert not calls
