from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager, nullcontext
from hashlib import sha256
from itertools import islice
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from app.vault_runtime.memory.contracts import (
    MEMORY_AUTHORITIES,
    REVIEWER_CONTRACT_VERSION,
    MemoryCandidate,
    MemoryContractError,
)
from app.vault_runtime.memory.models import (
    MemoryEmbedding,
    MemoryRecord,
    MemoryRetrievalSnapshot,
    MemoryRetrievalState,
    PendingMemoryAction,
    TranscriptEntry,
)
from app.vault_runtime.memory.schema import ensure_memory_schema
from app.vault_runtime.memory.suppression import canonical_lock, require_not_suppressed, record_suppression


class MemoryRepositoryError(RuntimeError):
    code = "memory_repository_error"


class MemoryAuthorizationError(MemoryRepositoryError):
    code = "memory_authorization_denied"


class MemoryTranscriptConflictError(MemoryRepositoryError):
    code = "memory_transcript_conflict"


class MemoryNotFoundError(MemoryRepositoryError):
    code = "memory_not_found"


class MemoryConfirmationError(MemoryRepositoryError):
    code = "memory_confirmation_required"


def transcript_fingerprint(entries: Iterable[TranscriptEntry]) -> str:
    digest = sha256()
    for entry in entries:
        digest.update(
            json.dumps(
                {
                    "entryIndex": entry.entry_index,
                    "role": entry.role,
                    "eventType": entry.event_type,
                    "text": entry.text_content,
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        digest.update(b"\n")
    return digest.hexdigest()


class MemoryRepository:
    """Voice PostgreSQL persistence adapted to Phase 2 local scope.

    R1 contributes the reconciliation lifecycle; this class deliberately does
    not model a memory/reviewer agent.
    """

    def __init__(
        self,
        *,
        database_url: str,
        connector: Callable[..., AbstractContextManager[Any]] | None = None,
    ) -> None:
        self._database_url = database_url
        self._connector = connector

    def _connect(self):
        if self._connector is not None:
            return self._connector(self._database_url)
        import psycopg

        return psycopg.connect(self._database_url, connect_timeout=5)

    def ensure_schema(self) -> None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                ensure_memory_schema(cursor)

    @staticmethod
    def _require_membership(
        cursor: Any, *, user_id: str, workspace_id: str, lock: bool = False
    ) -> None:
        cursor.execute(
            """
            SELECT 1
            FROM vault_private.local_workspace_memberships m
            JOIN vault_private.local_users u ON u.user_id = m.user_id
            JOIN vault_private.local_workspaces w ON w.workspace_id = m.workspace_id
            WHERE m.user_id = %s AND m.workspace_id = %s AND m.status = 'active'
              AND u.status = 'active' AND w.status = 'active'
            """ + (" FOR SHARE OF m,u,w" if lock else ""),
            (user_id, workspace_id),
        )
        if cursor.fetchone() is None:
            raise MemoryAuthorizationError("Active workspace membership is required.")

    @staticmethod
    def _scope_sql(alias: str = "m") -> str:
        return f"{alias}.workspace_id = %s AND ({alias}.visibility = 'workspace' OR {alias}.user_id = %s)"

    @staticmethod
    def _retrieval_ids(memory_ids: Iterable[str]) -> tuple[str, ...]:
        if isinstance(memory_ids, (str, bytes)):
            raise ValueError("Memory IDs must be a batch, not a string.")
        ids = tuple(islice(memory_ids, 26))
        if len(ids) > 25 or any(
            not isinstance(value, str) or not value or value != value.strip()
            for value in ids
        ) or len(set(ids)) != len(ids):
            raise ValueError("Expected at most 25 distinct nonempty memory IDs.")
        return ids

    def retrieval_snapshot(
        self, *, user_id: str, workspace_id: str,
        memory_ids: Iterable[str] = (),
    ) -> MemoryRetrievalSnapshot:
        ids = self._retrieval_ids(memory_ids)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(
                    cursor, user_id=user_id, workspace_id=workspace_id, lock=True
                )
                return self._retrieval_snapshot_cursor(
                    cursor, user_id=user_id, workspace_id=workspace_id, memory_ids=ids
                )

    def _retrieval_snapshot_cursor(
        self, cursor: Any, *, user_id: str, workspace_id: str,
        memory_ids: Iterable[str] = (),
    ) -> MemoryRetrievalSnapshot:
        """Internal read; caller owns transaction and current scope authority."""
        ids = self._retrieval_ids(memory_ids)
        cursor.execute(
                    """
                    WITH epochs AS (
                      SELECT COALESCE((SELECT retrieval_epoch
                        FROM vault_private.vault_memory_scope_epochs
                        WHERE workspace_id = %s AND user_id IS NULL), 0) AS shared,
                        COALESCE((SELECT retrieval_epoch
                        FROM vault_private.vault_memory_scope_epochs
                        WHERE workspace_id = %s AND user_id = %s), 0) AS private
                    ), memories AS (
                      SELECT m.memory_id, m.workspace_id, m.user_id, m.visibility,
                        m.subject_id, m.domain, m.memory_type, m.memory_key,
                        m.content_text, m.source_authority, m.confidence,
                        m.sensitivity, m.lifecycle_status, m.current_version,
                        m.created_at, m.updated_at, m.retrieval_epoch
                      FROM vault_private.vault_memory_records m
                      WHERE """ + self._scope_sql() + """
                        AND m.lifecycle_status = 'active'
                        AND m.memory_id = ANY(%s::text[])
                    )
                    SELECT epochs.shared, epochs.private, memories.*
                    FROM epochs LEFT JOIN memories ON TRUE ORDER BY memories.memory_id
                    """,
                    (workspace_id, workspace_id, user_id, workspace_id, user_id, list(ids)),
                )
        rows = cursor.fetchall()
        return MemoryRetrievalSnapshot(
            user_id=user_id, workspace_id=workspace_id,
            workspace_epoch=rows[0][0], private_epoch=rows[0][1],
            records=tuple(
                MemoryRetrievalState(MemoryRecord(*row[2:18]), row[18])
                for row in rows if row[2] is not None
            ),
        )

    def append_transcript(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        entry_index: int,
        role: str,
        event_type: str,
        text_content: str,
        metadata: dict[str, object] | None = None,
        entry_id: str | None = None,
    ) -> TranscriptEntry:
        self._validate_transcript(role, entry_index, text_content)
        with self._connect() as connection:
            return self.append_transcript_in_transaction(
                connection, user_id=user_id, workspace_id=workspace_id,
                voice_session_id=voice_session_id, entry_index=entry_index,
                role=role, event_type=event_type, text_content=text_content,
                metadata=metadata, entry_id=entry_id,
            )

    def append_transcript_in_transaction(
        self,
        connection: Any,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        entry_index: int,
        role: str,
        event_type: str,
        text_content: str,
        metadata: dict[str, object] | None = None,
        entry_id: str | None = None,
        reject_conflicting_duplicate: bool = False,
    ) -> TranscriptEntry:
        text = self._validate_transcript(role, entry_index, text_content)
        identifier = entry_id or str(uuid4())
        with connection.cursor() as cursor:
            self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
            cursor.execute(
                """
                INSERT INTO vault_private.vault_transcript_entries
                  (entry_id, workspace_id, user_id, voice_session_id, entry_index,
                   role, event_type, text_content, metadata_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                ON CONFLICT (workspace_id, user_id, voice_session_id, entry_index)
                DO UPDATE SET entry_id = vault_private.vault_transcript_entries.entry_id
                RETURNING entry_id, workspace_id, user_id, voice_session_id, entry_index,
                          role, event_type, text_content, created_at, metadata_json
                """,
                (
                    identifier, workspace_id, user_id, voice_session_id, entry_index,
                    role, event_type.strip(), text, json.dumps(metadata or {}, separators=(",", ":")),
                ),
            )
            row = cursor.fetchone()
            if reject_conflicting_duplicate and (
                row[5:8] != (role, event_type.strip(), text)
                or row[9] != (metadata or {})
            ):
                raise MemoryTranscriptConflictError(
                    "Transcript index was replayed with different content."
                )
            return TranscriptEntry(*row[:9])

    @staticmethod
    def _validate_transcript(role: str, entry_index: int, text_content: str) -> str:
        if role not in {"user", "assistant", "tool"}:
            raise MemoryContractError("invalid transcript role")
        text = text_content.strip()
        if entry_index < 0 or not text or len(text) > 16384:
            raise MemoryContractError("invalid transcript entry")
        return text

    def append_transcript_next(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        role: str,
        event_type: str,
        text_content: str,
        metadata: dict[str, object] | None = None,
    ) -> TranscriptEntry:
        if role not in {"user", "assistant", "tool"}:
            raise MemoryContractError("invalid transcript role")
        text = text_content.strip()
        if not text or len(text) > 16384:
            raise MemoryContractError("invalid transcript entry")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    ("\x1f".join((workspace_id, user_id, voice_session_id, "transcript")),),
                )
                cursor.execute(
                    """
                    SELECT COALESCE(max(entry_index), -1) + 1
                    FROM vault_private.vault_transcript_entries
                    WHERE workspace_id=%s AND user_id=%s AND voice_session_id=%s
                    """,
                    (workspace_id, user_id, voice_session_id),
                )
                entry_index = int(cursor.fetchone()[0])
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_transcript_entries
                      (entry_id,workspace_id,user_id,voice_session_id,entry_index,
                       role,event_type,text_content,metadata_json)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                    RETURNING entry_id,workspace_id,user_id,voice_session_id,entry_index,
                              role,event_type,text_content,created_at
                    """,
                    (
                        str(uuid4()), workspace_id, user_id, voice_session_id, entry_index,
                        role, event_type.strip(), text,
                        json.dumps(metadata or {}, separators=(",", ":")),
                    ),
                )
                return TranscriptEntry(*cursor.fetchone())

    def transcript_entries(
        self, *, user_id: str, workspace_id: str, voice_session_id: str
    ) -> tuple[TranscriptEntry, ...]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    SELECT entry_id, workspace_id, user_id, voice_session_id, entry_index,
                           role, event_type, text_content, created_at
                    FROM vault_private.vault_transcript_entries
                    WHERE workspace_id=%s AND user_id=%s AND voice_session_id=%s
                    ORDER BY entry_index
                    """,
                    (workspace_id, user_id, voice_session_id),
                )
                return tuple(TranscriptEntry(*row) for row in cursor.fetchall())

    def claim_ingestion(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        fingerprint: str,
        contract_version: int = REVIEWER_CONTRACT_VERSION,
        reviewer_model: str = "",
    ) -> bool:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_memory_ingestions
                      (ingestion_id, workspace_id, user_id, voice_session_id,
                       reviewer_contract_version, transcript_fingerprint, state, reviewer_model)
                    VALUES (%s,%s,%s,%s,%s,%s,'running',%s)
                    ON CONFLICT (workspace_id, user_id, voice_session_id,
                                 reviewer_contract_version, transcript_fingerprint)
                    DO NOTHING
                    RETURNING ingestion_id
                    """,
                    (
                        str(uuid4()), workspace_id, user_id, voice_session_id,
                        contract_version, fingerprint, reviewer_model or None,
                    ),
                )
                return cursor.fetchone() is not None

    def ingestion_completed(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        fingerprint: str,
        contract_version: int = REVIEWER_CONTRACT_VERSION,
    ) -> bool:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    SELECT 1 FROM vault_private.vault_memory_ingestions
                    WHERE workspace_id=%s AND user_id=%s AND voice_session_id=%s
                      AND reviewer_contract_version=%s AND transcript_fingerprint=%s
                      AND state='completed'
                    """,
                    (workspace_id, user_id, voice_session_id, contract_version, fingerprint),
                )
                return cursor.fetchone() is not None

    def complete_ingestion(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        fingerprint: str,
        candidate_count: int,
        stored_count: int,
        contract_version: int = REVIEWER_CONTRACT_VERSION,
        _connection: Any = None,
    ) -> None:
        with (nullcontext(_connection) if _connection is not None else self._connect()) as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    UPDATE vault_private.vault_memory_ingestions
                    SET state='completed',candidate_count=%s,stored_count=%s,
                        completed_at=now(),error_code=NULL
                    WHERE workspace_id=%s AND user_id=%s AND voice_session_id=%s
                      AND reviewer_contract_version=%s AND transcript_fingerprint=%s
                    """,
                    (
                        candidate_count, stored_count, workspace_id, user_id,
                        voice_session_id, contract_version, fingerprint,
                    ),
                )
                if cursor.rowcount != 1:
                    raise MemoryRepositoryError("Memory ingestion was not claimed.")

    def store_summary(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        summary_text: str,
        fingerprint: str,
        contract_version: int = REVIEWER_CONTRACT_VERSION,
        _connection: Any = None,
    ) -> str:
        summary = summary_text.strip()
        if not summary:
            raise MemoryContractError("summary text is required")
        with (nullcontext(_connection) if _connection is not None else self._connect()) as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                summary_id = str(uuid4())
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_session_summaries
                      (summary_id,workspace_id,user_id,voice_session_id,summary_text,
                       reviewer_contract_version,transcript_fingerprint)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (workspace_id,user_id,voice_session_id,
                                 reviewer_contract_version,transcript_fingerprint)
                    DO UPDATE SET summary_text=EXCLUDED.summary_text
                    RETURNING summary_id
                    """,
                    (
                        summary_id, workspace_id, user_id, voice_session_id,
                        summary, contract_version, fingerprint,
                    ),
                )
                return str(cursor.fetchone()[0])

    def session_summary(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        fingerprint: str,
        contract_version: int = REVIEWER_CONTRACT_VERSION,
    ) -> str | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    SELECT summary_text FROM vault_private.vault_session_summaries
                    WHERE workspace_id=%s AND user_id=%s AND voice_session_id=%s
                      AND reviewer_contract_version=%s AND transcript_fingerprint=%s
                    """,
                    (workspace_id, user_id, voice_session_id, contract_version, fingerprint),
                )
                row = cursor.fetchone()
                return str(row[0]) if row else None

    def previous_session_summary(
        self, *, user_id: str, workspace_id: str, exclude_voice_session_id: str
    ) -> str | None:
        """Return the most recent completed scoped summary before a new Voice session."""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    SELECT summary_text
                    FROM vault_private.vault_session_summaries
                    WHERE workspace_id=%s AND user_id=%s AND voice_session_id<>%s
                    ORDER BY created_at DESC, summary_id DESC
                    LIMIT 1
                    """,
                    (workspace_id, user_id, exclude_voice_session_id),
                )
                row = cursor.fetchone()
                return str(row[0]) if row else None

    def prepare_suppression_reviews(self, *, user_id, workspace_id, candidates, reviewer, model,
                                    evidence=(), source_refs=(), step=None):
        from .suppression import (suppression_rows,retained_forgotten_facts,prepare_semantic_review,
            suppression_fingerprint,candidate_fingerprint,explicit_remember_after,content_digest,identity_digest)
        with self._connect() as connection,connection.cursor() as cursor:
            self._require_membership(cursor,user_id=user_id,workspace_id=workspace_id)
            rows=suppression_rows(cursor,user_id,workspace_id)
            fingerprint=suppression_fingerprint(rows)
            proofs=[dict(scope=(user_id,workspace_id),candidate=candidate_fingerprint(c),
                suppression=fingerprint,blocked=[]) for c in candidates]
            pending=[]
            relevant=[]
            for index,candidate in enumerate(candidates):
                cited=evidence[index] if evidence else ()
                refs=source_refs[index] if source_refs else ()
                active=[r for r in rows if not explicit_remember_after(cursor,user_id,workspace_id,cited,refs,r[6])]
                ids={e[0] for e in cited if e[0] is not None}
                ids.update('source-ref:'+r['sourceId'] for r in refs if r is not None)
                deterministic=[r[0] for r in active if r[4]==content_digest(candidate.content_text)
                    or r[3]==identity_digest(candidate) and ids.intersection(r[5])]
                proofs[index]['blocked']=deterministic
                if active and not deterministic:
                    pending.append((index,candidate,active))
                    relevant.extend(active)
            facts=retained_forgotten_facts(cursor,workspace_id,list({r[0]:r for r in relevant}.values())) if pending else {}
        # Provider work occurs BEFORE canonical publication locks/transaction.
        # Resolve only authorized original facts with exact tombstone digest matches.
        groups={}
        for index,candidate,active in pending:
            key=tuple(r[0] for r in active)
            groups.setdefault(key,[]).append((index,candidate,active))
        calls=sum(((len(group)+7)//8)*((len(group[0][2])+7)//8) for group in groups.values())
        if calls>128:
            from .suppression import MemorySuppressionReviewRequired
            raise MemorySuppressionReviewRequired("Forgotten-fact review requires bounded continuation.")
        for ordinal,group in enumerate(groups.values()):
            prepared=prepare_semantic_review(rows=group[0][2],facts=facts,candidates=[g[1] for g in group],
                reviewer=reviewer,model=model,
                step=(lambda key,text,produce:step(str(ordinal)+':'+key,text,produce)) if step else None)
            for (index,_,_),proof in zip(group,prepared):
                proofs[index]['blocked']=proof['blocked']
        return proofs

    def reconcile_memory(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str,
        candidate: MemoryCandidate,
        evidence: tuple[tuple[str | None, str, str, str], ...],
        evidence_source_refs: tuple[dict | None, ...] | None = None,
        contract_version: int = REVIEWER_CONTRACT_VERSION,
        semantic_proof: dict | None = None,
        _connection: Any = None,
    ) -> MemoryRecord:
        item = candidate.validated()
        if not evidence:
            raise MemoryContractError("memory evidence is required")
        for _, _, authority, excerpt in evidence:
            if authority not in MEMORY_AUTHORITIES or not excerpt.strip():
                raise MemoryContractError("invalid memory evidence")
        if evidence_source_refs is not None:
            from .analysis_spans import validate_reference
            if len(evidence_source_refs) != len(evidence):
                raise MemoryContractError("Evidence source references must align with citations.")
            for reference, (_, _, _, excerpt) in zip(evidence_source_refs, evidence):
                if reference is not None:
                    validate_reference(reference, excerpt)
        with (nullcontext(_connection) if _connection is not None else self._connect()) as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute("SELECT pg_advisory_xact_lock_shared(hashtextextended(%s, 81008))", (workspace_id,))
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (canonical_lock(workspace_id,user_id,item),),
                )
                require_not_suppressed(cursor,user_id=user_id,workspace_id=workspace_id,item=item,evidence=evidence,
                    evidence_source_refs=evidence_source_refs,semantic_proof=semantic_proof,
                    require_semantic=getattr(self,'require_semantic_suppression',False))
                owner_predicate = "AND user_id=%s" if item.visibility == "private" else ""
                owner_params: tuple[object, ...] = (user_id,) if item.visibility == "private" else ()
                cursor.execute(
                    f"""
                    SELECT * FROM vault_private.vault_memory_records
                    WHERE workspace_id=%s AND visibility=%s {owner_predicate}
                      AND subject_id=%s AND domain=%s AND memory_type=%s AND memory_key=%s
                      AND lifecycle_status IN ('active','conflicted')
                    ORDER BY updated_at DESC FOR UPDATE
                    """,
                    (
                        workspace_id, item.visibility, *owner_params, item.subject_id,
                        item.domain, item.memory_type, item.memory_key,
                    ),
                )
                current = cursor.fetchone()
                if current is None:
                    memory_id, version = str(uuid4()), 1
                    status = "conflicted" if item.intent == "conflict" else "active"
                    cursor.execute(
                        """
                        INSERT INTO vault_private.vault_memory_records
                          (memory_id,workspace_id,user_id,visibility,subject_id,domain,memory_type,
                           memory_key,content_text,source_authority,confidence,sensitivity,
                           lifecycle_status,current_version)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            memory_id, workspace_id, user_id, item.visibility, item.subject_id,
                            item.domain, item.memory_type, item.memory_key, item.content_text,
                            item.source_authority, item.confidence, item.sensitivity, status, version,
                        ),
                    )
                else:
                    memory_id = str(current[0])
                    version = int(current[13])
                    same_content = str(current[8]) == item.content_text
                    if same_content and item.intent not in {"correct", "conflict"}:
                        cursor.execute(
                            """
                            UPDATE vault_private.vault_memory_records
                            SET confidence=%s, source_authority=%s, updated_at=now()
                            WHERE memory_id=%s
                            """,
                            (item.confidence, item.source_authority, memory_id),
                        )
                    else:
                        version += 1
                        status = "active" if item.intent == "correct" else "conflicted"
                        cursor.execute(
                            """
                            UPDATE vault_private.vault_memory_records
                            SET content_text=%s,source_authority=%s,confidence=%s,sensitivity=%s,
                                lifecycle_status=%s,current_version=%s,updated_at=now()
                            WHERE memory_id=%s
                            """,
                            (
                                item.content_text, item.source_authority, item.confidence,
                                item.sensitivity, status, version, memory_id,
                            ),
                        )
                        cursor.execute(
                            "DELETE FROM vault_private.vault_memory_embeddings WHERE memory_id=%s",
                            (memory_id,),
                        )
                version_id = str(uuid4())
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_memory_record_versions
                      (version_id,memory_id,version_number,actor_user_id,intent,content_text,source_authority,
                       confidence,sensitivity,source_session_id,reviewer_contract_version)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (memory_id,version_number) DO NOTHING
                    RETURNING version_id
                    """,
                    (
                        version_id, memory_id, version, user_id, item.intent, item.content_text,
                        item.source_authority, item.confidence, item.sensitivity,
                        voice_session_id, contract_version,
                    ),
                )
                inserted = cursor.fetchone()
                if inserted is None:
                    cursor.execute(
                        """
                        SELECT version_id FROM vault_private.vault_memory_record_versions
                        WHERE memory_id=%s AND version_number=%s
                        """,
                        (memory_id, version),
                    )
                    version_id = str(cursor.fetchone()[0])
                for evidence_index, (entry_id, kind, authority, excerpt) in enumerate(evidence):
                    reference = evidence_source_refs[evidence_index] if evidence_source_refs is not None else None
                    cursor.execute(
                        """
                        INSERT INTO vault_private.vault_memory_evidence
                          (evidence_id,version_id,transcript_entry_id,evidence_kind,
                           source_authority,evidence_text,source_ref_json)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (str(uuid4()), version_id, entry_id, kind, authority, excerpt[:16384],
                         Jsonb(reference) if reference is not None else None),
                    )
                return self._memory_by_id_cursor(
                    cursor, user_id=user_id, workspace_id=workspace_id, memory_id=memory_id
                )

    def memory(self, *, user_id: str, workspace_id: str, memory_id: str) -> MemoryRecord:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                return self._memory_by_id_cursor(
                    cursor, user_id=user_id, workspace_id=workspace_id, memory_id=memory_id
                )

    def memory_evidence(
        self, *, user_id: str, workspace_id: str, memory_id: str
    ) -> tuple[dict[str, object], ...]:
        """Return evidence for the current scoped memory version only."""
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                memory = self._memory_by_id_cursor(
                    cursor, user_id=user_id, workspace_id=workspace_id, memory_id=memory_id
                )
                cursor.execute(
                    """
                    SELECT e.evidence_kind,e.source_authority,e.evidence_text,
                           e.transcript_entry_id,e.source_ref_json
                    FROM vault_private.vault_memory_record_versions v
                    JOIN vault_private.vault_memory_evidence e ON e.version_id=v.version_id
                    WHERE v.memory_id=%s AND v.version_number=%s
                    ORDER BY e.evidence_id
                    """,
                    (memory.memory_id, memory.current_version),
                )
                return tuple({
                    "evidenceKind": str(row[0]), "sourceAuthority": str(row[1]),
                    "evidenceText": str(row[2]),
                    "transcriptEntryId": str(row[3]) if row[3] is not None else None,
                    **({"sourceRef": row[4]} if row[4] is not None else {}),
                } for row in cursor.fetchall())

    def _memory_by_id_cursor(
        self, cursor: Any, *, user_id: str, workspace_id: str, memory_id: str,
        lock: bool = False,
    ) -> MemoryRecord:
        cursor.execute(
            f"""
            SELECT m.memory_id,m.workspace_id,m.user_id,m.visibility,m.subject_id,m.domain,
                   m.memory_type,m.memory_key,m.content_text,m.source_authority,m.confidence,
                   m.sensitivity,m.lifecycle_status,m.current_version,m.created_at,m.updated_at
            FROM vault_private.vault_memory_records m
            JOIN vault_private.local_workspace_memberships membership
              ON membership.workspace_id=m.workspace_id AND membership.user_id=%s
             AND membership.status='active'
            WHERE m.memory_id=%s AND {self._scope_sql('m')}
            """ + (" FOR UPDATE OF m" if lock else ""),
            (user_id, memory_id, workspace_id, user_id),
        )
        row = cursor.fetchone()
        if row is None:
            raise MemoryNotFoundError("Memory is unavailable in the active scope.")
        return MemoryRecord(*row)

    def profile_memories(
        self, *, user_id: str, workspace_id: str, limit: int = 8
    ) -> tuple[MemoryRecord, ...]:
        bounded = max(1, min(int(limit), 32))
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    f"""
                    SELECT m.memory_id,m.workspace_id,m.user_id,m.visibility,m.subject_id,m.domain,
                           m.memory_type,m.memory_key,m.content_text,m.source_authority,m.confidence,
                           m.sensitivity,m.lifecycle_status,m.current_version,m.created_at,m.updated_at
                    FROM vault_private.vault_memory_records m
                    WHERE {self._scope_sql('m')} AND m.lifecycle_status='active'
                      AND m.confidence IN ('medium','high') AND m.sensitivity='normal'
                    ORDER BY CASE m.domain WHEN 'identity' THEN 0 WHEN 'personal' THEN 1
                      WHEN 'relationship' THEN 2 WHEN 'environment' THEN 3
                      WHEN 'platform' THEN 4 WHEN 'project' THEN 5 ELSE 6 END,
                      m.updated_at DESC LIMIT %s
                    """,
                    (workspace_id, user_id, bounded),
                )
                return tuple(MemoryRecord(*row) for row in cursor.fetchall())

    @staticmethod
    def _chat_action_source(cursor, *, user_id, workspace_id, conversation_id, turn_id):
        cursor.execute("""SELECT ordinal,input_text FROM vault_private.vault_conversation_turns
          WHERE user_id=%s AND workspace_id=%s AND conversation_id=%s AND turn_id=%s
          AND state IN ('running','completed') FOR SHARE""",
          (user_id,workspace_id,conversation_id,turn_id))
        row=cursor.fetchone()
        if row is None:
            raise MemoryConfirmationError("An original submitted Chat turn is required.")
        return row

    def prepare_action(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str | None = None,
        prepared_entry_index: int | None = None,
        conversation_id: str | None = None,
        turn_id: str | None = None,
        local_session_id: str | None = None,
        action_kind: str,
        memory_id: str,
        proposed_content: str | None = None,
    ) -> str:
        if action_kind not in {"correct", "forget"}:
            raise MemoryContractError("unsupported memory action")
        content = proposed_content.strip() if proposed_content is not None else None
        if action_kind == "correct" and (not content or len(content) > 4096):
            raise MemoryContractError("correction content is required and bounded")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                self._memory_by_id_cursor(cursor, user_id=user_id, workspace_id=workspace_id, memory_id=memory_id)
                if conversation_id is not None and turn_id is not None and voice_session_id is None:
                    from app.vault_runtime.local_identity.authority import has_current_session_scope
                    if not local_session_id or not has_current_session_scope(cursor,user_id=user_id,
                        workspace_id=workspace_id,local_session_id=local_session_id,lock=True):
                        raise MemoryConfirmationError("Current local session is required.")
                    prepared_entry_index,_ = self._chat_action_source(cursor,user_id=user_id,workspace_id=workspace_id,
                        conversation_id=conversation_id,turn_id=turn_id)
                else:
                    cursor.execute("""SELECT 1 FROM vault_private.vault_transcript_entries
                      WHERE workspace_id=%s AND user_id=%s AND voice_session_id=%s
                        AND entry_index=%s AND role='user'""",
                      (workspace_id,user_id,voice_session_id,prepared_entry_index))
                    if cursor.fetchone() is None:
                        raise MemoryConfirmationError("Preparing user transcript entry is required.")
                action_id = str(uuid4())
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_memory_pending_actions
                      (action_id,workspace_id,user_id,voice_session_id,memory_id,action_kind,
                       proposed_content,prepared_entry_index,conversation_id,prepared_turn_id)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        action_id, workspace_id, user_id, voice_session_id, memory_id,
                        action_kind, content, prepared_entry_index, conversation_id, turn_id,
                    ),
                )
                return action_id

    def consume_action(
        self,
        *,
        user_id: str,
        workspace_id: str,
        voice_session_id: str | None = None,
        action_id: str,
        confirmation_entry_index: int | None = None,
        conversation_id: str | None = None,
        turn_id: str | None = None,
        _connection: Any = None,
    ) -> PendingMemoryAction:
        with (nullcontext(_connection) if _connection is not None else self._connect()) as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    """
                    SELECT action_kind,memory_id,proposed_content,prepared_entry_index,prepared_turn_id
                    FROM vault_private.vault_memory_pending_actions
                    WHERE action_id=%s AND workspace_id=%s AND user_id=%s
                      AND voice_session_id IS NOT DISTINCT FROM %s
                      AND conversation_id IS NOT DISTINCT FROM %s AND status='pending'
                    FOR UPDATE
                    """,
                    (action_id, workspace_id, user_id, voice_session_id, conversation_id),
                )
                action = cursor.fetchone()
                source_ref=None
                if conversation_id is not None and turn_id is not None and voice_session_id is None:
                    if action is None or action[4] is None:
                        raise MemoryConfirmationError("Original prepared Chat action is unavailable.")
                    prepared_ordinal,_=self._chat_action_source(cursor,user_id=user_id,workspace_id=workspace_id,
                        conversation_id=conversation_id,turn_id=action[4])
                    if prepared_ordinal!=action[3]:
                        raise MemoryConfirmationError("Original prepared Chat source changed.")
                    confirmation_entry_index,text=self._chat_action_source(cursor,user_id=user_id,workspace_id=workspace_id,
                        conversation_id=conversation_id,turn_id=turn_id)
                    if len(text)>16384:
                        raise MemoryConfirmationError("Use a confirmation message within 16384 characters so its original evidence is retained completely.")
                    from .analysis_spans import source_reference
                    source_ref=source_reference("chat-final:"+turn_id,"user",text)
                    confirmation=(None,text)
                else:
                    cursor.execute("""SELECT entry_id,text_content FROM vault_private.vault_transcript_entries
                      WHERE workspace_id=%s AND user_id=%s AND voice_session_id=%s
                        AND entry_index=%s AND role='user'""",
                      (workspace_id,user_id,voice_session_id,confirmation_entry_index))
                    confirmation=cursor.fetchone()
                if action is None or confirmation_entry_index is None or confirmation_entry_index <= int(action[3]) or confirmation is None:
                    raise MemoryConfirmationError("A later same-session user confirmation is required.")
                cursor.execute(
                    """
                    UPDATE vault_private.vault_memory_pending_actions
                    SET status='consumed', consumed_at=now()
                    WHERE action_id=%s AND status='pending'
                    RETURNING action_id
                    """,
                    (action_id,),
                )
                if cursor.fetchone() is None:
                    raise MemoryConfirmationError("Memory action was already consumed.")
                return PendingMemoryAction(
                    action_id=action_id,
                    action_kind=str(action[0]),
                    memory_id=str(action[1]),
                    proposed_content=str(action[2]) if action[2] is not None else None,
                    confirmation_entry_id=str(confirmation[0]) if confirmation[0] is not None else None,
                    confirmation_text=str(confirmation[1]),
                    confirmation_source_ref=source_ref,
                )

    def delete_memory(self, *, user_id: str, workspace_id: str, memory_id: str, _connection: Any = None) -> bool:
        with (nullcontext(_connection) if _connection is not None else self._connect()) as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                # Exclusive vs reconciliation's shared workspace fence also
                # closes the replay race when a reviewer changes memory_key.
                cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 81008))", (workspace_id,))
                memory = self._memory_by_id_cursor(cursor, user_id=user_id, workspace_id=workspace_id, memory_id=memory_id)
                cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    (canonical_lock(workspace_id,memory.user_id,memory),))
                memory = self._memory_by_id_cursor(cursor,user_id=user_id,workspace_id=workspace_id,
                    memory_id=memory_id,lock=True)
                record_suppression(cursor,memory)
                cursor.execute(
                    f"DELETE FROM vault_private.vault_memory_records m WHERE m.memory_id=%s AND {self._scope_sql('m')} RETURNING m.memory_id",
                    (memory_id, workspace_id, user_id),
                )
                return cursor.fetchone() is not None

    def lexical_memories(
        self, *, user_id: str, workspace_id: str, query: str, limit: int = 25
    ) -> tuple[MemoryRecord, ...]:
        stop_words = {
            "and", "are", "for", "from", "has", "have", "how", "the", "this",
            "that", "was", "what", "when", "where", "which", "who", "with", "your",
        }
        terms = [
            term for term in re.findall(r"[a-z0-9]+", query.lower())
            if len(term) >= 3 and term not in stop_words
        ][:8]
        if not terms:
            return ()
        bounded = max(1, min(int(limit), 50))
        clauses = " OR ".join("lower(m.content_text) LIKE %s" for _ in terms)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    f"""
                    SELECT m.memory_id,m.workspace_id,m.user_id,m.visibility,m.subject_id,m.domain,
                           m.memory_type,m.memory_key,m.content_text,m.source_authority,m.confidence,
                           m.sensitivity,m.lifecycle_status,m.current_version,m.created_at,m.updated_at
                    FROM vault_private.vault_memory_records m
                    WHERE {self._scope_sql('m')} AND m.lifecycle_status='active'
                      AND ({clauses}) ORDER BY m.updated_at DESC LIMIT %s
                    """,
                    (workspace_id, user_id, *(f"%{term}%" for term in terms), bounded),
                )
                return tuple(MemoryRecord(*row) for row in cursor.fetchall())

    def store_embedding(
        self,
        *,
        user_id: str,
        workspace_id: str,
        memory_id: str,
        provider: str,
        model: str,
        embedding: list[float],
        content_text: str,
        expected_version: int | None = None,
    ) -> None:
        if expected_version is not None and (type(expected_version) is not int or expected_version < 1):
            raise MemoryContractError("embedding snapshot version must be a positive integer")
        if not provider.strip() or not model.strip() or not embedding:
            raise MemoryContractError("real embedding provider, model and vector are required")
        vector = tuple(float(value) for value in embedding)
        if any(value != value or abs(value) == float("inf") for value in vector):
            raise MemoryContractError("embedding contains a non-finite value")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id, lock=True)
                memory = self._memory_by_id_cursor(
                    cursor, user_id=user_id, workspace_id=workspace_id, memory_id=memory_id, lock=True
                )
                if expected_version is not None and memory.current_version != expected_version:
                    raise MemoryContractError("embedding snapshot version must match current memory version")
                if memory.content_text != content_text:
                    raise MemoryContractError("embedding content must match current memory content")
                cursor.execute(
                    """
                    INSERT INTO vault_private.vault_memory_embeddings
                      (memory_id,provider,model,dimensions,vector_json,embedding,content_fingerprint)
                    VALUES (%s,%s,%s,%s,%s::jsonb,%s::vector,%s)
                    ON CONFLICT (memory_id) DO UPDATE SET
                      provider=EXCLUDED.provider,model=EXCLUDED.model,
                      dimensions=EXCLUDED.dimensions,vector_json=EXCLUDED.vector_json,
                      embedding=EXCLUDED.embedding,
                      content_fingerprint=EXCLUDED.content_fingerprint,updated_at=now()
                    """,
                    (
                        memory_id, provider.strip(), model.strip(), len(vector),
                        json.dumps(vector, separators=(",", ":")),
                        "[" + ",".join(str(value) for value in vector) + "]",
                        sha256(content_text.encode("utf-8")).hexdigest(),
                    ),
                )

    def embeddings_for(
        self, *, user_id: str, workspace_id: str, model: str | None = None
    ) -> tuple[MemoryEmbedding, ...]:
        model_clause = "AND e.model=%s" if model is not None else ""
        params: tuple[object, ...] = (workspace_id, user_id, *((model,) if model is not None else ()))
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    f"""
                    SELECT e.memory_id,e.provider,e.model,e.dimensions,e.vector_json,e.content_fingerprint
                    FROM vault_private.vault_memory_embeddings e
                    JOIN vault_private.vault_memory_records m ON m.memory_id=e.memory_id
                    WHERE {self._scope_sql('m')} AND m.lifecycle_status='active' {model_clause}
                    """,
                    params,
                )
                results = []
                for row in cursor.fetchall():
                    raw = row[4] if isinstance(row[4], list) else json.loads(str(row[4]))
                    results.append(
                        MemoryEmbedding(
                            memory_id=str(row[0]), provider=str(row[1]), model=str(row[2]),
                            dimensions=int(row[3]), embedding=tuple(float(value) for value in raw),
                            content_fingerprint=str(row[5]),
                        )
                    )
                return tuple(results)

    def memories_missing_embeddings(
        self, *, user_id: str, workspace_id: str, model: str, limit: int = 256,
        after_memory_id: str | None = None,
    ) -> tuple[MemoryRecord, ...]:
        bounded = max(1, min(int(limit), 1000))
        if after_memory_id is not None and (type(after_memory_id) is not str or len(after_memory_id)>256):
            raise ValueError("Invalid bounded embedding maintenance cursor.")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._require_membership(cursor, user_id=user_id, workspace_id=workspace_id)
                cursor.execute(
                    f"""
                    SELECT m.memory_id,m.workspace_id,m.user_id,m.visibility,m.subject_id,m.domain,
                           m.memory_type,m.memory_key,m.content_text,m.source_authority,m.confidence,
                           m.sensitivity,m.lifecycle_status,m.current_version,m.created_at,m.updated_at
                    FROM vault_private.vault_memory_records m
                    LEFT JOIN vault_private.vault_memory_embeddings e ON e.memory_id=m.memory_id
                    WHERE {self._scope_sql('m')} AND m.lifecycle_status='active'
                      AND (e.memory_id IS NULL OR e.model<>%s
                        OR e.content_fingerprint<>encode(sha256(convert_to(m.content_text,'UTF8')),'hex'))
                      {"AND m.memory_id > %s" if after_memory_id is not None else ""}
                    ORDER BY {"m.memory_id" if after_memory_id is not None else "m.updated_at ASC"} LIMIT %s
                    """,
                    (workspace_id, user_id, model, *((after_memory_id,) if after_memory_id is not None else ()), bounded),
                )
                return tuple(MemoryRecord(*row) for row in cursor.fetchall())
