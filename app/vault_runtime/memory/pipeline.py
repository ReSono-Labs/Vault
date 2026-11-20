from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Protocol

from app.vault_runtime.memory.contracts import MemoryReview, REVIEWER_CONTRACT_VERSION
from app.vault_runtime.memory.repository import MemoryRepository, transcript_fingerprint
from app.vault_runtime.memory.retrieval import QueryEmbedder
from app.vault_runtime.memory.suppression import MemorySuppressedError


class MemoryReviewer(Protocol):
    """Review capability protocol. Implementations are not system agents."""

    def review(self, transcript: str) -> MemoryReview: ...


@dataclass(frozen=True, slots=True)
class FinalizeResult:
    voice_session_id: str
    summary: str
    memory_count: int
    embedded_count: int
    model: str
    embeddings_available: bool
    already_completed: bool = False
    decision_review: dict[str,object] | None = None


class MemoryPipeline:
    def __init__(self, *, repository: MemoryRepository, reviewer: MemoryReviewer) -> None:
        self._repository = repository
        self._reviewer = reviewer

    def finalize(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        embedder: QueryEmbedder | None = None,
        embedding_provider: str | None = None,
    ) -> FinalizeResult:
        if not callable(getattr(self._repository,"_connect",None)):
            raise ValueError("Canonical transactional repository required for finalization.")
        from uuid import uuid4
        from psycopg.types.json import Jsonb
        from .analysis_windows import bounded_review,encode_review,decode_review
        from .openai_reviewer import MemoryReviewOverflow
        scope=(workspace_id,user_id,voice_session_id,REVIEWER_CONTRACT_VERSION)
        lock_key=json.dumps(scope,separators=(",",":"))
        connection=self._repository._connect()
        connection.autocommit=True
        try:
            connection.execute("SELECT pg_advisory_lock(hashtextextended(%s,81009))",(lock_key,))
            entries=self._repository.transcript_entries(user_id=user_id,workspace_id=workspace_id,voice_session_id=voice_session_id)
            if not entries:
                raise ValueError("Session has no transcript to review.")
            fingerprint=transcript_fingerprint(entries)
            params=(*scope,fingerprint)
            row=connection.execute("""SELECT state,reviewer_provider,reviewer_model,review_json,analysis_steps_json
              FROM vault_private.vault_memory_ingestions WHERE workspace_id=%s AND user_id=%s
              AND voice_session_id=%s AND reviewer_contract_version=%s AND transcript_fingerprint=%s""",params).fetchone()
            if row and row[0]=='completed':
                summary=self._repository.session_summary(user_id=user_id,workspace_id=workspace_id,
                    voice_session_id=voice_session_id,fingerprint=fingerprint)
                if not summary:
                    raise ValueError("Completed ingestion has no summary.")
                return FinalizeResult(voice_session_id,summary,0,0,row[2] or "",embedder is not None,True)
            identity=getattr(self._reviewer,'model_identity',None)
            provider,model=identity() if callable(identity) else ('custom',None)
            if row and row[1] is not None and (row[1]!=provider or model is not None and row[2]!=model):
                raise ValueError("Checkpointed Voice review model/provider changed.")
            connection.execute("""INSERT INTO vault_private.vault_memory_ingestions
              (ingestion_id,workspace_id,user_id,voice_session_id,reviewer_contract_version,
               transcript_fingerprint,state,reviewer_provider,reviewer_model)
              VALUES(%s,%s,%s,%s,%s,%s,'running',%s,%s) ON CONFLICT
              (workspace_id,user_id,voice_session_id,reviewer_contract_version,transcript_fingerprint)
              DO UPDATE SET reviewer_provider=EXCLUDED.reviewer_provider,
                reviewer_model=COALESCE(vault_memory_ingestions.reviewer_model,EXCLUDED.reviewer_model)""",
              (str(uuid4()),*params,provider,model))
            cached=(row[4] if row else {}) or {}
            def step(key,text,produce):
                binding=sha256(text.encode()).hexdigest()
                if key in cached:
                    if cached[key]['input']!=binding:
                        raise ValueError("Voice analysis source step changed.")
                    return cached[key]['output']
                output=produce()
                cached[key]=dict(input=binding,output=output)
                connection.execute("""UPDATE vault_private.vault_memory_ingestions SET analysis_steps_json=%s
                  WHERE workspace_id=%s AND user_id=%s AND voice_session_id=%s
                  AND reviewer_contract_version=%s AND transcript_fingerprint=%s AND state='running'""",
                  (Jsonb(cached),*params))
                return output
            transcript="\n".join(f"[entryIndex={e.entry_index}] [{e.event_type}] {e.role}: {e.text_content}" for e in entries)
            evidence={e.entry_index:(e.entry_id,'tool_result' if e.role=='tool' else
                'user_statement' if e.role=='user' else 'assistant_statement',e.text_content) for e in entries}
            source_refs=None
            supports_pages=callable(getattr(self._reviewer,'review_page',None))
            windowed=supports_pages and (len(transcript)>60000 or bool(cached))
            if row and row[3] and not row[3].get('windowed'):
                review=decode_review(row[3])
                model=model or row[2] or review.model
                if review.model!=model:
                    raise ValueError("Checkpointed Voice factual model changed.")
            else:
                if not windowed:
                    try:
                        review=self._reviewer.review(transcript).validated()
                        windowed=supports_pages and len(review.memories)>=32
                    except MemoryReviewOverflow:
                        if not supports_pages: raise
                        windowed=True
                if windowed:
                    raw=[(e.entry_id,e.role,e.text_content) for e in entries]
                    review,evidence,source_refs=bounded_review(raw,reviewer=self._reviewer,model=model,step=step)
                    by_id={e.entry_id:e for e in entries}
                    evidence={i:(by_id[source_refs[i]['sourceId']].entry_id,kind.removeprefix('chat_'),text)
                              for i,(_,kind,text) in evidence.items()}
                model=model or review.model
                self.validate_review_evidence(review,evidence)
                if review.model!=model or callable(identity) and identity()!=(provider,model):
                    raise ValueError("Voice factual model/provider changed.")
                connection.execute("""UPDATE vault_private.vault_memory_ingestions
                  SET review_json=%s,reviewer_model=%s WHERE workspace_id=%s AND user_id=%s
                  AND voice_session_id=%s AND reviewer_contract_version=%s AND transcript_fingerprint=%s""",
                  (Jsonb({'windowed':1} if windowed else encode_review(review)),model,*params))
            suppression_proofs=self.prepare_review_suppression(user_id=user_id,workspace_id=workspace_id,
                review=review,evidence_by_index=evidence,source_refs_by_index=source_refs,step=step)
            with connection.transaction():
                with connection.cursor() as cursor:
                    self._repository._require_membership(cursor,user_id=user_id,workspace_id=workspace_id,lock=True)
                current=self._repository.transcript_entries(user_id=user_id,workspace_id=workspace_id,voice_session_id=voice_session_id)
                if transcript_fingerprint(current)!=fingerprint or callable(identity) and identity()!=(provider,model):
                    raise ValueError("Voice source or model changed before publication.")
                stored=self.reconcile_review(user_id=user_id,workspace_id=workspace_id,source_session_id=voice_session_id,
                    review=review,evidence_by_index=evidence,connection=connection,source_refs_by_index=source_refs,
                    suppression_proofs=suppression_proofs)
                records=[r for r in stored if r is not None and r.lifecycle_status=='active']
                self._repository.store_summary(user_id=user_id,workspace_id=workspace_id,voice_session_id=voice_session_id,
                    summary_text=review.summary,fingerprint=fingerprint,_connection=connection)
                self._repository.complete_ingestion(user_id=user_id,workspace_id=workspace_id,voice_session_id=voice_session_id,
                    fingerprint=fingerprint,candidate_count=len(review.memories),stored_count=len(records),_connection=connection)
            embedded=self.embed_records(user_id=user_id,workspace_id=workspace_id,records=records,
                embedder=embedder,embedding_provider=embedding_provider)
            return FinalizeResult(voice_session_id,review.summary,len(records),embedded,review.model,
                embedder is not None and bool(embedding_provider),False)
        finally:
            connection.close()  # Session advisory lock releases on every path.

    def prepare_review_suppression(self, *, user_id, workspace_id, review, evidence_by_index,
                                   source_refs_by_index=None, step=None):
        prepare=getattr(self._repository,'prepare_suppression_reviews',None)
        if not callable(prepare): return None
        self.validate_review_evidence(review,evidence_by_index)
        return prepare(user_id=user_id,workspace_id=workspace_id,
            candidates=[c.memory.validated() for c in review.memories],reviewer=self._reviewer,model=review.model,
            evidence=[tuple((*evidence_by_index[i][:2],c.memory.source_authority,evidence_by_index[i][2])
                for i in c.source_entry_indexes) for c in review.memories],
            source_refs=[tuple(source_refs_by_index[i] for i in c.source_entry_indexes)
                if source_refs_by_index is not None else () for c in review.memories],step=step)

    def reconcile_review(self, *, user_id, workspace_id, source_session_id, review,
                         evidence_by_index, connection=None, source_refs_by_index=None,suppression_proofs=None):
        """One canonical publication loop; adapters supply original evidence projections.

        A caller-owned transaction allows Chat checkpoint and writes to be atomic.
        The returned tuple preserves candidate order; None denotes suppression.
        """
        self.validate_review_evidence(review,evidence_by_index)
        if source_refs_by_index is not None:
            from .analysis_spans import validate_reference
            # Validate every cited reference before the first canonical write.
            for candidate in review.memories:
                for index in candidate.source_entry_indexes:
                    if index not in source_refs_by_index:
                        raise ValueError("Memory source reference is missing.")
                    validate_reference(source_refs_by_index[index], evidence_by_index[index][2])
        if suppression_proofs is None and connection is None:
            suppression_proofs=self.prepare_review_suppression(user_id=user_id,workspace_id=workspace_id,
                review=review,evidence_by_index=evidence_by_index,source_refs_by_index=source_refs_by_index)
        if suppression_proofs is not None and len(suppression_proofs)!=len(review.memories):
            raise ValueError("Forgotten-fact qualification must cover every candidate.")
        records = []
        for candidate_index,reviewed in enumerate(review.memories):
            cited = tuple(evidence_by_index[index] for index in reviewed.source_entry_indexes)
            if (any(kind.endswith('document_observation') for _,kind,_ in cited)
                    and reviewed.memory.source_authority!='model_derived'):
                raise ValueError('External attachment evidence cannot assert user or verified-tool authority.')
            try:
                record = self._repository.reconcile_memory(
                    user_id=user_id,
                    workspace_id=workspace_id,
                    voice_session_id=source_session_id,
                    candidate=reviewed.memory,
                    evidence=tuple(
                        (
                            entry_id,
                            kind,
                            reviewed.memory.source_authority,
                            text,
                        )
                        for entry_id,kind,text in cited
                    ),
                    **({"semantic_proof":suppression_proofs[candidate_index]} if suppression_proofs is not None else {}),
                    **({"_connection":connection} if connection is not None else {}),
                    **({"evidence_source_refs": tuple(source_refs_by_index[index]
                        for index in reviewed.source_entry_indexes)} if source_refs_by_index is not None else {}),
                )
            except MemorySuppressedError:
                records.append(None)
                continue
            records.append(record)
        return tuple(records)

    @staticmethod
    def validate_review_evidence(review,evidence_by_index):
        review.validated()
        if any(any(index not in evidence_by_index for index in candidate.source_entry_indexes)
               for candidate in review.memories):
            raise ValueError("Memory review cites unavailable source evidence.")

    def embed_records(self, *, user_id, workspace_id, records, embedder, embedding_provider):
        """Shared best-effort vector writes; canonical maintenance retries failures."""
        embedded = 0
        if embedder is not None and embedding_provider:
            for memory in records:
                if memory is None or memory.lifecycle_status!="active":
                    continue
                try:
                    vector = embedder.embed(memory.content_text)
                    self._repository.store_embedding(
                        user_id=user_id, workspace_id=workspace_id,
                        memory_id=memory.memory_id, provider=embedding_provider,
                        model=embedder.model_key, embedding=vector,
                        content_text=memory.content_text, expected_version=memory.current_version,
                    )
                    embedded += 1
                except Exception:
                    continue
        return embedded
